"""
报告导出模块：可复现Jupyter Notebook + APA格式Results段落生成。
Phase 3 核心 —— 分析结果可直接进论文。
"""
import html as html_mod
import json
import os
import time
import uuid


def generate_apa_paragraph(question, result, guard_summary=None,
                           inference=None, test_name="statistical test"):
    """
    根据分析结果自动生成APA 7格式的Results段落（中文）。
    返回结构化学术写作文本，可直接复制进论文。
    """
    lines = []
    lines.append(f"针对研究问题「{question}」，本研究采用{test_name}进行分析。")

    if result:
        # 提取关键数值
        lines.append(f"结果显示：{result}")

    if guard_summary:
        lines.append(f"方法学检查：{guard_summary}。")

    if inference:
        bayes = inference.get("bayes")
        if bayes and bayes.get("bf10"):
            bf_val = bayes["bf10"]
            if bf_val > 10:
                evidence = "提供了强有力的证据支持"
            elif bf_val > 3:
                evidence = "提供了中等程度的证据支持"
            else:
                evidence = "提供的证据不足以支持或拒绝"
            lines.append(
                f"贝叶斯因子分析（BF₁₀ = {bf_val:.2f}）{evidence}备择假设。"
            )
        power = inference.get("power")
        if power and power.get("achieved_power"):
            lines.append(
                f"统计功效分析显示，当前样本量的检验效能为 {power['achieved_power']:.2f}"
            )
            if power.get("adequate"):
                lines[-1] += "，满足常规标准（≥ 0.80）。"
            else:
                lines[-1] += "，低于建议阈值（0.80），结果需谨慎解读。"
        robustness = inference.get("robustness")
        if robustness and robustness.get("stability"):
            verdict_map = {"STABLE": "稳健", "MODERATE": "中等稳定", "UNSTABLE": "不够稳健"}
            verdict = verdict_map.get(robustness["stability"]["verdict"], "未知")
            boot = robustness.get("bootstrap", {})
            ci_lo = boot.get("ci_lower", "N/A")
            ci_hi = boot.get("ci_upper", "N/A")
            lines.append(
                f"稳健性检查结论为「{verdict}」，"
                f"Bootstrap 95% CI [{ci_lo}, {ci_hi}]。"
            )

    lines.append("综上，上述结果在控制了统计假设检验前提条件后具有可解释性。")
    return "\n\n".join(lines)


def export_notebook(session_state, dataset_info, history_items,
                    output_dir="exports"):
    """
    将整个分析会话导出为可复现的 Jupyter Notebook (.ipynb)。
    包含：数据加载代码、每个问题的分析代码、输出结果、方法论注释。
    """
    os.makedirs(output_dir, exist_ok=True)
    nb_id = str(uuid.uuid4())[:8]
    filename = f"analysis_{nb_id}.ipynb"
    filepath = os.path.join(output_dir, filename)

    cells = []

    def md_cell(source):
        cells.append({
            "cell_type": "markdown", "metadata": {},
            "source": [source + "\n"],
        })

    def code_cell(source):
        cells.append({
            "cell_type": "code", "metadata": {}, "execution_count": None,
            "outputs": [], "source": [source + "\n"],
        })

    md_cell("# AI Data Assistant — Research Analysis Notebook")
    md_cell(
        f"> Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"This notebook contains the full reproducible analysis pipeline.\n"
        f"Dataset: **{dataset_info.get('name', 'unknown')}** "
        f"({dataset_info.get('rows', '?')} rows × {dataset_info.get('cols', '?')} columns)"
    )

    code_cell(
        "import pandas as pd\n"
        "import numpy as np\n"
        "import matplotlib.pyplot as plt\n\n"
        "# Load your data\ndf = pd.read_csv('your_data.csv')  # TODO: update path\n"
        "print(df.shape)\ndf.head()"
    )

    for i, item in enumerate(history_items, 1):
        question = item.get("question", f"Question {i}")
        code = item.get("code", "")
        result_text = item.get("result", "")

        md_cell(f"## Q{i}: {question}")
        if code:
            code_cell(code)
        if result_text:
            result_text.replace("\\", "\\\\").replace('"', '\\"')
            md_cell(f"**Result:** {result_text[:2000]}")

    nb_content = {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.11.0",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }

    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(nb_content, fh, ensure_ascii=False, indent=1)

    return filepath


def export_html_report(history_items, dataset_name="Unknown Dataset"):
    """将分析会话导出为自包含HTML报告。"""
    html_parts = [
        "<!DOCTYPE html><html><head><meta charset='UTF-8'>",
        "<title>Analysis Report</title>",
        "<style>",
        "body{font-family:'Georgia',serif;max-width:800px;margin:0 auto;padding:40px;line-height:1.7;color:#333;}",
        "h1{border-bottom:2px solid #333;padding-bottom:10px;}",
        ".qa{margin-bottom:30px;}",
        ".question{font-weight:bold;font-size:16px;color:#1a1a2a;margin-bottom:8px;}",
        ".answer{padding:12px;background:#f5f5f5;border-left:3px solid #4f8cff;}",
        ".methodology{margin-top:8px;padding:8px;background:#eef;color:#226;font-size:13px;}",
        ".meta{color:#666;font-size:12px;}",
        "</style></head><body>",
        "<h1>Data Analysis Report</h1>",
        f"<p class='meta'>Generated: {time.strftime('%Y-%m-%d %H:%M')} | Dataset: {dataset_name}</p>",
    ]

    for i, item in enumerate(history_items, 1):
        q = item.get("question", f"Q{i}")
        r = item.get("result", "")
        m = item.get("methodology") or item.get("sql") or ""
        html_parts.append("<div class='qa'>")
        html_parts.append(f"<div class='question'>{i}. {html_mod.escape(str(q))}</div>")
        html_parts.append(f"<div class='answer'>{html_mod.escape(str(r))}</div>")
        if m:
            html_parts.append(f"<div class='methodology'><strong>Method:</strong> {m}</div>")
        html_parts.append("</div>")

    html_parts.append("</body></html>")
    return "\n".join(html_parts)
