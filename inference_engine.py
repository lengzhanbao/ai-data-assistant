"""
推断引擎（inference_engine）：贝叶斯替代、统计功效、稳健性检查、回归诊断、因果推断入门。
Phase 2 核心模块 —— 从"跑一个检验"升级到"完整推断报告"。
"""

import numpy as np
import pandas as pd
from scipy import stats as sps

try:
    import pingouin as pg
    HAS_PINGOUIN = True
except ImportError:
    HAS_PINGOUIN = False

try:
    import statsmodels.api as sm_api
    from statsmodels.stats.diagnostic import het_breuschpagan
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    from statsmodels.stats.power import FTestAnovaPower, TTestIndPower
    from statsmodels.stats.stattools import durbin_watson as dw_stat
    HAS_STATSMODELS = True
except ImportError:
    HAS_STATSMODELS = False


# ── 贝叶斯替代方案 ──────────────────────────────────────────────────

def bayes_alternative(group1, group2=None, test_type="t_test", paired=False):
    """
    对频率派检验给出贝叶斯因子替代方案。
    返回 {'bf10': float, 'interpretation': str, 'posterior_plot_hint': str}
    BF10 > 1 支持H1，< 1 支持H0。BF10 > 10 = 强证据。
    """
    result = {"bf10": None, "interpretation": "", "note": ""}
    if not HAS_PINGOUIN:
        result["note"] = "pingouin未安装，跳过贝叶斯分析"
        return result

    try:
        g1 = pd.Series(group1).dropna()
        if group2 is not None:
            g2 = pd.Series(group2).dropna()
        else:
            g2 = None

        if test_type == "t_test" and g2 is not None:
            t_stat, _ = sps.ttest_ind(g1.values, g2.values)
            bf = pg.bayesfactor_ttest(t=t_stat, nx=len(g1), ny=len(g2),
                paired=paired, alternative="two-sided", r=0.707)
            result["bf10"] = round(_py(bf), 4)
        elif test_type == "t_test":
            t_stat, _ = sps.ttest_1samp(g1.values, 0)
            bf = pg.bayesfactor_ttest(t=t_stat, nx=len(g1),
                paired=paired, alternative="two-sided", r=0.707)
            result["bf10"] = round(_py(bf), 4)
            result["bf10"] = round(float(bf), 4)
    except Exception as exc:
        result["note"] = f"贝叶斯因子计算失败: {str(exc)[:80]}"
        return result

    bf_val = result.get("bf10")
    if bf_val is not None:
        if bf_val > 100:
            result["interpretation"] = f"BF10={bf_val:.1f}，极强证据支持H1"
        elif bf_val > 30:
            result["interpretation"] = f"BF10={bf_val:.1f}，非常强证据支持H1"
        elif bf_val > 10:
            result["interpretation"] = f"BF10={bf_val:.1f}，强证据支持H1"
        elif bf_val > 3:
            result["interpretation"] = f"BF10={bf_val:.1f}，中等证据支持H1"
        elif bf_val > 1:
            result["interpretation"] = f"BF10={bf_val:.1f}，弱证据支持H1"
        elif bf_val > 1/3:
            result["interpretation"] = f"BF10={bf_val:.3f}，证据不足，无法判断"
        elif bf_val > 1/10:
            result["interpretation"] = f"BF10={bf_val:.3f}，中等证据支持H0"
        else:
            result["interpretation"] = f"BF10={bf_val:.4f}，强证据支持H0"
    return result


# ── 统计功效分析 ────────────────────────────────────────────────────

