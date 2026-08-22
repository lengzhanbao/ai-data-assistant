"""Mock LLM for demo mode - works without API key."""
import numpy as np


def chat(system: str, user: str, temperature: float = 0.2, timeout: int = 60) -> str:
    """Generate simple analysis code based on the user message."""
    if "SQL" in system:
        return "SELECT * FROM df LIMIT 10;"

    if "异常" in system or "insight" in user.lower():
        return (
            "result = f'数据总览：共{len(df)}行，{len(df.columns)}列。\\n'\n"
            "for col in df.select_dtypes(include='number').columns:\n"
            "    s = df[col].dropna()\n"
            "    z = abs((s - s.mean()) / s.std())\n"
            "    outliers = (z > 3).sum()\n"
            "    result += f'{col}: mean={s.mean():.2f}, std={s.std():.2f}, 异常值={outliers}\\n'\n"
        )

    # Default: basic descriptive stats + chart
    return (
        "import matplotlib.pyplot as plt\n"
        "numeric_cols = df.select_dtypes(include='number').columns.tolist()\n"
        "stats_text = ', '.join([f'{c}: {df[c].mean():.2f}' for c in numeric_cols[:5]])\n"
        "result = f'描述性统计（前5个数值列均值）：{stats_text}'\n"
        "if len(numeric_cols) >= 1:\n"
        "    fig = plt.figure(figsize=(8, 4))\n"
        "    df[numeric_cols[0]].hist(bins=20, ax=fig.gca(), color='#4f8cff', edgecolor='white')\n"
        "    plt.title(f'Distribution of {numeric_cols[0]}')\n"
        "methodology = '使用描述性统计和直方图探索数值列分布。由于是演示模式，未执行推断检验。'"
    )