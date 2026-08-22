"""
分析引擎：把"自然语言问题 + 数据集"变成"LLM 生成代码 → 沙箱执行 → 结果/图表"。
"""
import json
import os as _os

import inference_engine
import stats_guard

if _os.getenv("LLM_API_KEY"):
    from llm_client import chat
else:
    try:
        from mock_llm import chat as _mock_chat
        _DEMO_MODE = True
    except ImportError:
        raise RuntimeError(
            "LLM_API_KEY not set. Set it in environment or .env file."
        ) from None

    def chat(system, user, temperature=0.2, timeout=60):
        return _mock_chat(system, user, temperature, timeout)
from sandbox import run_code

SYSTEM_PROMPT = """你是一个研究方法学助手（Research Methods Copilot）。用户会上传数据集并提问。
你会得到数据集结构信息和统计假设检查结果。请编写 Python 代码完成分析，严格遵守：
1. 可用库：pandas(pd)、numpy(np)、matplotlib(plt)、scipy(stats)、statsmodels(sm)、pingouin(pg)。
2. 数据集已作为变量 df 提供。不要读文件、不要 import os/sys/subprocess/socket。
3. 输出两个变量：
   - `result`：中文结论字符串，必须包含效应量(Cohen d / eta-squared / Cramer V / r)及其解释
   - `methodology`：中文方法论说明，含三部分：(a)为什么选这个方法 (b)假设检查结果 (c)结果如何解读
4. 如需图表用 fig = plt.figure()，不要 plt.show()。
5. 多重比较必须应用 Bonferroni 或 FDR 校正并注明。
6. 只输出代码，不要解释，不要 ``` 标记。"""

# 自动洞察/异常下探专用提示词（对应小爱JD「数据分析 / 异常下探」）
INSIGHT_PROMPT = """你是一个运营数据分析专家，擅长「异常下探」。用户给了一份数据集，你要自动完成：
1. 数据总览：规模、关键指标均值/中位数、Top 项。
2. 异常下探：主动找出异常点——明显偏离的数值（可用 z-score 或与均值对比）、空值、极端值、异常趋势，并尝试解释可能原因（数据层面）。
3. 运营建议：基于发现给出 2-3 条可落地的建议。
请编写一段 Python 代码完成上述分析，严格遵守：
- 使用 pandas（别名 pd）、numpy（别名 np）、matplotlib（别名 plt），数据集为变量 `df`。
- 把最终完整结论（含具体数字）赋值给 `result`（字符串，用中文，分「总览/异常/建议」三段）。
- 如需图表用 `fig`，不要 plt.show()，不要输出 ``` 标记。
- 只输出代码。"""

SQL_SYSTEM = """你是一个 SQL 专家。给你一个数据集表结构、一个用户问题、以及对应的 pandas 分析代码，
请翻译成等价的 SQL（SQLite/MySQL 兼容语法）。只输出 SQL 语句本身，不要解释，不要 ``` 标记。
如果该分析难以用 SQL 表达（如复杂绘图），输出等价的数据查询部分即可。"""


_MAX_DESCRIBE_COLS = 30
_MAX_CELL_CHARS = 80


def _truncate_cell(value) -> str:
    text = str(value)
    return text[:_MAX_CELL_CHARS] + "…" if len(text) > _MAX_CELL_CHARS else text


def describe_df(df) -> str:
    n_cols = len(df.columns)
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    describe_data = {}
    if len(numeric_cols) > _MAX_DESCRIBE_COLS:
        describe_data = df[numeric_cols[:_MAX_DESCRIBE_COLS]].describe().fillna("").to_dict()
    elif n_cols <= _MAX_DESCRIBE_COLS:
        describe_data = df.describe(include="all").fillna("").to_dict()
    else:
        describe_data = df.describe().fillna("").to_dict()

    head_records = []
    for row in df.head(3).to_dict("records"):
        head_records.append({str(k): _truncate_cell(v) for k, v in row.items()})

    info = {
        "shape": list(df.shape),
        "columns": [str(c) for c in df.columns],
        "dtypes": {str(c): str(t) for c, t in list(df.dtypes.items())[:_MAX_DESCRIBE_COLS]},
        "head": head_records,
        "describe": describe_data,
    }
    if n_cols > _MAX_DESCRIBE_COLS:
        info["note"] = f"共{n_cols}列，仅展示前{_MAX_DESCRIBE_COLS}列详情"
    return json.dumps(info, ensure_ascii=False, default=str)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def analyze(df, question: str, max_retry: int = 1, context: str = "") -> dict:
    """返回 {'ok','result','chart','error'}。chart 为 PNG bytes 或 None。"""
    return _run(df, question, SYSTEM_PROMPT, max_retry)