def power_analysis(n=None, effect_size=None, alpha=0.05,
                   power=0.80, test_type="t_test"):
    """
    反向计算功效：给定任意两个参数，求第三个。
    - 给 n 和 effect_size → 求 achieved power
    - 给 n 和 power → 求最小可检测效应量 (MDE)
    - 给 effect_size 和 power → 求所需样本量
    """
    result = {"test_type": test_type, "alpha": alpha, "requested_power": power}
    if not HAS_STATSMODELS:
        result["note"] = "statsmodels未安装"
        return result

    try:
        if test_type in ("t_test", "t_test_ind", "mann_whitney"):
            analysis = TTestIndPower()
        elif test_type == "anova":
            analysis = FTestAnovaPower()
        else:
            analysis = TTestIndPower()

        ratio = 1.0
        if n is not None and effect_size is not None and effect_size > 0:
            achieved = analysis.power(
                effect_size=effect_size, nobs1=n, alpha=alpha, ratio=ratio
            )
            result["achieved_power"] = round(float(achieved), 4)
            result["adequate"] = bool(achieved >= power)

        if n is not None and (effect_size is None or effect_size <= 0):
            mde = analysis.solve_power(
                nobs1=n, alpha=alpha, power=power, ratio=ratio
            )
            result["mde"] = round(float(mde), 4)
            result["interpretation"] = (
                f"当前样本量 n={n} 在 alpha={alpha} 下能检测到的最小效应量 d={result['mde']}"
            )

        if effect_size is not None and effect_size > 0 and n is None:
            required_n = analysis.solve_power(
                effect_size=effect_size, alpha=alpha, power=power, ratio=ratio
            )
            result["required_n_per_group"] = int(np.ceil(required_n))
            result["interpretation"] = (
                f"检测 d={effect_size} 需要每组至少 {result['required_n_per_group']} 个样本"
                f" (alpha={alpha}, power={power})"
            )
    except Exception as exc:
        result["note"] = f"功效分析失败: {str(exc)[:80]}"
    return result


# ── 稳健性检查套件 ──────────────────────────────────────────────────

def robustness_check(df, value_col, group_col=None, test_func=None,
                     n_bootstrap=500, ci_level=0.95):
    """
    稳健性检查：
      1. 全样本结果
      2. 去除异常值(±3 SD)后重跑
      3. Bootstrap 置信区间
      4. 结论稳定性评估
    返回 dict 含各步骤结果和 stability verdict。
    """
    clean = df[value_col].dropna().values
    results = {"value_col": str(value_col), "group_col": str(group_col) if group_col else None}

    # Step 1: 全样本描述
    full_mean = float(np.mean(clean))
    full_median = float(np.median(clean))
    results["full_sample"] = {"n": len(clean), "mean": round(full_mean, 4), "median": round(full_median, 4)}

    # Step 2: 去异常值
    sd = np.std(clean)
    mask = np.abs(clean - full_mean) < 3 * sd
    trimmed = clean[mask]
    n_outliers_removed = len(clean) - len(trimmed)
    trim_mean = float(np.mean(trimmed))
    results["trimmed"] = {
        "n": len(trimmed),
        "outliers_removed": n_outliers_removed,
        "mean": round(trim_mean, 4),
        "mean_shift_pct": round(abs(trim_mean - full_mean) / max(abs(full_mean), 1e-8) * 100, 2),
    }

    # Step 3: Bootstrap CI for mean
    rng = np.random.RandomState(42)
    boot_means = [np.mean(rng.choice(clean, size=len(clean), replace=True))
                  for _ in range(min(n_bootstrap, 2000))]
    alpha_ci = 1 - ci_level
    lo, hi = np.percentile(boot_means, [100 * alpha_ci / 2, 100 * (1 - alpha_ci / 2)])
    results["bootstrap"] = {
        "n_iterations": min(n_bootstrap, 2000),
        "ci_lower": round(float(lo), 4),
        "ci_upper": round(float(hi), 4),
        "ci_level": ci_level,
    }
    results["bootstrap"]["excludes_zero"] = bool(lo * hi > 0)

    # Step 4: 稳定性评估
    shift_pct = results["trimmed"]["mean_shift_pct"]
    stable_flags = []
    if shift_pct < 5:
        stable_flags.append("去异常值后均值变化 < 5%")
    if results["bootstrap"]["excludes_zero"]:
        stable_flags.append("Bootstrap CI 不含0")
    results["stability"] = {
        "verdict": "STABLE" if len(stable_flags) >= 2 else ("MODERATE" if len(stable_flags) == 1 else "UNSTABLE"),
        "checks_passed": stable_flags,
        "detail": "; ".join(stable_flags) if stable_flags else "结论不够稳健，需谨慎解读",
    }
    return results


