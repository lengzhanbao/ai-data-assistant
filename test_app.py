"""端到端测试：用假 LLM 验证 /upload -> /ask -> /insights 完整 Web 链路（无需真实 API key）。"""
import importlib
import os
import sys as _sys
from io import BytesIO

import analyzer
from app import app

# 测试脚本复用同一 Flask app；启动前清理上次进程残留的内存状态。
app.config["sessions"].clear()

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
assert up["active"] == up["dataset_id"]
assert len(up["datasets"]) == 1

# /ask：正常分析 + 图表 + SQL 对照
r = client.post("/ask", json={"question": "哪个视频完播率最高？"})
ask = r.get_json()
print("ASK ok=%s has_chart=%s has_sql=%s" % (bool(ask.get("result")), bool(ask.get("chart")), bool(ask.get("sql"))))
assert ask.get("chart"), "未返回图表 URL"
assert "完播率最高" in ask["result"]
# 按需获取 SQL
r_sql = client.get(f"/ask/{ask['result_id']}/sql")
sql_res = r_sql.get_json()
assert sql_res and sql_res.get("sql"), "未返回 SQL 对照"
assert ask["dataset_id"] == up["dataset_id"]
assert ask.get("result_id"), ask
history = client.get("/history").get_json()
assert history["items"] and history["items"][0]["result_id"] == ask["result_id"]
item = client.get(f"/history/{ask['result_id']}").get_json()
assert item["question"] == "哪个视频完播率最高？"
assert client.get(f"/history/{ask['result_id']}/download/result").status_code == 200
chart_name = ask["chart"].rsplit("/", 1)[-1]
assert client.get(ask["chart"]).status_code == 200
assert chart_name.startswith(up["dataset_id"] + "_")

# /datasets 列出数据集
r = client.get("/datasets")
listed = r.get_json()
print("DATASETS count=%s active=%s" % (len(listed["datasets"]), listed["active"]))
assert len(listed["datasets"]) == 1
assert listed["datasets"][0]["active"]

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

# 边界：上传损坏文件应被 422 拒绝
bad = client.post("/upload", data={"file": (BytesIO(b"not a valid xlsx file"), "bad.xlsx")}, content_type="multipart/form-data")
assert bad.status_code == 422, bad.status_code
assert bad.get_json()["code"] == "INVALID_FILE", bad.get_json()
print("SECURITY invalid file rejected: OK")

empty = client.post("/upload", data={"file": (BytesIO(b""), "empty.csv")}, content_type="multipart/form-data")
assert empty.status_code == 422, empty.status_code
print("SECURITY empty file rejected: OK")

# /ask 不带 JSON
no_body = client.post("/ask")
assert no_body.status_code == 400, no_body.status_code
assert no_body.get_json()["code"] == "INVALID_REQUEST", no_body.get_json()
print("SECURITY ask requires JSON body: OK")

# /ask 问题过长
long = "问" * 3000
too_long = client.post("/ask", json={"question": long})
assert too_long.status_code == 422, too_long.status_code
assert too_long.get_json()["code"] == "QUESTION_TOO_LONG", too_long.get_json()
print("SECURITY ask question length bound: OK")

bad_type = client.post("/ask", json={"question": 123})
assert bad_type.status_code == 400, bad_type.status_code
print("SECURITY ask question type validation: OK")

# 生产环境缺 FLASK_SECRET 应启动失败
_sys.modules.pop("app", None)
os.environ["FLASK_ENV"] = "production"
os.environ.pop("FLASK_SECRET", None)
try:
    importlib.import_module("app")
except RuntimeError as exc:
    assert "FLASK_SECRET" in str(exc), exc
    print("SECURITY production secret enforcement: OK")
finally:
    os.environ.pop("FLASK_ENV", None)
    _sys.modules.pop("app", None)
    # 重新导入 app，恢复测试客户端
    import app as _app
    client = _app.app.test_client()
    with client.session_transaction() as sess:
        sess["sid"] = "test-sid"

# 重新上传数据以确保 ask/insights 还能跑
with open("sample_data/video_stats.csv", "rb") as f:
    client.post("/upload", data={"file": (f, "v.csv")}, content_type="multipart/form-data")

# 多数据集：第二次上传应创建新的 dataset_id
r1 = client.get("/datasets")
first_active = r1.get_json()["active"]
with open("sample_data/video_stats.csv", "rb") as f:
    r2 = client.post("/upload", data={"file": (f, "v2.csv")}, content_type="multipart/form-data")
up2 = r2.get_json()
assert up2["dataset_id"] != first_active
assert len(up2["datasets"]) == 2
assert up2["active"] == up2["dataset_id"]
print("MULTI_DATASET second upload OK")

# 切换数据集
r = client.post("/datasets/select", json={"dataset_id": first_active})
assert r.status_code == 200, r.status_code
assert r.get_json()["active"] == first_active
print("MULTI_DATASET select active OK")

# 删除非活跃数据集
r = client.get("/datasets")
non_active = next(d for d in r.get_json()["datasets"] if not d["active"])["dataset_id"]
r = client.delete(f"/datasets/{non_active}")
assert r.status_code == 200, r.status_code
print("MULTI_DATASET delete OK")

# 未知数据集应 404
r = client.delete("/datasets/不存在的id")
assert r.status_code == 404, r.status_code
print("MULTI_DATASET unknown id rejected: OK")

print("\n[PASS] 端到端 /upload -> /ask(SQL) -> /insights -> /health + 安全边界 + 多数据集 全部正常")
