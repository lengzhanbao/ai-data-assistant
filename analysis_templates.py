"""
预置分析模板：一键执行标准统计流程，不依赖用户知道统计学术语。
每个模板定义了完整的分析管线（假设检查→方法选择→代码生成→推断报告）。
"""


TEMPLATES = [
    {
        "id": "group_compare",
        "name": "组间差异比较",
        "icon": "⚖️",
        "description": "自动检测数据结构，选择t检验/Mann-Whitney U/ANOVA/Kruskal-Wallis",
        "question": "不同组之间的{value_col}有显著差异吗？请报告效应量和95%置信区间。",
        "requires": ["1 numeric + 1 categorical"],
        "prompt_hint": ("使用适当的组间比较方法。如果正态性满足且方差齐用独立样本t检验；"
                        "如果方差不齐用Welch t；如果非正态用Mann-Whitney U。"
                        "必须报告效应量(Cohen d或rank-biserial r)和Bootstrap 95%CI。"
                        "如有多组，用ANOVA+Tukey HSD或Kruskal-Wallis+Dunn。"),
    },
    {
        "id": "correlation",
        "name": "相关性分析",
        "icon": "🔗",
        "description": "Pearson/Spearman相关系数+散点图+显著性检验+效应量",
        "question": "{x_col}和{y_col}之间的相关性如何？请给出相关系数、p值和效应量解释。",
        "requires": ["2+ numeric"],
        "prompt_hint": ("计算Pearson r（正态满足）或Spearman rho（非正态）。"
                        "绘制散点图加回归线。报告r/rho值、p值、95%CI。"
                        "解释效应大小（小<0.3, 中0.3-0.5, 大>0.5）。"),
    },
    {
        "id": "regression",
        "name": "回归建模",
        "icon": "📈",
        "description": "OLS/逻辑回归+完整诊断面板(VIF/BP/DW/AIC/BIC)",
        "question": "用{x_cols}预测{y_col}。请给出回归系数、R²、诊断结果。",
        "requires": ["1 dependent + 1+ independent variables"],
        "prompt_hint": ("拟合OLS回归模型。必须输出：(1)各系数的标准化beta值和95%CI "
                        "(2)VIF共线性检查 (3)Breusch-Pagan异方差检验 (4)Durbin-Watson "
                        "(5)R²_adj, AIC, BIC。如有问题变量需指出并建议处理方案。"),
    },
    {
        "id": "distribution",
        "name": "分布探索",
        "icon": "📊",
        "description": "直方图+Q-Q图+描述统计+偏度/峰度",
        "question": "分析{value_col}的分布特征。给出描述统计、正态性检验结果和分布可视化。",
        "requires": ["1 numeric"],
        "prompt_hint": ("绘制直方图(带核密度曲线)和Q-Q图。报告n, mean, median, sd, "
                        "skewness, kurtosis, Shapiro-Wilk p值。判断是否近似正态分布。"
                        "如有极端偏斜建议对数变换。"),
    },
    {
        "id": "time_series",
        "name": "时间序列分析",
        "icon": "🕐",
        "description": "趋势分解(STL)+ADF平稳性+ACF/PACF+简单预测",
        "question": "分析{date_col}和{value_col}的时间序列。进行趋势分解和平稳性检验。",
        "requires": ["1 datetime + 1 numeric"],
        "prompt_hint": ("按时间排序后绘制时间序列图。用STL分解趋势/季节/残差。"
                        "运行ADF平稳性检验。绘制ACF/PACF图。"
                        "如需要预测，从简单指数平滑开始，逐步增加复杂度，比较AIC。"),
    },
    {
        "id": "categorical_assoc",
        "name": "分类变量关联",
        "icon": "🔀",
        "description": "卡方独立性检验+Cramer's V效应量+列联表热力图",
        "question": "{cat1}和{cat2}之间有关联吗？",
        "requires": ["2 categorical"],
        "prompt_hint": ("构建列联表(crosstab)。运行卡方独立性检验。"
                        "报告chi-squared, df, p-value, Cramér's V效应量。"
                        "绘制堆叠柱状图或热力图展示关联模式。"
                        "如期望频数<5的格子超过20%，改用Fisher精确检验。"),
    },
    {
        "id": "outlier_detect",
        "name": "异常检测",
        "icon": "🎯",
        "description": "z-score/IQR/修正z-score三重检测+箱线图标注",
        "question": "找出{value_col}中的异常值。用多种方法交叉验证。",
        "requires": ["1 numeric"],
        "prompt_hint": ("用三种方法检测异常值：(1)z-score > 3 (2)IQR法(1.5×IQR) "
                        "(3)修正z-score(MAD-based)。标注哪些点被多种方法同时标记为异常。"
                        "绘制箱线图和散点图，异常点用红色标注。讨论可能的成因。"),
    },
    {
        "id": "clustering",
        "name": "聚类分析",
        "icon": "🔮",
        "description": "K-means+最优K选择(肘部法则+轮廓系数)+PCA降维可视化",
        "question": "对{numeric_cols}进行聚类分析，找出自然分组。",
        "requires": ["2+ numeric"],
        "prompt_hint": ("标准化数据后运行K-means。用肘部法则和轮廓系数确定最优K。"
                        "用PCA降维到2D并按cluster着色绘制散点图。"
                        "报告各cluster的大小、中心位置和轮廓系数。"
                        "给每个cluster一个业务含义标签。"),
    },
]


