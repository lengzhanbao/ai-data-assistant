"""
分析引擎：把"自然语言问题 + 数据集"变成"LLM 生成代码 → 沙箱执行 → 结果/图表"。
"""
import json

from llm_client import chat
from sandbox import run_code

SYSTEM_PROMPT = """你是一个数据分析助手。用户会上传一份数据集并提问。
你会得到数据集的结构信息（列名、类型、前几行、统计描述）。
请编写一段 Python 代码来回答用户的问题，严格遵守：
1. 使用 pandas（别名 pd）、numpy（别名 np）、matplotlib（别名 plt）。
2. 数据集已作为变量 `df` 提供，不要重新读取任何文件，不要 import 文件相关模块。
3. 把文字结论赋值给变量 `result`（字符串）。如需图表，用 `fig = plt.figure()` 或直接在 `plt` 上绘图，最后不要调用 plt.show()。
4. 只输出代码本身，不要解释，不要使用 ``` 标记。
5. 结论要具体，给出真实数值（如"完播率最高的是《xxx》，达 62.3%"），用中文表达。
6. 如果问题需要分组/排序/聚合，用 pandas 完成；图表标题用中文。"""

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


def describe_df(df) -> str:
    info = {
        "shape": list(df.shape),
        "columns": list(df.columns),
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
        "head": df.head(5).fillna("").to_dict("records"),
        "describe": df.describe(include="all").fillna("").to_dict(),
    }
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


def analyze(df, question: str, max_retry: int = 1) -> dict:
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


def _run(df, question: str, system_prompt: str, max_retry: int) -> dict:
    schema = describe_df(df)
    user_msg = f"数据集结构：\n{schema}\n\n用户问题：{question}\n\n请只输出 Python 代码。"
    code = _strip_fences(chat(system_prompt, user_msg))
    res = run_code(code, df)

    attempt = 0
    while (not res["ok"]) and attempt < max_retry:
        fix_msg = (
            f"你刚才生成的代码执行报错：\n{res['error']}\n\n原始代码：\n{code}\n\n"
            f"请根据报错修正，只输出正确代码。"
        )
        code = _strip_fences(chat(system_prompt, fix_msg))
        res = run_code(code, df)
        attempt += 1

    res["code"] = code  # 供调试/展示
    return res
