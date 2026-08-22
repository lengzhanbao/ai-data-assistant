"""inference_engine tests: bayes, power, robustness, regression, causal."""
import numpy as np
import pandas as pd
import pytest

from inference_engine import (
    bayes_alternative, power_analysis, robustness_check,
    regression_diagnostics, causal_hints,
)

rng = np.random.RandomState(42)
PASS = 0; FAIL = 0; FAILURES = []
def t(name, cond):
    global PASS, FAIL
    if cond: PASS += 1
    else: FAIL += 1; FAILURES.append(name)

# Bayes factor
g1 = rng.normal(50,10,60); g2 = rng.normal(55,10,60)
r = bayes_alternative(g1, g2)
t("bayes: bf>10", r.get("bf10",0) > 10)
t("bayes: interpretation non-empty", len(r.get("interpretation","")) > 5)
g3 = rng.normal(50,10,60); g4 = rng.normal(50.2,10,60)  # tiny diff
r2 = bayes_alternative(g3, g4)
t("bayes_null: bf<10", (r2.get("bf10") or 999) < 10)

# Power analysis
rp = power_analysis(n=30, effect_size=0.8)
t("power: has achieved_power", "achieved_power" in rp)
t("power: adequate for d=0.8 n=30", rp.get("adequate") == True)
rp2 = power_analysis(n=10, effect_size=0.2)
t("power_low_n: not adequate", rp2.get("adequate") == False)
rp3 = power_analysis(n=None, effect_size=0.5, power=0.80)
t("power_solve_n: has required_n", "required_n_per_group" in rp3)
rp4 = power_analysis(n=100, effect_size=None, power=0.80)
t("power_solve_mde: has mde", "mde" in rp4)

# Robustness
df_rob = pd.DataFrame({"val": rng.normal(100,15,200)})
df_rob.loc[50] = 500
rr = robustness_check(df_rob, "val")
t("robust: has stability verdict", rr["stability"]["verdict"] in ("STABLE","MODERATE","UNSTABLE"))
t("robust: bootstrap CI exists", "ci_lower" in rr["bootstrap"])
t("robust: outliers detected", rr["trimmed"]["outliers_removed"] > 0)

# Regression diagnostics
df_reg = pd.DataFrame({"x1": rng.normal(0,1,100), "x2": rng.normal(0,1,100)})
df_reg["y"] = 2*df_reg["x1"] + df_reg["x2"]*0.5 + rng.normal(0,0.3,100)
rd = regression_diagnostics(df_reg, "y", ["x1","x2"])
t("regdiag: R2adj>0.5", rd.get("r_squared_adj",0) > 0.5)
t("regdiag: VIF computed", isinstance(rd.get("vif"), dict))
t("regdiag: coefficients present", len(rd.get("coefficients",[])) >= 3)
t("regdiag: no high VIF", rd.get("high_vif_warning") == False or len(rd.get("high_vif_vars",[])) == 0)
t("regdiag: BP test present", rd.get("breusch_pagan") is not None)
t("regdiag: DW present", rd.get("durbin_watson") is not None)
t("regdiag: std_beta present", any(c.get("std_beta") for c in rd["coefficients"] if c["variable"] != "const"))

# Causal hints
df_caus = pd.DataFrame({
    "treat": [0]*50 + [1]*50,
    "outcome": rng.normal(0,1,100),
    "age": rng.normal(35,8,100),
    "income": rng.normal(50,20,100),
})
rc = causal_hints(df_caus, "treat", "outcome", ["age","income"])
t("causal: covariates checked", len(rc["covariates_checked"]) == 2)
t("causal: has SMD values", all("smd" in c for c in rc["covariates_checked"]))
t("causal: recommendations exist", len(rc["recommendations"]) > 0)

# Edge cases
try:
    bayes_alternative(np.array([]), np.array([])); t("bayes_empty: no crash", True)
except Exception: t("bayes_empty: no crash", False)

try:
    robustness_check(pd.DataFrame({"val":[np.nan]*10}), "val"); t("robust_nan: no crash", True)
except Exception: t("robust_nan: no crash", False)

try:
    regression_diagnostics(pd.DataFrame({"x":[1],"y":[1]}), "y", ["x"]); t("reg_tiny: no crash", True)
except Exception: t("reg_tiny: no crash", False)

print(f"\n{'='*50}\nPASSED: {PASS}/{PASS+FAIL}")
if FAILURES: print("FAILED:", FAILURES)
else: print("ALL PASSED!")
assert FAIL == 0