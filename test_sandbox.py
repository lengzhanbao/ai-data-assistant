"""离线测试：不调用 LLM，直接验证安全沙箱能执行代码并出图。"""
import pandas as pd

from sandbox import _preflight, run_code


def main():
    df = pd.read_csv("sample_data/video_stats.csv")

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

    bad = run_code("import os\nresult='should not happen'", df)
    print("\n危险代码拦截 ok:", not bad["ok"])
    assert not bad["ok"]
    print("[PASS] 沙箱成功拦截危险导入")

    for label, dangerous in (
        ("__import__", "__import__('os').system('ls')"),
        ("dunder", "df.__class__"),
        ("func def", "def f(): return 1\nresult = f()"),
        ("lambda", "f = lambda x: x\nresult = str(f(1))"),
        ("open", "result = open('secret.txt').read()"),
        ("savefig", "plt.savefig('/tmp/out.png')"),
    ):
        blocked = run_code(dangerous, df)
        assert not blocked["ok"], f"{label} 未被拦截"
    print("[PASS] AST 预检拦截 __import__ / 属性访问 / 函数定义 / lambda / open")

    try:
        _preflight("a" * 30000)
    except ValueError:
        pass
    else:
        raise AssertionError("过长代码未被拒绝")
    print("[PASS] 代码长度上限生效")


if __name__ == "__main__":
    main()