def get_template(template_id):
    for t in TEMPLATES:
        if t["id"] == template_id:
            return t
    return None


def match_templates(variable_types):
    nums = sum(1 for v in variable_types if str(v.get("type", "")).startswith("numeric") or v.get("type") == "ordinal")
    cats = sum(1 for v in variable_types if v.get("type") == "categorical")
    dates = sum(1 for v in variable_types if v.get("type") == "datetime")
    matched = []
    for t in TEMPLATES:
        tid = t["id"]
        if tid == "data_quality":
            matched.append(t)
        elif tid in ("distribution", "outlier_detect", "power_analysis") and nums >= 1:
            matched.append(t)
        elif tid in ("group_compare",) and nums >= 1 and cats >= 1:
            matched.append(t)
        elif tid == "paired_compare":
            matched.append(t)
        elif tid in ("correlation", "regression", "clustering", "rfm_segmentation") and nums >= 2:
            matched.append(t)
        elif tid in ("time_series", "ts_forecast") and dates >= 1 and nums >= 1:
            matched.append(t)
        elif tid in ("categorical_assoc", "chi_square_test") and cats >= 2:
            matched.append(t)
    return matched
# ── Category 1: 数据质量报告 ──
TEMPLATES.append({
    "id": "data_quality",
    "name": "数据质量报告",
    "icon": "🏥",
    "description": "缺失值/重复行/格式异常/离群值一站式体检",
    "question": "请全面检查这份数据的质量：缺失值、重复行、异常格式、离群值，给出质量评分和修复建议。",
    "requires": ["any"],
    "prompt_hint": ("执行完整的数据质量检查：(1)每列缺失值数量和占比 "
                    "(2)重复行检测 (3)数值列离群值(z-score>3和IQR法) "
                    "(4)分类列的稀有类别(占比<1%) (5)日期列格式一致性检查。"
                    "输出结构化的质量报告，每个问题给出严重程度(高/中/低)和修复建议。"),
})

