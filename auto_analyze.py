"""
自动数据分析引擎：上传即分析，不需要用户先提问。
生成结构化的"数据发现报告"，包括描述统计、相关性发现、组间差异提示。
"""
import numpy as np
import pandas as pd


def auto_profile(df):
    """上传后自动执行完整的数据探索，返回结构化发现列表。"""
    findings = []
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()

    # 1. 数据概览
    overview = {
        "type": "overview",
        "title": "数据概览",
        "detail": f"共 {len(df)} 行 × {len(df.columns)} 列"
                  f"（数值列 {len(numeric_cols)}，分类列 {len(cat_cols)}）",
        "severity": "info",
    }
    findings.append(overview)

    # 2. 缺失值检查
    missing = df.isnull().sum()
    missing_pct = (missing / len(df) * 100).round(1)
    cols_with_missing = missing_pct[missing_pct > 0].sort_values(ascending=False)
    if len(cols_with_missing) > 0:
        top_missing = cols_with_missing.head(5)
        detail = ", ".join([f"{col}: {pct}%" for col, pct in top_missing.items()])
        severity = "warning" if cols_with_missing.iloc[0] > 30 else "info"
        findings.append({
            "type": "missing_values",
            "title": f"缺失值（{len(cols_with_missing)} 列有缺失）",
            "detail": detail,
            "severity": severity,
        })
    else:
        findings.append({
            "type": "missing_values",
            "title": "缺失值",
            "detail": "所有列完整无缺失 ✓",
            "severity": "good",
        })

    # 3. 数值列分布发现
    for col in numeric_cols[:5]:
        s = df[col].dropna()
        if len(s) < 5:
            continue
        skew = float(s.skew())
        float(s.kurtosis())
        desc = f"mean={s.mean():.2f}, median={s.median():.2f}, std={s.std():.2f}"
        if abs(skew) > 2:
            desc += f", 严重偏斜(skew={skew:.2f})"
            sev = "warning"
        elif abs(skew) > 1:
            desc += f", 中度偏斜(skew={skew:.2f})"
            sev = "info"
        else:
            desc += f", 近似对称(skew={skew:.2f})"
            sev = "good"

        # 异常值检测
        z_scores = np.abs((s - s.mean()) / s.std()) if s.std() > 0 else pd.Series(0, index=s.index)
        n_outliers = int((z_scores > 3).sum())
        if n_outliers > 0:
            desc += f", 发现{n_outliers}个极端值(|z|>3)"
            sev = max(sev, "warning") if sev != "good" else "warning"

        findings.append({
            "type": "distribution",
            "title": f"{col}",
            "detail": desc,
            "severity": sev,
        })

    # 4. 相关性发现
    if len(numeric_cols) >= 2:
        corr_matrix = df[numeric_cols].corr()
        high_corr_pairs = []
        for i in range(len(numeric_cols)):
            for j in range(i + 1, min(i + 6, len(numeric_cols))):
                r = corr_matrix.iloc[i, j]
                if abs(r) > 0.5 and not np.isnan(r):
                    direction = "正相关" if r > 0 else "负相关"
                    strength = "强" if abs(r) > 0.7 else "中等"
                    high_corr_pairs.append(
                        f"{numeric_cols[i]} × {numeric_cols[j]}: "
                        f"{strength}{direction}(r={r:.3f})"
                    )
        if high_corr_pairs:
            findings.append({
                "type": "correlation",
                "title": f"显著相关性（{len(high_corr_pairs)}对 |r|>0.5）",
                "detail": "; ".join(high_corr_pairs[:3]),
                "severity": "info",
            })

    # 5. 分类变量组间差异预检
    if cat_cols and numeric_cols:
        for cat_col in cat_cols[:3]:
            levels = df[cat_col].dropna().unique()
            if len(levels) == 2:
                g1 = df[df[cat_col] == levels[0]][numeric_cols[0]].dropna()
                g2 = df[df[cat_col] == levels[1]][numeric_cols[0]].dropna()
                if len(g1) >= 5 and len(g2) >= 5:
                    diff_pct = abs(g1.mean() - g2.mean()) / max(abs(g2.mean()), 1e-8) * 100
                    if diff_pct > 10:
                        from scipy import stats as sps
                        t_stat, p_val = sps.ttest_ind(g1, g2)
                        sig = "✓ 显著" if p_val < 0.05 else "不显著"
                        findings.append({
                            "type": "group_diff",
                            "title": f"{cat_col}: {levels[0]} vs {levels[1]}",
                            "detail": (
                                f"{numeric_cols[0]}均值差 {diff_pct:.1f}% "
                                f"(t={t_stat:.2f}, p={p_val:.4f}) {sig}"
                            ),
                            "severity": "info" if p_val < 0.05 else "info",
                        })

    # 6. 建议下一步分析
    suggestions = []
    if len(numeric_cols) >= 2:
        suggestions.append("🔗 相关性分析：哪些变量互相影响？")
    if cat_cols and numeric_cols:
        suggestions.append("⚖️ 组间比较：不同组的指标有显著差异吗？")
    if len(numeric_cols) >= 3:
        suggestions.append("📈 回归建模：用多个自变量预测目标变量")
    if len(numeric_cols) >= 2:
        suggestions.append("🔮 聚类分析：数据里有没有自然分组？")

    return {
        "findings": findings,
        "suggestions": suggestions,
        "n_numeric": len(numeric_cols),
        "n_categorical": len(cat_cols),
    }
