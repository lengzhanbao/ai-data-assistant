"""
沙箱子进程运行脚本（由 sandbox.py 调用，不要手动运行）。
参数：argv[1]=df.pkl  argv[2]=out.json  argv[3]=code.py
"""
import sys
import io
import json
import base64
import contextlib

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

# 安全策略与主进程 sandbox.py 共享（单一事实来源）
from sandbox import ALLOWED_IMPORTS as ALLOWED, SAFE_BUILTINS as SAFE

# 中文字体：优先 Windows 常见字体，找不到再退回默认（避免图内中文乱码）
_CJK_FONTS = ["Microsoft YaHei", "SimHei", "SimSun", "Noto Sans CJK SC", "PingFang SC"]
_available = {f.name for f in font_manager.fontManager.ttflist}
for _f in _CJK_FONTS:
    if _f in _available:
        plt.rcParams["font.sans-serif"] = [_f, "DejaVu Sans"]
        break
plt.rcParams["axes.unicode_minus"] = False


def _guard(name, *a, **k):
    if name.split(".")[0] not in ALLOWED:
        raise ImportError(f"禁止导入 {name}（沙箱仅允许 {sorted(ALLOWED)}）")
    return __import__(name, *a, **k)


def main():
    dfpath, outpath, codepath = sys.argv[1], sys.argv[2], sys.argv[3]
    df = pd.read_pickle(dfpath)
    code = open(codepath, encoding="utf-8").read()

    plt.close("all")
    ns = {
        "__builtins__": SAFE,
        "pd": pd, "np": np, "plt": plt, "df": df,
        "__import__": _guard,
    }
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        exec(code, ns)

    result = ns.get("result", stdout.getvalue().strip())
    if not isinstance(result, str):
        result = str(result)

    chart = None
    if plt.get_fignums():
        fig = ns.get("fig") or plt.gcf()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        buf.seek(0)
        chart = base64.b64encode(buf.read()).decode()

    json.dump({"ok": True, "result": result, "chart": chart}, open(outpath, "w"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        json.dump({"ok": False, "error": traceback.format_exc(), "result": None, "chart": None},
                  open(sys.argv[2], "w"))