def insight(df, max_retry: int = 1) -> dict:
    """自动洞察/异常下探：不需要用户提问，直接产出 总览/异常/建议。"""
    return _run(df, "自动洞察", INSIGHT_PROMPT, max_retry)


def to_sql(df, question: str, code: str) -> str:
    """把 pandas 分析翻译成等价 SQL（面试对应『会 SQL 优先』）。失败返回空串。"""
    try:
        schema = describe_df(df)
        user_msg = (
            f"表结构：\n{schema}\n\n用户问题：{question}\n\n"
            f"对应的 pandas 代码：\n{code}\n\n请翻译成等价 SQL："
        )
        return _strip_fences(chat(SQL_SYSTEM, user_msg))
    except Exception:
        return ""


def _run(df, question: str, system_prompt: str, max_retry: int, context: str = "") -> dict:
    guard_result = stats_guard.full_guard_check(df, question)
    guard_prompt = stats_guard.guard_to_prompt(guard_result)
    schema = describe_df(df)
    (context + "\n\n" if context else "")
    user_msg = f"数据集结构：\n{schema}\n\n用户问题：{question}\n{guard_prompt}\n\n请只输出 Python 代码。"
    try:
        code = _strip_fences(chat(system_prompt, user_msg))
    except Exception:
        return {"ok": False, "result": None, "chart": None, "error": "模型代码生成失败", "code": ""}
    res = run_code(code, df)

    attempt = 0
    max_retry = max(0, min(int(max_retry), 2))
    while (not res["ok"]) and attempt < max_retry:
        error_text = str(res.get("error", "执行失败"))[:2000]
        fix_msg = (
            f"你刚才生成的代码执行报错：\n{error_text}\n\n原始代码：\n{code[:12000]}\n\n"
            f"请根据报错修正，只输出正确代码。"
        )
        try:
            code = _strip_fences(chat(system_prompt, fix_msg))
        except Exception:
            break
        res = run_code(code, df)
        attempt += 1

    res["code"] = code[:20000]
    res["guard_summary"] = guard_result.get("guard_summary", "")

    if res.get("ok"):
        try:
            numeric_cols = [v["column"] for v in guard_result.get("variable_types", [])
                           if str(v["type"]).startswith("numeric") or v["type"] == "ordinal"]
            cats = [v["column"] for v in guard_result.get("variable_types", [])
                    if v["type"] == "categorical" and v["n_unique"] == 2]
            inference_extra = {}
            if numeric_cols and len(df) >= 20:
                val_series = df[numeric_cols[0]].dropna()
                if len(val_series) >= 10:
                    inference_extra["power"] = inference_engine.power_analysis(
                        n=len(val_series), test_type="t_test")
                    inference_extra["robustness"] = inference_engine.robustness_check(
                        df, numeric_cols[0])
                if cats:
                    groups = df.groupby(cats[0])[numeric_cols[0]]
                    grp_data = [g.dropna().values for _, g in groups]
                    if len(grp_data) == 2 and all(len(g) >= 5 for g in grp_data):
                        bayes_result = inference_engine.bayes_alternative(grp_data[0], grp_data[1])
                        inference_extra["bayes"] = bayes_result
            res["inference"] = inference_extra
        except Exception:
            pass
    if not res.get("ok"):
        detail = res.get("error", "")
        # 提取最后一行有意义的错误信息
        lines = [ln.strip() for ln in str(detail).split("\n") if ln.strip()]
        short_err = lines[-1][:200] if lines else "未知错误"
        res["error"] = f"代码执行失败：{short_err}"
    return res
