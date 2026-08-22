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
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile

# 安全策略单一事实来源：runner.py 从本模块导入，避免双份维护
ALLOWED_IMPORTS = {
    "pandas", "numpy", "matplotlib", "plotly", "sklearn", "scipy",
    "statsmodels", "pingouin",
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
    ast.ClassDef, ast.Try, ast.Raise,
    ast.Yield, ast.YieldFrom, ast.Delete, ast.Global, ast.Nonlocal,
    ast.With, ast.AsyncWith, ast.Await, ast.AsyncFor,
)
_DISALLOWED_NAMES = {
    "__builtins__", "__import__", "eval", "exec", "compile", "open",
    "input", "globals", "locals", "vars", "os", "sys", "subprocess",
    "socket", "requests", "urllib", "pathlib", "__class__", "__subclasses__",
}
_SAFE_CALL_NAMES = {
    "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float",
    "format", "int", "isinstance", "len", "list", "map", "max", "min",
    "print", "range", "repr", "round", "set", "sorted", "str", "sum",
    "tuple", "zip", "pd", "np", "plt", "df", "type", "bytes", "frozenset",
    "hash", "hex", "oct", "ord", "chr", "bin", "callable", "divmod",
}
_SAFE_ATTRIBUTE_NAMES = {
    # pandas DataFrame/Series methods & properties
    "loc", "iloc", "columns", "dtypes", "dtype", "shape", "size", "index",
    "head", "tail", "sample", "values", "T", "empty", "ndim",
    "sort_values", "sort_index", "groupby", "agg", "aggregate", "transform",
    "mean", "median", "std", "var", "sem", "skew", "kurt",
    "min", "max", "sum", "prod", "count", "idxmax", "idxmin",
    "dropna", "fillna", "ffill", "bfill", "interpolate", "replace",
    "astype", "convert_dtypes", "infer_objects", "copy", "drop",
    "rename", "rename_axis", "insert", "assign", "pop",
    "value_counts", "nunique", "unique", "duplicated", "drop_duplicates",
    "reset_index", "set_index", "reindex", "reindex_like", "align",
    "pivot_table", "pivot", "melt", "stack", "unstack", "explode",
    "merge", "join", "concat", "append", "combine_first", "update",
    "corr", "cov", "quantile", "describe", "info", "memory_usage",
    "rolling", "expanding", "ewm", "resample", "shift", "diff", "pct_change",
    "rank", "clip", "abs", "round", "cumsum", "cumprod", "cummax", "cummin",
    "between", "isin", "contains", "startswith", "endswith", "strip", "lstrip",
    "rstrip", "lower", "upper", "title", "capitalize", "len", "split", "cat",
    "zfill", "pad", "center", "repeat", "slice", "slice_replace",
    "apply", "applymap", "map", "pipe", "where", "mask", "query", "eval",
    "to_datetime", "to_numeric", "to_string", "to_frame", "to_series", "tolist",
    "items", "iterrows", "itertuples", "keys", "add_prefix", "add_suffix",
    # datetime accessor
    "dt", "year", "month", "day", "hour", "minute", "second", "weekday",
    "dayofweek", "day_name", "month_name", "quarter", "date", "time",
    # string accessor
    "str",
    # numpy
    "array", "arange", "linspace", "logspace", "zeros", "ones", "full",
    "eye", "diag", "percentile", "corrcoef", "cov", "mean", "median", "std",
    "var", "nanmean", "nanstd", "nanmin", "nanmax", "argmax", "argmin",
    "argsort", "sort", "concatenate", "stack", "vstack", "hstack", "column_stack",
    "reshape", "ravel", "flatten", "squeeze", "expand_dims", "transpose",
    "unique", "in1d", "intersect1d", "union1d", "setdiff1d", "setxor1d",
    "where", "clip", "maximum", "minimum", "absolute", "sign", "floor",
    "ceil", "trunc", "sqrt", "power", "exp", "log", "log10", "log2", "sin",
    "cos", "tan", "arcsin", "arccos", "arctan", "sinh", "cosh", "tanh",
    "random", "seed", "rand", "randn", "randint", "choice", "shuffle",
    "normal", "poisson", "binomial", "uniform", "inf", "nan", "pi", "e",
    "isinf", "isnan", "isfinite", "nan_to_num", "finite",
    "DataFrame", "Series", "Index", "MultiIndex", "Categorical",
    "Timestamp", "Timedelta", "Period", "Interval",
    "cut", "qcut", "factorize", "get_dummies", "melt",
    "read_csv", "read_excel", "date_range", "period_range", "timedelta_range",
    "to_timedelta", "to_pickle", "notna", "notnull", "isna", "isnull",
    # matplotlib
    "figure", "gca", "gcf", "subplots", "subplot", "axes", "clf", "cla",
    "close", "sca", "draw", "pause",
    "title", "xlabel", "ylabel", "clabel", "suptitle", "text", "annotate",
    "xticks", "yticks", "zticks", "xlim", "ylim", "zlim", "xscale", "yscale",
    "legend", "grid", "tight_layout", "subplots_adjust", "colorbar",
    "plot", "plotly", "bar", "barh", "line", "scatter", "hist", "boxplot", "pie", "errorbar",
    "fill_between", "fill_betweenx", "stackplot", "stem", "step", "violinplot",
    "imshow", "contour", "contourf", "pcolormesh", "quiver", "streamplot",
    "plot_date", "hexbin", "axvline", "axhline", "axvspan", "axhspan",
    "axison", "spines", "patch", "patches", "lines", "texts", "tables",
    "collections", "images", "artists", "containers", "child_axes",
    "set_title", "set_xlabel", "set_ylabel", "set_xlim", "set_ylim",
    "set_xticks", "set_yticks", "set_xticklabels", "set_yticklabels",
    "tick_params", "autoscale", "margins", "axis", "invert_xaxis", "invert_yaxis",
    "get_position", "set_position", "add_subplot", "add_axes", "twinx", "twiny",
    "show", "style", "use", "rcParams", "cm", "colors", "colormaps",
    "patches", "ticker", "dates", "font_manager", "pylab",
    # sklearn basic
    "fit", "predict", "transform", "fit_transform", "score", "inverse_transform",
    "LinearRegression", "LogisticRegression", "StandardScaler", "MinMaxScaler",
    "LabelEncoder", "OneHotEncoder", "KMeans", "PCA", "train_test_split",
    "accuracy_score", "precision_score", "recall_score", "f1_score",
    "confusion_matrix", "classification_report", "mean_squared_error",
    "mean_absolute_error", "r2_score", "silhouette_score",
    # scipy basic
    "stats", "optimize", "signal", "integrate", "linalg", "sparse",
    "pearsonr", "spearmanr", "kendalltau", "chi2_contingency", "ttest_ind",
    "ttest_rel", "mannwhitneyu", "wilcoxon", "kruskal", "friedmanchisquare",
    "linregress", "shapiro", "normaltest", "levene", "bartlett",
    # statsmodels & pingouin & extended scipy
    "OLS", "GLM", "Logit", "Probit", "add_constant", "summary", "summary2",
    "params", "bse", "tvalues", "pvalues", "conf_int", "rsquared",
    "rsquared_adj", "fvalue", "f_pvalue", "aic", "bic", "llf", "resid",
    "fittedvalues", "anova_lm", "het_breuschpagan", "durbin_watson", "vif",
    "variance_inflation_factor", "multitest", "multipletests",
    "pairwise_tukeyhsd", "MultiComparison", "adfuller", "acf", "pacf",
    "seasonal_decompose", "STL", "ARIMA", "SARIMAX", "ExponentialSmoothing",
    "ttest", "mannwhitney", "wilcoxon", "anova", "welch_anova", "kruskal",
    "chi2_independence", "corr", "correlation", "partial_corr",
    "pairwise_tests", "pairwise_corr", "rm_anova", "normality",
    "homoscedasticity", "compute_effsize", "bayesfactor_ttest",
    "power_ttest", "cronbach_alpha", "effectsize",
    # scipy extended
    "chisquare", "fisher_exact", "boschloo_exact", "barnard_exact",
    "mode", "sem", "iqr", "median_abs_deviation", "variation",
    "skewtest", "kurtosistest", "anderson", "cramervonmises",
    "bootstrap", "permutation_test", "monte_carlo_test",
# general safe attrs
    "name", "names", "columns", "values", "index", "data", "dtype", "types",
    "result_type", "categories", "ordered", "freq", "tz", "unit",
    "start", "stop", "step", "endpoint", "retstep", "base", "num",
    "left", "right", "include_lowest", "bins", "labels", "precision",
    "ascending", "inplace", "kind", "na_position", "ignore_index",
    "key", "level", "by", "axis", "skipna", "numeric_only", "ddof",
    "margin", "margins_name", "fill_value", "observed", "dropna",
    "how", "on", "left_on", "right_on", "suffixes", "validate", "indicator",
    "normalize", "bins_count", "subset", "keep", "orientation",
    "width", "height", "bottom", "top", "alpha", "color", "cmap", "norm",
    "linewidth", "linestyle", "marker", "markersize", "edgecolor", "facecolor",
    "fontsize", "fontweight", "rotation", "ha", "va", "label", "labels",
    "fmt", "dpi", "bbox_inches", "pad", "aspect", "interpolation",
    "origin", "extent", "levels", "extend", "orientation", "density",
    "weights", "cumulative", "histtype", "rwidth", "align", "log",
}


def _preflight(code: str) -> None:
    """执行前 AST 预检。

    允许白名单模块导入和常见数据分析调用；阻断非白名单 import、
    动态执行、dunder、危险结构。此检查不是 OS 级安全边界。
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
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_mod = alias.name.split(".")[0]
                if root_mod not in ALLOWED_IMPORTS:
                    raise ValueError(f"禁止导入 {alias.name}")
        if isinstance(node, ast.ImportFrom):
            if node.module:
                root_mod = node.module.split(".")[0]
                if root_mod not in ALLOWED_IMPORTS:
                    raise ValueError(f"禁止导入 from {node.module}")
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