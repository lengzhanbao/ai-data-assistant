"""
统计方法学守卫：在LLM生成代码之前，自动检测数据假设，推荐合适的统计方法。
这是 Research Methods Copilot 的核心差异化模块。
"""
import warnings

import numpy as np
from scipy import stats as sps


def _py(v):
    """Convert numpy scalar to Python native type."""
    if hasattr(v, "item"):
        return v.item()
    return v


def _clean_numeric(series):
    """Extract numeric values and remove NaN/Inf. Accepts Series or ndarray."""
    import pandas as pd
    if hasattr(series, "dropna"):
        series = series.dropna()
    arr = pd.to_numeric(pd.Series(series), errors="coerce").dropna().values
    arr = arr[np.isfinite(arr)]
    return arr


def check_normality(series) -> dict:
    """Shapiro-Wilk normality test. Uses DAgostino-Pearson for n>5000."""
    clean = _clean_numeric(series)
    n = len(clean)
    if n < 3:
        return {"test": None, "statistic": None, "p_value": None,
                "normal": False, "note": f"n={n} < 3, cannot test normality"}
    if len(set(clean)) <= 1:
        return {"test": None, "statistic": None, "p_value": None,
                "normal": False, "note": "constant data (variance=0)"}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if n > 5000:
                stat, p = sps.normaltest(clean)
                test_name = "DAgostino-Pearson"
            else:
                stat, p = sps.shapiro(clean)
                test_name = "Shapiro-Wilk"
    except Exception as exc:
        reason = str(exc)[:80] if exc else ""
        return {"test": None, "statistic": None, "p_value": None,
                "normal": False, "note": f"normality test failed: {reason}"}
    return {"test": test_name, "statistic": round(_py(stat), 4),
            "p_value": round(_py(p), 6), "normal": _py(p) > 0.05, "note": ""}


def check_variance_equality(group1=None, group2=None, groups=None) -> dict:
    """Levene variance equality test for 2+ groups."""
    arrays = [g for g in ([group1] + ([group2] if group2 is not None else []) +
             (groups if groups else [])) if g is not None]
    cleaned = [_clean_numeric(a) for a in arrays]
    cleaned = [a for a in cleaned if len(a) >= 3]
    if len(cleaned) < 2:
        return {"test": None, "statistic": None, "p_value": None,
                "var_equal": True, "note": "insufficient groups/samples, skipped"}
    variances = [np.var(a) for a in cleaned]
    if any(v == 0 for v in variances):
        return {"test": "Levene", "statistic": None, "p_value": None,
                "var_equal": False, "note": "at least one group has zero variance"}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            stat, p = sps.levene(*cleaned)
    except Exception:
        return {"test": None, "statistic": None, "p_value": None,
                "var_equal": True, "note": "levene failed, assuming equal"}
    return {"test": "Levene", "statistic": round(_py(stat), 4),
            "p_value": round(_py(p), 6), "var_equal": _py(p) > 0.05, "note": ""}


def check_sample_size(n: int, test_type: str = "t_test") -> dict:
    """Sample size adequacy check."""
    minimums = {"t_test": 30, "mann_whitney": 20, "anova": 15,
                "chi_square": 25, "correlation": 10, "regression": 10}
    min_n = minimums.get(test_type, 30)
    adequate = bool(n >= min_n)
    note = ""
    if not adequate:
        note = (f"current n={n}, recommend at least {min_n}. "
                f"Interpret results cautiously; consider Bootstrap CI.")
    return {"adequate": adequate, "n": n, "minimum_recommended": min_n, "note": note}


def detect_variable_types(df) -> list:
    """Classify each column: numeric_continuous/numeric_discrete/categorical/ordinal/datetime/text/identifier."""
    result = []
    for col in df.columns:
        series = df[col].dropna()
        n_unique = series.nunique()
        dtype = str(df[col].dtype)
        entry = {"column": str(col), "dtype": dtype, "n_unique": int(n_unique)}
        if "datetime" in dtype or "timestamp" in dtype:
            entry["type"] = "datetime"
        elif dtype in ("object", "string", "str") or "category" in dtype:
            if n_unique <= 20:
                entry["type"] = "categorical"
            elif n_unique >= len(series) * 0.9:
                entry["type"] = "identifier"
            else:
                entry["type"] = "text"
        elif "int" in dtype:
            if n_unique <= 10:
                entry["type"] = "ordinal"
            else:
                entry["type"] = "numeric_discrete"
        elif "float" in dtype:
            entry["type"] = "numeric_continuous"
        elif "bool" in dtype:
            entry["type"] = "categorical"
        else:
            entry["type"] = "unknown"
        result.append(entry)
    return result