# ── 回归诊断面板 ────────────────────────────────────────────────────

def regression_diagnostics(df, y_col, x_cols, add_intercept=True):
    """
    完整回归诊断：
      - VIF 共线性
      - Breusch-Pagan 异方差检验
      - Durbin-Watson 自相关
      - R²adj / AIC / BIC / F-statistic
      - 各系数的标准化 beta 和 95% CI
    """
    if not HAS_STATSMODELS:
        return {"error": "statsmodels未安装"}

    y = pd.to_numeric(df[y_col], errors="coerce").dropna()
    X = df.loc[:, x_cols].apply(pd.to_numeric, errors="coerce")
    valid_mask = y.notna() & X.notna().all(axis=1)
    y_clean = y[valid_mask].values.astype(float)
    X_clean = X[valid_mask].values.astype(float)
    col_names = list(x_cols)

    if len(y_clean) < len(x_cols) + 5:
        return {"error": f"n={len(y_clean)} insufficient for {len(x_cols)} predictors"}

    if add_intercept:
        X_design_arr = np.column_stack([np.ones(len(y_clean))] + [X_clean[:, i] for i in range(X_clean.shape[1])])
        design_names = ["const"] + col_names
    else:
        X_design_arr = X_clean
        design_names = col_names

    model = sm_api.OLS(y_clean, X_design_arr).fit()

    diagnostics = {
        "n": len(y),
        "r_squared": round(float(model.rsquared), 4),
        "r_squared_adj": round(float(model.rsquared_adj), 4),
        "aic": round(float(model.aic), 2),
        "bic": round(float(model.bic), 2),
        "f_statistic": round(float(model.fvalue), 4) if model.fvalue is not None else None,
        "f_p_value": round(_safe_float(model.f_pvalue), 6) if model.f_pvalue is not None else None,
    }

    # VIF
    vif_values = {}
    for i, colname in enumerate(design_names):
        if colname.lower() != "const":
            try:
                vif = variance_inflation_factor(X_design_arr, i)
                vif_values[colname] = round(float(vif), 2)
            except Exception:
                vif_values[colname] = None
    diagnostics["vif"] = vif_values
    high_vif = {k: v for k, v in vif_values.items() if v is not None and v > 5}
    diagnostics["high_vif_warning"] = bool(high_vif)
    diagnostics["high_vif_vars"] = list(high_vif.keys()) if high_vif else []

    # Breusch-Pagan heteroscedasticity
    try:
        bp_lm, bp_lm_pval, bp_f, bp_f_pval = het_breuschpagan(model.resid, X_design_arr)
        diagnostics["breusch_pagan"] = {
            "lm_stat": round(float(bp_lm), 4),
            "p_value": round(_safe_float(bp_lm_pval), 6),
            "heteroscedastic": bool(bp_lm_pval < 0.05),
        }
    except Exception:
        diagnostics["breusch_pagan"] = None

    # Durbin-Watson autocorrelation
    try:
        dw = dw_stat(model.resid)
        diagnostics["durbin_watson"] = round(float(dw), 4)
        diagnostics["autocorrelation_warning"] = bool(dw < 1.5 or dw > 2.5)
    except Exception:
        diagnostics["durbin_watson"] = None

    # Coefficients with CI
    std_y_val = float(np.std(y_clean)) if len(y_clean) > 0 else 0.0
    coefs = []
    conf = model.conf_int()
    param_names = list(design_names)
    for i, pname in enumerate(param_names):
        coef_entry = {
            "variable": str(pname),
            "coef": round(float(model.params[i]), 4),
            "se": round(float(model.bse[i]), 4),
            "t_value": round(float(model.tvalues[i]), 4),
            "p_value": round(_safe_float(model.pvalues[i]), 6),
            "ci_lower": round(float(conf[i][0]), 4),
            "ci_upper": round(float(conf[i][1]), 4),
        }
        # Standardized beta
        if pname.lower() != "const":
            x_idx = col_names.index(pname) if pname in col_names else -1
            std_x_val = float(np.std(X_clean[:, x_idx])) if x_idx >= 0 and x_idx < X_clean.shape[1] else 1.0
            coef_entry["std_beta"] = round(float(model.params[i]) * std_x_val / std_y_val, 4) if std_y_val > 0 and std_x_val > 0 else None
        coefs.append(coef_entry)
    diagnostics["coefficients"] = coefs

    # Overall assessment
    issues = []
    if diagnostics.get("high_vif_warning"):
        issues.append(f"VIF>5共线性: {', '.join(diagnostics['high_vif_vars'])}")
    bp = diagnostics.get("breusch_pagan")
    if bp and bp.get("heteroscedastic"):
        issues.append("存在异方差(Breusch-Pagan p<0.05)，建议使用稳健标准误")
    dw = diagnostics.get("durbin_watson")
    if dw is not None and diagnostics.get("autocorrelation_warning"):
        issues.append(f"残差自相关(DW={dw})")
    diagnostics["assessment"] = "; ".join(issues) if issues else "回归诊断通过，无明显问题"
    diagnostics["has_issues"] = bool(issues)

    return diagnostics


