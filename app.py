"""
AI 数据分析助手 —— Flask Web 服务
上传 Excel/CSV → 自然语言提问 → LLM 生成 Pandas 代码 → 沙箱执行 → 文字结论 + 图表
"""
import json
import logging
import os
import re
import time
import uuid

import pandas as pd
from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    make_response,
    render_template,
    request,
    send_file,
    session,
    stream_with_context,
    url_for,
)

import analysis_templates
import auto_analyze
import report_export
import stats_guard
from analyzer import analyze, insight, to_sql

_LOG_PATH = os.getenv("APP_LOG_FILE", "")
_logger = logging.getLogger("ai_data_assistant")
_logger.setLevel(logging.INFO)
if _LOG_PATH and not _logger.handlers:
    os.makedirs(os.path.dirname(os.path.abspath(_LOG_PATH)), exist_ok=True)
    _handler = logging.FileHandler(_LOG_PATH, encoding="utf-8")
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_handler)


def _log_event(event: str, **payload):
    """结构化 JSON 日志事件；不记录 API key、密码、完整 DataFrame。"""
    record = {"event": event, "ts": int(time.time() * 1000), **payload}
    try:
        _logger.info(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    except Exception:
        pass

app = Flask(__name__)
_env = os.getenv("FLASK_ENV", "development").lower()
_secret = os.getenv("FLASK_SECRET")
if not _secret and _env == "production":
    raise RuntimeError("生产环境必须配置 FLASK_SECRET")
app.secret_key = _secret or "local-development-only-secret"
app.config.update(
    MAX_CONTENT_LENGTH=int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024))),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
    JSON_SORT_KEYS=False,
    # session -> { "active": dataset_id, "datasets": {...}, "history": [...] }
    sessions={},
    charts={},
)

BASE = os.path.dirname(__file__)
UPLOAD = os.path.join(BASE, "uploads")
CHARTS = os.path.join(BASE, "charts")
os.makedirs(UPLOAD, exist_ok=True)
os.makedirs(CHARTS, exist_ok=True)

_MAX_CHART_AGE_SECONDS = 24 * 3600


def _cleanup_old_charts():
    """清理超过24小时的旧图表文件。"""
    now = time.time()
    try:
        for name in os.listdir(CHARTS):
            path = os.path.join(CHARTS, name)
            if os.path.isfile(path) and (now - os.path.getmtime(path)) > _MAX_CHART_AGE_SECONDS:
                try:
                    os.remove(path)
                except OSError:
                    pass
    except OSError:
        pass

ALLOWED = {".csv", ".xlsx", ".xls"}
MAX_DATASETS_PER_SESSION = 5
MAX_TOTAL_DATASETS = 50
MAX_QUESTION_LENGTH = 2000
MAX_PREVIEW_CELL_LENGTH = 500
MAX_ROWS = 100000
MAX_COLUMNS = 200
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def _chart_filename(dataset_id: str, suffix: str) -> str:
    return f"{dataset_id}_{suffix}.png"


def _chart_path(name: str) -> str:
    return os.path.join(CHARTS, name)


def _remove_dataset_artifacts(sid: str, dataset_id: str):
    """删除数据集上传文件和该数据集产生的图表。"""
    prefix = f"{sid}_{dataset_id}"
    for directory in (UPLOAD, CHARTS):
        try:
            for name in os.listdir(directory):
                if name.startswith(prefix) or (directory == CHARTS and name.startswith(f"{dataset_id}_")):
                    try:
                        os.remove(os.path.join(directory, name))
                    except OSError:
                        pass
        except OSError:
            pass


def _session_id():
    sid = session.get("sid")
    if not sid:
        sid = str(uuid.uuid4())
        session["sid"] = sid
    return sid


def _session_state(sid: str):
    return app.config["sessions"].setdefault(
        sid, {"active": None, "datasets": {}, "history": []}
    )


def _json_error(message, status=400, code="INVALID_REQUEST"):
    return jsonify({"error": message, "code": code}), status


def _preview_value(value):
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value)
    return text if len(text) <= MAX_PREVIEW_CELL_LENGTH else text[:MAX_PREVIEW_CELL_LENGTH] + "…"