def recommend_method(variable_types: list, question_hint: str = "") -> dict:
    """Recommend statistical method based on variable types and question keywords."""
    nums = [v for v in variable_types if str(v.get("type", "")).startswith("numeric")]
    cats = [v for v in variable_types if v.get("type") == "categorical"]
    dates = [v for v in variable_types if v.get("type") == "datetime"]
    hint_lower = question_hint.lower() if question_hint else ""

    if any(kw in hint_lower for kw in ["相关", "corr", "关系", "关联"]):
        method = "pearson_or_spearman"
        rationale = ("连续变量相关性。正态满足用Pearson r，否则Spearman rho。"
                     "报告效应量r/rho及95% CI。")
    elif any(kw in hint_lower for kw in ["差异", "比较", "对比", "diff", "compare"]) and cats and nums:
        cat_levels = cats[0].get("n_unique", 2)
        if cat_levels == 2:
            method = "independent_t_test_or_mann_whitney"
            rationale = ("两组独立样本比较。正态+方差齐用t检验；方差不齐用Welch t；"
                         "非正态用Mann-Whitney U。必须报告效应量(Cohen d或rank-biserial r)及95%CI。")
        else:
            method = "one_way_anova_or_kruskal_wallis"
            rationale = (f"{cat_levels}组比较。参数条件满足用ANOVA+Tukey HSD；"
                         "否则Kruskal-Wallis+Dunn(Bonferroni校正)。必须报告eta-squared效应量。")
    elif dates and nums:
        method = "time_series_eda"
        rationale = ("检测到时间列+数值列。建议STL趋势分解、ADF平稳性检验、ACF/PACF图。"
                     "预测从简单指数平滑开始。")
    elif any(kw in hint_lower for kw in ["预测", "predict", "回归", "regression"]) and nums:
        method = "regression_with_diagnostics"
        rationale = ("回归前检查VIF共线性、残差正态性、异方差(Breusch-Pagan)。"
                     "报告R2adj、AIC、BIC、标准化beta和95%CI。")
    else:
        method = "descriptive_eda"
        rationale = ("无法明确推断意图，输出描述性统计+分布可视化。"
                     "如需推断分析请指定变量和比较方式。")

    return {"method": method, "rationale": rationale}


def full_guard_check(df, question: str = "") -> dict:
    """Complete assumption-checking pipeline."""
    var_types = detect_variable_types(df)
    rec = recommend_method(var_types, question)
    numeric_cols = [v["column"] for v in var_types if str(v["type"]).startswith("numeric")]

    normality_results = {}
    for col in numeric_cols[:10]:
        normality_results[col] = check_normality(df[col])

    all_normal = all(r.get("normal", False) for r in normality_results.values()) if normality_results else False
    total_n = len(df)
    sample_ok = check_sample_size(total_n, rec["method"])

    variance_result = None
    cats = [v for v in var_types if v["type"] == "categorical" and v["n_unique"] >= 2]
    if cats and numeric_cols and "t_test" in rec["method"]:
        groups = [g.dropna().values for _, g in df.groupby(cats[0]["column"])[numeric_cols[0]]]
        if len(groups) == 2:
            variance_result = check_variance_equality(groups[0], groups[1])

    return {
        "variable_types": var_types,
        "recommendation": rec,
        "assumptions": {
            "normality": normality_results,
            "all_numeric_normal": bool(all_normal),
            "variance_equality": variance_result,
            "sample_size": sample_ok,
        },
        "guard_summary": _build_summary(rec, all_normal, variance_result, sample_ok),
    }


def guard_to_prompt(guard_result: dict) -> str:
    """Format assumption-checking results as LLM-readable prompt snippet."""
    lines = ["\n## Statistical Guard (auto-detected, strictly follow)"]
    rec = guard_result.get("recommendation", {})
    lines.append(f"- Recommended method: {rec.get('method', 'unknown')}")
    lines.append(f"- Rationale: {rec.get('rationale', '')}")
    assumptions = guard_result.get("assumptions", {})
    lines.append(f"- Numeric columns normality: {'SATISFIED' if assumptions.get('all_numeric_normal') else 'NOT SATISFIED'}")
    veq = assumptions.get("variance_equality")
    if veq:
        status = "SATISFIED" if veq.get("var_equal") else "NOT SATISFIED"
        lines.append(f"- Variance equality (Levene): {status} (p={veq.get('p_value')})")
    ss = assumptions.get("sample_size", {})
    lines.append(f"- Sample size: n={ss.get('n', 'unknown')}, {'adequate' if ss.get('adequate') else 'INSUFFICIENT'}")
    if ss.get("note"):
        lines.append(f"  WARNING: {ss['note']}")
    lines.append("""
- MANDATORY requirements:
  1. If normality NOT satisfied, use non-parametric methods (Mann-Whitney U / Kruskal-Wallis / Spearman)
  2. `result` variable MUST include effect size (Cohen's d / eta-squared / Cramer V / r) with interpretation
  3. For multiple comparisons, apply Bonferroni or FDR correction and state so in conclusions
  4. Set `methodology` variable to a Chinese methodology paragraph explaining: (a) why this method was chosen (b) assumption check results (c) how to interpret results
""")
    return "\n".join(lines)


def _build_summary(rec, all_normal, variance_result, sample_ok) -> str:
    parts = []
    parts.append(f"Recommended: {rec.get('method', 'unknown')}")
    if not all_normal:
        parts.append("WARNING normality not satisfied -> non-parametric recommended")
    if variance_result and not variance_result.get("var_equal", True):
        parts.append("WARNING unequal variance -> Welch t or Mann-Whitney U")
    if not sample_ok.get("adequate", True):
        parts.append(f"WARNING insufficient sample (n={sample_ok.get('n')})")
    return "; ".join(parts) if parts else "All assumption checks passed"