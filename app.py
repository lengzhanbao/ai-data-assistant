"""
AI 数据分析助手 —— Flask Web 服务
上传 Excel/CSV → 自然语言提问 → LLM 生成 Pandas 代码 → 沙箱执行 → 文字结论 + 图表
"""
import os
import io
import uuid

from flask import (
    Flask, request, render_template, session, jsonify, send_file, url_for,
)
import pandas as pd

from analyzer import analyze, insight, to_sql

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "dev-secret-change-me")
app.config["df_store"] = {}

BASE = os.path.dirname(__file__)
UPLOAD = os.path.join(BASE, "uploads")
CHARTS = os.path.join(BASE, "charts")
os.makedirs(UPLOAD, exist_ok=True)
os.makedirs(CHARTS, exist_ok=True)

ALLOWED = {".csv", ".xlsx", ".xls"}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    """前端探测 LLM 是否配置好，未配置时给友好提示。"""
    import llm_client
    ok = bool(llm_client.API_KEY)
    return jsonify({"llm_ready": ok, "model": llm_client.MODEL,
                    "base": llm_client.BASE_URL,
                    "hint": None if ok else "未配置 LLM_API_KEY，请在环境变量设置 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL"})


@app.route("/upload", methods=["POST"])
def upload():
    sid = session.get("sid") or str(uuid.uuid4())
    session["sid"] = sid

    f = request.files.get("file")
    if not f:
        return jsonify({"error": "未收到文件"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED:
        return jsonify({"error": "仅支持 csv / xlsx / xls"}), 400

    path = os.path.join(UPLOAD, f"{sid}{ext}")
    f.save(path)
    df = pd.read_csv(path) if ext == ".csv" else pd.read_excel(path)
    app.config["df_store"][sid] = df

    return jsonify({
        "rows": int(df.shape[0]),
        "cols": int(df.shape[1]),
        "columns": [{"name": c, "dtype": str(t)} for c, t in df.dtypes.items()],
        "preview": df.head(5).fillna("").to_dict("records"),
    })


@app.route("/ask", methods=["POST"])
def ask():
    sid = session.get("sid")
    df = app.config["df_store"].get(sid)
    if df is None:
        return jsonify({"error": "请先上传数据"}), 400

    q = (request.json or {}).get("question", "").strip()
    if not q:
        return jsonify({"error": "问题为空"}), 400

    try:
        res = analyze(df, q)
    except Exception as e:
        return jsonify({"error": f"分析引擎错误：{e}"}), 500

    if not res["ok"]:
        return jsonify({"error": "分析失败：\n" + res["error"], "code": res.get("code")}), 500

    # SQL 对照（失败不阻塞主结果）
    sql = to_sql(df, q, res.get("code", ""))
    chart_url = _save_chart(sid, q, res.get("chart"))
    return jsonify({"result": res["result"], "chart": chart_url,
                    "code": res.get("code"), "sql": sql or None})


@app.route("/insights", methods=["POST"])
def insights():
    """自动洞察 / 异常下探：一键出 总览+异常+建议（对应小爱JD）。"""
    sid = session.get("sid")
    df = app.config["df_store"].get(sid)
    if df is None:
        return jsonify({"error": "请先上传数据"}), 400

    try:
        res = insight(df)
    except Exception as e:
        return jsonify({"error": f"分析引擎错误：{e}"}), 500

    if not res["ok"]:
        return jsonify({"error": "洞察失败：\n" + res["error"], "code": res.get("code")}), 500

    chart_url = _save_chart(sid, "__insight__", res.get("chart"))
    return jsonify({"result": res["result"], "chart": chart_url, "code": res.get("code")})


def _save_chart(sid, q, chart_bytes):
    if not chart_bytes:
        return None
    name = f"{sid}_{abs(hash(q))}.png"
    with open(os.path.join(CHARTS, name), "wb") as fh:
        fh.write(chart_bytes)
    return url_for("chart", name=name)


@app.route("/chart/<name>")
def chart(name):
    return send_file(os.path.join(CHARTS, name), mimetype="image/png")


def main():
    """Console entry: python -m app 或 ai-data-assistant"""
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)


if __name__ == "__main__":
    main()