def _dataset_view(dataset_id: str, info: dict) -> dict:
    df = info["df"]
    preview = [
        {str(column): _preview_value(value) for column, value in row.items()}
        for row in df.head(5).to_dict("records")
    ]
    return {
        "dataset_id": dataset_id,
        "name": info.get("name", ""),
        "rows": info.get("rows", int(df.shape[0])),
        "cols": info.get("cols", int(df.shape[1])),
        "columns": info.get("columns", []),
        "preview": preview,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'",
    )
    incoming_id = request.headers.get("X-Request-Id", "")
    request_id = incoming_id if _SAFE_REQUEST_ID.fullmatch(incoming_id) else uuid.uuid4().hex
    response.headers.setdefault("X-Request-Id", request_id)
    return response


@app.errorhandler(413)
def request_too_large(_error):
    return _json_error("上传文件超过大小限制", 413, "PAYLOAD_TOO_LARGE")


@app.route("/health")
def health():
    """前端探测 LLM 是否配置好；不返回 API 地址或密钥。"""
    import llm_client
    ok = bool(llm_client.API_KEY)
    return jsonify({"llm_ready": ok, "model": llm_client.MODEL,
                    "hint": None if ok else "未配置 LLM_API_KEY，请在环境变量设置 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL"})


@app.route("/upload", methods=["POST"])
def upload():
    sid = _session_id()
    state = _session_state(sid)
    f = request.files.get("file")
    if not f or not f.filename:
        return _json_error("未收到文件")
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED:
        return _json_error("仅支持 csv / xlsx / xls")

    if len(state["datasets"]) >= MAX_DATASETS_PER_SESSION:
        return _json_error(
            f"当前会话数据集数量已达上限 {MAX_DATASETS_PER_SESSION}",
            422,
            "DATASET_LIMIT",
        )

    dataset_id = str(uuid.uuid4())
    path = os.path.join(UPLOAD, f"{sid}_{dataset_id}{ext}")
    try:
        f.save(path)
        try:
            df = pd.read_csv(path, encoding="utf-8-sig") if ext == ".csv" else pd.read_excel(path)
        except UnicodeDecodeError:
            df = pd.read_csv(path, encoding="gbk") if ext == ".csv" else pd.read_excel(path)
    except (OSError, UnicodeError, ValueError, pd.errors.ParserError, ImportError):
        try:
            os.remove(path)
        except OSError:
            pass
        return _json_error("文件无法解析，请检查格式和内容", 422, "INVALID_FILE")

    if df.empty or len(df.columns) == 0:
        try:
            os.remove(path)
        except OSError:
            pass
        return _json_error("文件没有可分析的数据", 422, "EMPTY_DATA")
    if len(df) > MAX_ROWS or len(df.columns) > MAX_COLUMNS:
        try:
            os.remove(path)
        except OSError:
            pass
        return _json_error(
            f"数据规模超过限制（最多 {MAX_ROWS} 行、{MAX_COLUMNS} 列）",
            422,
            "DATASET_TOO_LARGE",
        )

    state["datasets"][dataset_id] = {
        "name": f.filename,
        "df": df,
        "rows": int(df.shape[0]),
        "cols": int(df.shape[1]),
        "columns": [{"name": str(c), "dtype": str(t)} for c, t in df.dtypes.items()],
        "created_at": int(time.time()),
    }
    state["active"] = dataset_id

    # 全局 LRU：超过 MAX_TOTAL_DATASETS 时淘汰最早会话的全部数据集
    _evict_oldest_if_needed()

    preview = [
        {str(column): _preview_value(value) for column, value in row.items()}
        for row in df.head(5).to_dict("records")
    ]
    _log_event("dataset_uploaded", dataset_id=dataset_id, rows=len(df), cols=int(df.shape[1]))
    return jsonify({
        "dataset_id": dataset_id,
        "rows": int(df.shape[0]),
        "cols": int(df.shape[1]),
        "columns": [{"name": str(c), "dtype": str(t)} for c, t in df.dtypes.items()],
        "preview": preview,
        "datasets": _serialize_datasets(state),
        "active": dataset_id,
    })


def _serialize_datasets(state) -> list:
    items = []
    for did, info in state["datasets"].items():
        items.append({
            "dataset_id": did,
            "name": info.get("name", ""),
            "rows": info.get("rows", 0),
            "cols": info.get("cols", 0),
            "active": state["active"] == did,
            "created_at": info.get("created_at", 0),
        })
    return items


def _evict_oldest_if_needed():
    sessions = app.config["sessions"]
    overflow = _count_total_datasets(sessions) - MAX_TOTAL_DATASETS
    if overflow <= 0:
        return
    all_datasets = []
    for sid, state in sessions.items():
        for did, info in state["datasets"].items():
            all_datasets.append((info.get("created_at", 0), sid, did))
    all_datasets.sort()
    for _, sid, did in all_datasets[:overflow]:
        state = sessions.get(sid)
        if not state or did not in state["datasets"]:
            continue
        state["datasets"].pop(did)
        _remove_dataset_artifacts(sid, did)
        if state["active"] == did:
            state["active"] = next(iter(state["datasets"]), None)


