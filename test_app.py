"""端到端测试：用假 LLM 验证 /upload -> /ask -> /insights 完整 Web 链路（无需真实 API key）。"""
import analyzer
from app import app

# 假 LLM：按 system 内容分流（SQL 翻译 / 普通分析 / 洞察）
def fake_chat(system, user, temperature=0.2, timeout=60):
    if "SQL 专家" in system:
        return "SELECT 视频标题, 完播率 FROM df ORDER BY 完播率 DESC LIMIT 1;"
    if "异常下探" in system:
        return (
            "avg_w = df['完播率'].mean()\n"
            "low = df[df['完播率'] < avg_w - 2*df['完播率'].std()]\n"
            "result = f\"总览：共{len(df)}条视频，完播率均值{avg_w:.1%}\\n异常：完播率显著低于均值的有{len(low)}条\\n建议：对低完播率视频优化封面与开头3秒。\"\n"
        )
    return (
        "top = df.loc[df['完播率'].idxmax()]\n"
        "result = f\"完播率最高：《{top['视频标题']}》，达 {top['完播率']*100:.1f}%\"\n"
        "fig = plt.figure(figsize=(8,4))\n"
        "df.sort_values('播放量', ascending=False).head(5).plot.bar("
        "x='视频标题', y='播放量', ax=fig.gca(), legend=False, color='#4f8cff')\n"
        "plt.title('播放量 Top5')\n"
        "plt.xticks(rotation=30, ha='right')\n"
    )

analyzer.chat = fake_chat

client = app.test_client()
with client.session_transaction() as sess:
    sess["sid"] = "test-sid"

with open("sample_data/video_stats.csv", "rb") as f:
    r = client.post("/upload", data={"file": (f, "v.csv")}, content_type="multipart/form-data")
up = r.get_json()
print("UPLOAD rows=%s cols=%s columns=%s" % (up["rows"], up["cols"], len(up["columns"])))
assert up["rows"] == 15 and up["cols"] == 9

# /ask：正常分析 + 图表 + SQL 对照
r = client.post("/ask", json={"question": "哪个视频完播率最高？"})
ask = r.get_json()
print("ASK ok=%s has_chart=%s has_sql=%s" % (bool(ask.get("result")), bool(ask.get("chart")), bool(ask.get("sql"))))
assert ask.get("chart"), "未返回图表 URL"
assert ask.get("sql"), "未返回 SQL 对照"
assert "完播率最高" in ask["result"]

# /insights：自动洞察/异常下探
r = client.post("/insights")
ins = r.get_json()
print("INSIGHTS ok=%s has_异常=%s" % (bool(ins.get("result")), ("异常" in (ins.get("result") or ""))))
assert ins.get("result") and "异常" in ins["result"]

# /health
r = client.get("/health")
h = r.get_json()
print("HEALTH llm_ready=%s" % h["llm_ready"])
assert "llm_ready" in h

# 安全：路径穿越攻击应被拒绝（修复 CHART-1 漏洞的回归测试）
r = client.get("/chart/..%2f..%2fREADME.md")
assert r.status_code in (400, 404), r.status_code
r2 = client.get("/chart/..%2F..%2Fetc%2Fpasswd")
assert r2.status_code in (400, 404), r2.status_code
print("SECURITY chart path-traversal blocked: OK")

print("\n[PASS] 端到端 /upload -> /ask(SQL) -> /insights -> /health 全部正常")
