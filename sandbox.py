"""
安全沙箱：用独立子进程（subprocess）执行 LLM 生成的 Pandas 代码。
安全措施：
  1. 独立 Python 进程，原生 timeout 超时即 kill，互不污染主进程。
  2. 运行脚本（runner.py）限制导入白名单，禁止 os / subprocess / socket 等危险模块。
  3. 限制内置函数（只允许安全子集）。
  4. 数据集以变量 df 注入（通过临时 pickle 传递），代码无法读取磁盘其他文件。
  5. AST 预检：执行前阻断 import / 动态执行 / 文件网络访问 / 危险 dunder；允许受控 Pandas/NumPy/Matplotlib 分析 API。

⚠️ 本沙箱是「本地单用户演示用」。公网部署必须再叠加：
   - 容器/操作系统级隔离（Docker / gVisor / Firecracker）
   - 非 root 用户、只读文件系统、禁止网络
   - CPU / 内存 / PID 限额、seccomp / AppArmor
"""
import ast
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
    "isinstance": isinstance, "format": format, "repr": repr,
    "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
    "KeyError": KeyError, "IndexError": IndexError, "ZeroDivisionError": ZeroDivisionError,
    "FileNotFoundError": FileNotFoundError,
}

_MAX_CODE_LENGTH = 20000
_MAX_AST_NODES = 4000
_MAX_STRING_LITERAL = 2000
_MAX_RESULT_CHARS = 12000
_MAX_CHART_BYTES = 5 * 1024 * 1024

_DISALLOWED_NODES = (
    ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef,
    ast.ClassDef, ast.Lambda, ast.Try, ast.Raise, ast.Yield,
    ast.YieldFrom, ast.Delete, ast.Global, ast.Nonlocal,
    ast.GeneratorExp, ast.ListComp, ast.SetComp, ast.DictComp,
    ast.With, ast.AsyncWith, ast.Await, ast.AsyncFor, ast.NamedExpr,
)
_DISALLOWED_NAMES = {
    "__builtins__", "__import__", "eval", "exec", "compile", "open",
    "input", "globals", "locals", "vars", "os", "sys", "subprocess",
    "socket", "requests", "urllib", "pathlib",
}
_SAFE_CALL_NAMES = {
    "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float",
    "format", "int", "isinstance", "len", "list", "map", "max", "min",
    "print", "range", "repr", "round", "set", "sorted", "str", "sum",
    "tuple", "zip",
}
_SAFE_ATTRIBUTE_NAMES = {
    "loc", "iloc", "columns", "dtypes", "shape", "head", "tail",
    "sort_values", "sort_index", "groupby", "agg", "aggregate", "mean",
    "median", "std", "min", "max", "sum", "count", "idxmax", "idxmin",
    "dropna", "fillna", "astype", "value_counts", "nunique", "unique",
    "reset_index", "set_index", "pivot_table", "corr", "cov", "quantile",
    "describe", "plot", "bar", "line", "scatter", "hist", "box", "pie",
    "dt", "str", "year", "month", "day", "figure", "gca", "subplots",
    "title", "xlabel", "ylabel", "xticks", "yticks", "legend", "grid",
    "tight_layout", "to_datetime", "isna", "isnull", "isnan", "where",
    "array", "arange", "percentile", "corrcoef", "DataFrame", "Series",
}


def _preflight(code: str) -> None:
    """执行前 AST 预检。

    允许常见 Pandas/NumPy/Matplotlib 数据分析调用；阻断文件、网络、动态执行、
    dunder、任意方法调用和任意属性访问。此检查不是 OS 级安全边界。
    """
    if not isinstance(code, str) or not code.strip():
        raise ValueError("代码不能为空")
    if len(code) > _MAX_CODE_LENGTH:
        raise ValueError("代码过长")
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError) as exc:
        raise ValueError("代码语法无效") from exc
    if sum(1 for _ in ast.walk(tree)) > _MAX_AST_NODES:
        raise ValueError("代码过于复杂")
    for node in ast.walk(tree):
        if isinstance(node, _DISALLOWED_NODES):
            raise ValueError(f"代码包含禁止结构：{type(node).__name__}")
        if isinstance(node, ast.Name) and node.id in _DISALLOWED_NAMES:
            raise ValueError(f"代码包含禁止名称：{node.id}")
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str) and len(node.value) > _MAX_STRING_LITERAL:
                raise ValueError("字符串常量过长")
            if isinstance(node.value, int) and node.value.bit_length() > 128:
                raise ValueError("整数常量过大")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") or node.attr not in _SAFE_ATTRIBUTE_NAMES:
                raise ValueError(f"代码属性不在允许列表：{node.attr}")
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                if func.id not in _SAFE_CALL_NAMES:
                    raise ValueError(f"代码调用不在允许列表：{func.id}")
            elif isinstance(func, ast.Attribute):
                if func.attr.startswith("__") or func.attr not in _SAFE_ATTRIBUTE_NAMES:
                    raise ValueError(f"代码方法不在允许列表：{func.attr}")
            else:
                raise ValueError("代码调用目标不受支持")

_RUNNER = os.path.join(os.path.dirname(__file__), "runner.py")


def run_code(code: str, df, timeout: int = 20):
    """执行代码，返回 {'ok','result','chart','error'}。chart 为 PNG bytes 或 None。"""
    try:
        _preflight(code)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "result": None, "chart": None}

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
        if d.get("result") is not None:
            d["result"] = str(d["result"])[:_MAX_RESULT_CHARS]
        if d.get("chart"):
            try:
                d["chart"] = base64.b64decode(d["chart"], validate=True)
            except (ValueError, TypeError):
                return {"ok": False, "error": "图表数据无效", "result": None, "chart": None}
            if len(d["chart"]) > _MAX_CHART_BYTES:
                return {"ok": False, "error": "图表过大", "result": None, "chart": None}
        return d
    finally:
        shutil.rmtree(tmp, ignore_errors=True)  # 清理临时文件，防磁盘泄漏