def _count_total_datasets(sessions) -> int:
    return sum(len(s["datasets"]) for s in sessions.values())


def _record_history(state, entry: dict):
    history = state.setdefault("history", [])
    history.append(entry)
    del history[:-50]


def _active_dataset(sid: str):
    state = _session_state(sid)
    if not state["active"]:
        return None, None
    info = state["datasets"].get(state["active"])
    if not info:
        state["active"] = None
        return None, None
    return state["active"], info


@app.route("/datasets", methods=["GET"])
def list_datasets():
    sid = _session_id()
    state = _session_state(sid)
    return jsonify({"datasets": _serialize_datasets(state), "active": state["active"]})


@app.route("/datasets/select", methods=["POST"])
def select_dataset():
    sid = _session_id()
    state = _session_state(sid)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _json_error("请求体必须是 JSON 对象")
    did = payload.get("dataset_id")
    if not isinstance(did, str) or did not in state["datasets"]:
        return _json_error("数据集不存在", 404, "DATASET_NOT_FOUND")
    state["active"] = did
    info = state["datasets"][did]
    view = _dataset_view(did, info)
    return jsonify({"active": did, **view})


@app.route("/datasets/<did>", methods=["DELETE"])
def delete_dataset(did):
    sid = _session_id()
    state = _session_state(sid)
    if did not in state["datasets"]:
        return _json_error("数据集不存在", 404, "DATASET_NOT_FOUND")
    state["datasets"].pop(did)
    state["history"] = [item for item in state.get("history", []) if item.get("dataset_id") != did]
    _remove_dataset_artifacts(sid, did)
    if state["active"] == did:
        state["active"] = next(iter(state["datasets"]), None)
    return jsonify({"datasets": _serialize_datasets(state), "active": state["active"]})



def _build_context(state, current_q):
    history = state.get("history", [])
    if len(history) < 2:
        return ""
    recent = history[-3:]
    parts = []
    for item in recent:
        q = item.get("question", "")
        str(item.get("result", ""))[:200]
        parts.append(f"Q: {q}")
    parts.append(f"Current: {current_q}")
    return "\n".join(parts)

@app.route("/ask", methods=["POST"])
def ask():
    sid = _session_id()
    did, info = _active_dataset(sid)
    if info is None:
        return _json_error("请先上传数据", 400, "DATASET_REQUIRED")

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _json_error("请求体必须是 JSON 对象")
    q = payload.get("question")
    if not isinstance(q, str):
        return _json_error("问题必须是字符串")
    q = q.strip()
    if not q:
        return _json_error("问题为空")
    if len(q) > MAX_QUESTION_LENGTH:
        return _json_error("问题过长", 422, "QUESTION_TOO_LONG")

    try:
        ctx = _build_context(_session_state(sid), q)
        res = analyze(info["df"], q, context=ctx)
    except Exception:
        return _json_error("分析引擎暂时不可用", 500, "ANALYSIS_ERROR")

    if not res.get("ok"):
        return _json_error("分析失败，请调整问题后重试", 422, res.get("code") or "ANALYSIS_FAILED")

    chart_url = _save_chart(sid, did, q, res.get("chart"))
    result_id = str(uuid.uuid4())
    start = time.monotonic()
    history_entry = {
        "result_id": result_id,
        "dataset_id": did,
        "question": q[:500],
        "result": str(res.get("result") or "")[:12000],
        "code": str(res.get("code") or "")[:20000],
        "chart": chart_url,
        "created_at": int(time.time()),
    }
    _record_history(_session_state(sid), history_entry)
    _log_event("ask_ok", dataset_id=did, result_id=result_id, q_len=len(q),
               has_chart=bool(chart_url),
               duration_ms=int((time.monotonic() - start) * 1000))
    return jsonify({"result": res.get("result"), "chart": chart_url,
                    "code": res.get("code"),
                    "dataset_id": did, "result_id": result_id})


@app.route("/history", methods=["GET"])
def history():
    sid = _session_id()
    state = _session_state(sid)
    return jsonify({
        "items": [
            {key: value for key, value in item.items() if key not in {"code", "result"}}
            for item in reversed(state.get("history", []))
        ]
    })


