"""离线测试：不调用 LLM，直接验证安全沙箱能执行代码并出图。"""
import pandas as pd
from sandbox import run_code


def main():
    df = pd.read_csv("sample_data/video_stats.csv")

    # 模拟 LLM 会生成的代码：找出完播率最高的视频，并画柱状图
    code = """
top = df.loc[df['完播率'].idxmax()]
result = f"完播率最高的是《{top['视频标题']}》，达 {top['完播率']*100:.1f}%"
fig = plt.figure(figsize=(8,4))
df.sort_values('播放量', ascending=False).head(5).plot.bar(
    x='视频标题', y='播放量', ax=fig.gca(), legend=False, color='#4f8cff')
plt.title('播放量 Top5 视频')
plt.xticks(rotation=30, ha='right')
"""

    res = run_code(code, df)
    print("ok     :", res["ok"])
    print("result :", res["result"])
    print("chart  :", "有图" if res["chart"] else "无图", f"({len(res['chart'] or b'')} bytes)")
    assert res["ok"], res["error"]
    assert res["chart"], "未生成图表"
    assert "完播率最高" in res["result"]
    print("\n[PASS] 沙箱执行 + 出图链路正常")

    # 安全测试：尝试导入 os 应被拒绝
    bad = run_code("import os\nresult='should not happen'", df)
    print("\n危险代码拦截 ok:", not bad["ok"])
    assert not bad["ok"]
    print("[PASS] 沙箱成功拦截危险导入")


if __name__ == "__main__":
    main()
