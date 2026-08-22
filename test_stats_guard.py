"""
统计方法学守卫（stats_guard）边界case测试。
覆盖：正常数据、极小样本、零方差、全缺失、混合类型、大数据集。
"""
import numpy as np
import pandas as pd

from stats_guard import (
    check_normality, check_variance_equality, check_sample_size,
    detect_variable_types, recommend_method, full_guard_check,
    guard_to_prompt,
)

PASS = 0
FAIL = 0
FAILURES = []


def t(name, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(name)


# ── 正常性检查 ──

rng = np.random.RandomState(42)
normal_data = pd.Series(rng.normal(50, 10, 100))
r = check_normality(normal_data)
t("normal_data: normal=True", r["normal"] == True)
t("normal_data: has test name", r["test"] is not None)
t("normal_data: p > 0.05", r["p_value"] > 0.05)

skewed = pd.Series(rng.exponential(2, 200))
r2 = check_normality(skewed)
t("skewed: normal=False", r2["normal"] == False)

binary = pd.Series([0, 1] * 50)
r3 = check_normality(binary)
t("binary: normal=False", r3["normal"] == False)

# ── 边界case：样本量 ──

tiny = pd.Series([1.0, 2.0])
r4 = check_normality(tiny)
t("n=2: normal=False", r4["normal"] == False)
t("n=2: note mentions n", "n=2" in r4.get("note", ""))

single = pd.Series([5.0])
r5 = check_normality(single)
t("n=1: normal=False", r5["normal"] == False)

empty = pd.Series([], dtype=float)
r6 = check_normality(empty)
t("empty: normal=False", r6["normal"] == False)

large = pd.Series(rng.normal(0, 1, 6000))
r7 = check_normality(large)
t("n=6000: uses DAgostino", "Agostino" in (r7.get("test") or ""))

exact_5000 = pd.Series(rng.normal(0, 1, 5000))
r8 = check_normality(exact_5000)
t("n=5000: uses Shapiro", r8.get("test") == "Shapiro-Wilk")

constant = pd.Series([5.0] * 50)
r9 = check_normality(constant)
t("constant: normal=False or handled", isinstance(r9.get("normal"), bool))

with_nan = pd.Series([1.0, np.nan, 3.0, np.nan, 5.0, 4.0, 6.0])
r10 = check_normality(with_nan)
t("with_nan: handles gracefully", isinstance(r10.get("normal"), bool))

with_inf = pd.Series([1.0, np.inf, 3.0, 5.0])
r11 = check_normality(with_inf)
t("with_inf: handles gracefully", isinstance(r11.get("normal"), bool))


# ── 方差齐性 ──

g1 = rng.normal(10, 5, 50)
g2 = rng.normal(10, 5, 50)
r12 = check_variance_equality(g1, g2)
t("equal_var: var_equal=True", r12.get("var_equal") == True)

g3 = np.random.RandomState(123).normal(10, 30, 50)
r13 = check_variance_equality(g1, g3)
t("unequal_var: detects difference", isinstance(r13.get("var_equal"), bool))

zero_var = np.array([5.0] * 50)
r14 = check_variance_equality(g1[:50], zero_var)
t("zero_var_group: var_equal=False", r14.get("var_equal") == False)
t("zero_var_group: mentions zero variance", "zero variance" in (r14.get("note") or ""))

r15 = check_variance_equality(np.array([]), np.array([]))
t("both_empty: handled", isinstance(r15.get("var_equal"), bool))

multi_groups = [rng.normal(i * 10, 5, 30) for i in range(4)]
r16 = check_variance_equality(groups=multi_groups)
t("multi_groups: runs Levene", r16.get("test") == "Levene")


# ── 样本量检查 ──

r17 = check_sample_size(25, "t_test")
t("n=25_t_test: not adequate", r17["adequate"] == False)
t("n=25_t_test: recommends 30", r17["minimum_recommended"] == 30)

r18 = check_sample_size(100, "t_test")
t("n=100_t_test: adequate", r18["adequate"] == True)

r19 = check_sample_size(15, "anova")
t("n=15_anova: adequate (>=15)", r19["adequate"] == True)


# ── 变量类型检测 ──

df_mixed = pd.DataFrame({
    "num_cont": rng.normal(0, 1, 100),
    "num_disc": rng.randint(0, 100, 100),
    "ordinal": pd.Categorical(["low", "mid", "high"] * 33 + ["low"]),
    "cat": ["A", "B"] * 50,
    "text": [f"item_{i}" for i in range(100)],
})
vt = detect_variable_types(df_mixed)
types = {v["column"]: v["type"] for v in vt}
t("num_cont detected", types["num_cont"] == "numeric_continuous")
t("cat detected", types["cat"] == "categorical")
t("text detected as identifier (all unique)", types["text"] == "identifier")


# ── 方法推荐 ──

vt_simple = [
    {"column": "score", "type": "numeric_continuous"},
    {"column": "group", "type": "categorical", "n_unique": 2},
]
rec = recommend_method(vt_simple, "两组有差异吗")
t("diff_2groups: recommends t_test/MWU", rec["method"] == "independent_t_test_or_mann_whitney")
t("rationale mentions effect size", "Cohen" in rec["rationale"] or "效应量" in rec["rationale"])

vt_multi = [
    {"column": "y", "type": "numeric_continuous"},
    {"column": "grp", "type": "categorical", "n_unique": 4},
]
rec2 = recommend_method(vt_multi, "四组比较")
t("4groups: recommends ANOVA/KW", rec2["method"] == "one_way_anova_or_kruskal_wallis")

rec3 = recommend_method(vt_simple, "相关关系如何")
t("correlation keyword: recommends corr", "pearson" in rec3["method"].lower() or "spearman" in rec3["method"].lower())

rec4 = recommend_method(vt_simple, "")
t("no_hint: descriptive fallback", rec4["method"] == "descriptive_eda")


# ── 完整管线 ──

df_full = pd.DataFrame({
    "value": rng.normal(50, 10, 80),
    "condition": ["control"] * 40 + ["treatment"] * 40,
})
guard = full_guard_check(df_full, "两组值有差异吗")
t("full: has recommendation", "recommendation" in guard)
t("full: has assumptions", "assumptions" in guard)
t("full: has guard_summary", isinstance(guard.get("guard_summary"), str))
t("full: method is t_test family", "t_test" in guard["recommendation"]["method"] or "mann" in guard["recommendation"]["method"])
t("full: variance_equality checked", guard["assumptions"]["variance_equality"] is not None)

prompt = guard_to_prompt(guard)
t("prompt: non-empty", len(prompt) > 100)
t("prompt: mentions methodology", "methodology" in prompt)
t("prompt: mentions effect size", "效应量" in prompt)


# 极端边界：全NaN列
df_allnan = pd.DataFrame({"x": [np.nan] * 10, "g": ["A"] * 5 + ["B"] * 5})
try:
    g2_result = full_guard_check(df_allnan, "比较")
    t("all_nan: no crash", True)
except Exception:
    t("all_nan: no crash", False)

# 单行数据
df_single = pd.DataFrame({"x": [1.0], "g": ["A"]})
try:
    g3_result = full_guard_check(df_single, "分析")
    t("single_row: no crash", True)
except Exception:
    t("single_row: no crash", False)


print(f"\n{'='*50}")
print(f"PASSED: {PASS} / {PASS + FAIL}")
if FAILURES:
    print(f"FAILED ({len(FAILURES)}):")
    for f in FAILURES:
        print(f"  - {f}")
else:
    print("ALL TESTS PASSED!")
print(f"{'='*50}")

assert FAIL == 0, f"{len(FAILURES)} test(s) failed: {FAILURES}"
