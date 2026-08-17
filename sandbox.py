"""
安全沙箱：用独立子进程（subprocess）执行 LLM 生成的 Pandas 代码。
安全措施：
  1. 独立 Python 进程，原生 timeout 超时即 kill，互不污染主进程。
  2. 运行脚本（runner.py）限制导入白名单，禁止 os / subprocess / socket 等危险模块。
  3. 限制内置函数（只允许安全子集）。
  4. 数据集以变量 df 注入（通过临时 pickle 传递），代码无法读取磁盘其他文件。
"""
import os
import sys
import json
import base64
import shutil
import tempfile
import subprocess

# 安全策略单一事实来源：runner.py 从本模块导入，避免双份维护
ALLOWED_IMPORTS = {
    "pandas", "numpy", "matplotlib", "plotly", "sklearn", "scipy",
    "math", "json", "datetime", "re", "collections", "statistics",
}

SAFE_BUILTINS = {
    "len": len, "range": range, "enumerate": enumerate, "zip": zip,
    "sorted": sorted, "list": list, "dict": dict, "set": set, "tuple": tuple,
    "sum": sum, "min": min, "max": max, "abs": abs, "round": round,
    "int": int, "float": float, "str": str, "bool": bool, "print": print,
    "map": map, "filter": filter, "any": any, "all": all,
    "isinstance": isinstance, "type": type, "format": format, "repr": repr,
    "getattr": getattr, "hasattr": hasattr,
    "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
    "KeyError": KeyError, "IndexError": IndexError, "ZeroDivisionError": ZeroDivisionError,
    "FileNotFoundError": FileNotFoundError,
}

_RUNNER = os.path.join(os.path.dirname(__file__), "runner.py")


def run_code(code: str, df, timeout: int = 20):
    """执行代码，返回 {'ok','result','chart','error'}。chart 为 PNG bytes 或 None。"""
    tmp = tempfile.mkdtemp(prefix="sandbox_")
    dfpath = os.path.join(tmp, "df.pkl")
    codepath = os.path.join(tmp, "code.py")
    outpath = os.path.join(tmp, "out.json")

    import pandas as pd
    try:
        df.to_pickle(dfpath)
        with open(codepath, "w", encoding="utf-8") as f:
            f.write(code)

        try:
            proc = subprocess.run(
                [sys.executable, _RUNNER, dfpath, outpath, codepath],
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "error": f"执行超时（>{timeout}s），已终止。请让代码更高效，或只取需要的列。",
                "result": None,
                "chart": None,
            }

        if not os.path.exists(outpath):
            err = (proc.stderr or proc.stdout or "子进程无输出").strip()
            return {"ok": False, "error": err, "result": None, "chart": None}

        with open(outpath, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("chart"):
            d["chart"] = base64.b64decode(d["chart"])
        return d
    finally:
        shutil.rmtree(tmp, ignore_errors=True)  # 清理临时文件，防磁盘泄漏