# ── 因果推断提示器 ──────────────────────────────────────────────────

def causal_hints(df, treatment_col, outcome_col, covariate_cols=None):
    """
    因果推断基础检查：
      1. 处理组和对照组的协变量平衡性（标准化差异 SMD）
      2. 提示潜在混淆变量
      3. 建议方法（PSM/DiD/IV）
    """
    hints = {
        "treatment": str(treatment_col),
        "outcome": str(outcome_col),
        "covariates_checked": [],
        "balance_issues": [],
        "recommendations": [],
    }
    treat_vals = set(df[treatment_col].dropna().unique())
    if len(treat_vals) != 2:
        hints["balance_issues"].append(f"处理变量有{len(treat_vals)}个水平，非二分类，SMD不适用")
        return hints

    treated_mask = df[treatment_col] == sorted(treat_vals)[1]
    covars = covariate_cols or [c for c in df.select_dtypes(include=[np.number]).columns
                                 if c not in (treatment_col, outcome_col)]
    for covar in covars[:10]:
        vals_treated = pd.to_numeric(df.loc[treated_mask, covar], errors="coerce").dropna()
        vals_control = pd.to_numeric(df.loc[~treated_mask, covar], errors="coerce").dropna()
        if len(vals_treated) < 3 or len(vals_control) < 3:
            continue
        pooled_sd = np.sqrt((vals_treated.var() + vals_control.var()) / 2)
        smd = abs(vals_treated.mean() - vals_control.mean()) / pooled_sd if pooled_sd > 0 else 0
        hints["covariates_checked"].append({
            "variable": str(covar), "smd": round(float(smd), 4),
            "balanced": bool(smd < 0.1),
        })
        if smd >= 0.1:
            hints["balance_issues"].append(f"{covar}: SMD={smd:.3f} >= 0.1，两组不平衡")

    if hints["balance_issues"]:
        hints["recommendations"].append("建议使用倾向得分匹配(PSM)控制混淆偏倚")
        hints["recommendations"].append("或使用双重差分法(DiD)如果有时序数据")
        hints["recommendations"].append("敏感性分析：检查不可观测混淆变量的影响(E-value)")
    else:
        hints["recommendations"].append("协变量平衡良好(SMD均<0.1)，可直接比较")

    return hints


def _py(v):
    """Convert numpy scalar to Python native type."""
    if hasattr(v, "item"):
        return v.item()
    return v

def _safe_float(val):
    """Convert to float safely."""
    try:
        v = float(val)
        if np.isnan(v) or np.isinf(v):
            return 0.0
        return v
    except (TypeError, ValueError):
        return 0.0