@app.route("/history/<result_id>", methods=["GET"])
def history_item(result_id):
    sid = _session_id()
    state = _session_state(sid)
    item = next((x for x in state.get("history", []) if x["result_id"] == result_id), None)
    if item is None:
        return _json_error("分析结果不存在", 404, "RESULT_NOT_FOUND")
    return jsonify(item)


@app.route("/history/<result_id>/download/<kind>", methods=["GET"])
def download_history(result_id, kind):
    if kind not in {"result", "code", "sql"}:
        abort(404)
    sid = _session_id()
    state = _session_state(sid)
    item = next((x for x in state.get("history", []) if x["result_id"] == result_id), None)
    if item is None:
        return _json_error("分析结果不存在", 404, "RESULT_NOT_FOUND")
    response = make_response(item.get(kind, ""))
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="{result_id}-{kind}.txt"'
    return response


@app.route("/ask/<result_id>/sql", methods=["GET"])
def get_sql(result_id):
    """按需生成 SQL 对照（用户点击时才调用 LLM）。"""
    sid = _session_id()
    state = _session_state(sid)
    item = next((x for x in state.get("history", []) if x["result_id"] == result_id), None)
    if item is None:
        return _json_error("分析结果不存在", 404, "RESULT_NOT_FOUND")
    if item.get("code"):
        info = state["datasets"].get(item.get("dataset_id"), {})
        df = info.get("df")
        if df is not None:
            sql = to_sql(df, item.get("question", ""), item["code"])
            item["sql"] = str(sql or "")[:12000]
            return jsonify({"sql": sql or None})
    return jsonify({"sql": None})


@app.route("/insights", methods=["POST"])
def insights():
    """自动洞察 / 异常下探：一键出 总览+异常+建议（对应小爱JD）。"""
    sid = _session_id()
    did, info = _active_dataset(sid)
    if info is None:
        return _json_error("请先上传数据", 400, "DATASET_REQUIRED")

    start = time.monotonic()
    try:
        res = insight(info["df"])
    except Exception:
        return _json_error("分析引擎暂时不可用", 500, "ANALYSIS_ERROR")

    if not res.get("ok"):
        return _json_error("洞察失败，请稍后重试", 422, res.get("code") or "INSIGHT_FAILED")

    chart_url = _save_chart(sid, did, "__insight__", res.get("chart"))
    _log_event("insight_ok", dataset_id=did, has_chart=bool(chart_url),
               duration_ms=int((time.monotonic() - start) * 1000))
    return jsonify({"result": res.get("result"), "chart": chart_url, "code": res.get("code"),
                    "dataset_id": did})


def _save_chart(sid, dataset_id, q, chart_bytes):
    """保存图表，返回 URL。文件名 = dataset_id_<suffix>.png。"""
    if not chart_bytes:
        return None
    suffix = uuid.uuid4().hex[:8]
    name = _chart_filename(dataset_id, suffix)
    with open(_chart_path(name), "wb") as fh:
        fh.write(chart_bytes)
    return url_for("chart", name=name)


@app.route("/chart/<name>")
def chart(name):
    """返回当前会话自己的图表，白名单 + dataset ownership 校验。"""
    if not _SAFE_NAME.match(name):
        abort(404)
    sid = _session_id()
    state = _session_state(sid)
    owned_ids = set(state["datasets"])
    if not any(name.startswith(f"{did}_") for did in owned_ids):
        abort(404)
    path = _chart_path(name)
    if not os.path.isfile(path):
        abort(404)
    return send_file(path, mimetype="image/png")


@app.route("/export/notebook", methods=["POST"])
def export_notebook():
    sid = _session_id()
    state = _session_state(sid)
    if not state.get("history"):
        return _json_error("no analysis history", 404, "EMPTY_HISTORY")
    did, info = _active_dataset(sid)
    if info is None:
        return _json_error("upload data first", 400, "DATASET_REQUIRED")
    try:
        filepath = report_export.export_notebook(state, info, state["history"])
        with open(filepath, encoding="utf-8") as fh:
            nb_content = fh.read()
        os.remove(filepath)
        response = make_response(nb_content)
        response.headers["Content-Type"] = "application/json"
        response.headers["Content-Disposition"] = "attachment"
        return response
    except Exception as exc:
        return _json_error(str(exc)[:100], 500, "EXPORT_ERROR")