# ── Category 3: 配对比较 ──
TEMPLATES.append({
    "id": "paired_compare",
    "name": "配对前后测",
    "icon": "🔄",
    "description": "配对t检验/Wilcoxon符号秩检验，适用于A/B前后对比",
    "question": "比较{before_col}和{after_col}之间是否有显著差异（配对设计）。报告效应量和置信区间。",
    "requires": ["2 numeric (paired)"],
    "prompt_hint": ("这是配对设计。先计算差值d = after - before，检查差值的正态性。"
                    "如果正态用配对t检验(paired t-test)，否则用Wilcoxon符号秩检验。"
                    "必须报告效应量(Cohen dz或matched-pairs rank-biserial r)和95%CI。"
                    "同时给出Bayes因子BF10作为频率派检验的补充证据。"),
})

# ── Category 5: 卡方独立性 + Fisher精确 ──
TEMPLATES.append({
    "id": "chi_square_test",
    "name": "卡方独立性检验",
    "icon": "🔀",
    "description": "卡方/Fisher精确+Cramér's V+列联表可视化",
    "question": "{cat1}和{cat2}之间是否独立？给出卡方统计量、p值和Cramer's V。",
    "requires": ["2 categorical"],
    "prompt_hint": ("构建列联表(crosstab)。运行卡方独立性检验。"
                    "检查期望频数：如果有超过20%的格子期望频数<5，改用Fisher精确检验。"
                    "报告chi-squared, df, p-value, Cramer's V(小<0.1, 中0.1-0.3, 大>0.3)。"
                    "绘制堆叠百分比柱状图展示关联模式。"
                    "在结论中解释哪些单元格贡献了最大的卡方值。"),
})

# ── Category 6: 时间序列预测 ──
TEMPLATES.append({
    "id": "ts_forecast",
    "name": "时间序列预测",
    "icon": "🔮",
    "description": "STL分解+ADF平稳性+ARIMA/指数平滑预测+预测区间",
    "question": "基于{date_col}和{value_col}的历史数据，预测未来趋势并给出置信区间。",
    "requires": ["datetime + numeric"],
    "prompt_hint": ("按时间排序后：(1)绘制时间序列图 (2)STL分解看趋势/季节/残差 "
                    "(3)ADF平稳性检验 (4)ACF/PACF确定ARIMA参数范围 "
                    "(5)拟合SimpleExpSmoothing和ARIMA，用AIC选择更优模型 "
                    "(6)预测未来10个周期并画出95%置信区间阴影。"
                    "报告模型参数、AIC、RMSE（如有验证集）。"),
})

# ── Category 7: 功效分析 ──
TEMPLATES.append({
    "id": "power_analysis",
    "name": "功效分析",
    "icon": "⚡",
    "description": "反向计算功效/MDE/所需样本量——AB实验和论文必备",
    "question": "当前样本量能检测到多大的效应？要达到80%功效需要每组多少人？",
    "requires": ["numeric column"],
    "prompt_hint": ("运行统计功效分析：(1)根据当前数据的效应量(Cohen d)和样本量n，"
                    "计算achieved power。如果power<0.80则说明样本不足。"
                    "(2)反向计算MDE(minimum detectable effect)：当前n能检测到的最小效应。"
                    "(3)如果要达到80%功效检测中等效应(d=0.5)，每组需要多少样本。"
                    "输出三个数字并解释其实际含义。"),
})

# ── Category 8: RFM用户分群 ──
TEMPLATES.append({
    "id": "rfm_segmentation",
    "name": "RFM用户分群",
    "icon": "👥",
    "description": "K-means聚类+RFM打分+用户画像标签",
    "question": "对用户进行RFM分群分析，给每个群体起一个业务标签。",
    "requires": ["user_id, recency, frequency, monetary columns"],
    "prompt_hint": ("如果数据有用户ID和交易记录，计算R(recency)/F(frequency)/M(monetary)。"
                    "标准化后运行K-means(k=3~5)，用轮廓系数选最优k。"
                    "对每个cluster计算R/F/M均值并排名，根据排名给业务标签"
                    "(如'高价值忠诚客户','流失风险','新客户','低频用户')。"
                    "输出各cluster的人数占比和特征描述。绘制雷达图或热力图。"),
})