@app.route("/export/html", methods=["GET"])
def export_html():
    sid = _session_id()
    state = _session_state(sid)
    if not state.get("history"):
        return _json_error("no history", 404, "EMPTY_HISTORY")
    ds_name = "Unknown"
    if state.get("active") and state["active"] in state.get("datasets", {}):
        ds_name = state["datasets"][state["active"]].get("name", "Unknown")
    html_content = report_export.export_html_report(state["history"], ds_name)
    response = make_response(html_content)
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    response.headers["Content-Disposition"] = "inline"
    return response


@app.route("/export/apa/<result_id>", methods=["GET"])
def export_apa(result_id):
    sid = _session_id()
    state = _session_state(sid)
    item = next((x for x in state.get("history", []) if x["result_id"] == result_id), None)
    if item is None:
        return _json_error("not found", 404, "RESULT_NOT_FOUND")
    apa_text = report_export.generate_apa_paragraph(
        question=item.get("question", ""),
        result=str(item.get("result", "")),
    )
    return jsonify({"apa": apa_text})


@app.route("/templates")
def list_templates():
    sid = _session_id()
    _session_state(sid)
    did, info = _active_dataset(sid)
    if info is None:
        return jsonify({"templates": []})
    guard_result = stats_guard.full_guard_check(info["df"])
    matched = analysis_templates.match_templates(guard_result.get("variable_types", []))
    return jsonify({"templates": [
        {"id": t["id"], "name": t["name"], "icon": t["icon"],
         "description": t["description"]} for t in matched
    ]})




@app.route("/ask/stream", methods=["POST"])
def ask_stream():
    import time as _t

    def generate():
        sid = _session_id()
        did, info = _active_dataset(sid)
        if info is None:
            yield "data: " + json.dumps({"step": "error", "message": "upload first"}) + "\n\n"
            return
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not payload.get("question"):
            yield "data: " + json.dumps({"step": "error", "message": "empty question"}) + "\n\n"
            return
        q = payload["question"].strip()
        yield "data: " + json.dumps({"step": "guard", "message": "Checking...", "progress": 15}) + "\n\n"
        yield "data: " + json.dumps({"step": "codegen", "message": "Generating code...", "progress": 35}) + "\n\n"
        start = _t.monotonic()
        try:
            ctx = _build_context(_session_state(sid), q)
            res = analyze(info["df"], q, context=ctx)
        except Exception as exc:
            yield "data: " + json.dumps({"step": "error", "message": str(exc)[:100]}) + "\n\n"
            return
        if not res.get("ok"):
            yield "data: " + json.dumps({"step": "error", "message": str(res.get("error", ""))[:200]}) + "\n\n"
            return
        yield "data: " + json.dumps({"step": "inference", "message": "Computing effect sizes...", "progress": 85}) + "\n\n"
        chart_url = _save_chart(sid, did, q, res.get("chart"))
        result_id = str(uuid.uuid4())
        entry = {
            "result_id": result_id, "dataset_id": did,
            "question": q[:500],
            "result": str(res.get("result") or "")[:12000],
            "code": str(res.get("code") or "")[:20000],
            "chart": chart_url, "created_at": int(time.time()),
            "guard_summary": res.get("guard_summary"),
            "inference": res.get("inference"),
        }
        _record_history(_session_state(sid), entry)
        dur_ms = int((_t.monotonic() - start) * 1000)
        yield "data: " + json.dumps({
            "step": "done", "progress": 100,
            "result": res.get("result"), "chart": chart_url,
            "code": res.get("code"),
            "methodology": res.get("methodology"),
            "guard_summary": res.get("guard_summary"),
            "inference": res.get("inference"),
            "dataset_id": did, "result_id": result_id,
            "duration_ms": dur_ms,
        }) + "\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/datasets/<did>/export", methods=["GET"])
def export_dataset_data(did):
    sid = _session_id()
    state = _session_state(sid)
    info = state["datasets"].get(did)
    if not info:
        return _json_error("not found", 404, "DATASET_NOT_FOUND")
    from io import StringIO
    buf = StringIO()
    info["df"].to_csv(buf, index=False)
    response = make_response(buf.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8-sig"
    fname = str(info.get("name", "data")).replace(" ", "_")
    response.headers["Content-Disposition"] = 'attachment; filename="' + fname + '_export.csv"'
    return response



@app.route("/upload/profile", methods=["GET"])
def upload_profile():
    """Upload-time automatic data exploration report."""
    sid = _session_id()
    did, info = _active_dataset(sid)
    if info is None:
        return jsonify({"error": "no data"})
    profile = auto_analyze.auto_profile(info["df"])
    return jsonify(profile)

def main():
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
