# AI Data Assistant · AI 数据分析助手

> Your private ChatGPT-for-Data, running entirely on your machine.
> 上传 Excel/CSV，用中文问一句，自动生成 Pandas 代码、给出结论与图表——你在本机私有的「数据问答助手」。

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![CI](https://github.com/lengzhanbao/ai-data-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/lengzhanbao/ai-data-assistant/actions)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/lengzhanbao/ai-data-assistant/issues)

---

**English** · [中文](#中文)

## English

### What is this?

Upload a CSV / Excel file, ask a question in plain language, and the assistant:
1. Understands your data schema (columns, dtypes, sample rows, statistics)
2. Generates **Pandas / Matplotlib code** via an LLM
3. Executes it in a **safe sandbox** (isolated subprocess + import whitelist + timeout)
4. Returns a **text answer + chart**, and shows you the generated code

### Highlights

- 🔍 **Auto Insights / Anomaly Detection** — one click produces *overview → anomalies → recommendations* (z-score based)
- 🗄️ **SQL Translation** — every analysis also shows the equivalent SQL (great for interviews / BI teams)
- 🛡️ **Safe Sandbox** — generated code runs in an isolated process with an import whitelist; no `os`, `subprocess`, `socket`
- 🔁 **Self-healing** — if generated code fails, the error is fed back to the LLM for one auto-retry
- 🌐 **BYO LLM** — works with any OpenAI-compatible endpoint (OpenAI, DeepSeek, GLM, local Ollama…)

### Quick Start

```bash
pip install -r requirements.txt

# Configure your LLM (OpenAI-compatible)
export LLM_BASE_URL="https://api.openai.com/v1"
export LLM_API_KEY="sk-..."
export LLM_MODEL="gpt-4o-mini"

python app.py
# Open http://127.0.0.1:5000 — upload sample_data/video_stats.csv and ask away
```

Try these questions with the sample data:
- Which video has the highest completion rate? (哪个视频完播率最高？)
- Top 5 videos by play count? (播放量最高的 5 个视频？)
- Play-count trend by publish date? (按发布日期画播放量趋势图)
- Click **🔍 Auto Insights** for one-click anomaly detection

### Project Layout

```
app.py             Flask server (upload / ask / insights / health / charts)
analyzer.py        Engine: LLM codegen + sandbox run + auto-retry + SQL translation
sandbox.py         Safe sandbox (isolated subprocess + whitelist + timeout)
runner.py          Sandbox child process (CJK font config)
llm_client.py      OpenAI-compatible LLM client
templates/index.html  Single-page UI
sample_data/       Sample video analytics data
test_sandbox.py    Sandbox tests
test_app.py        End-to-end web tests (with a fake LLM)
```

### Tests

```bash
python test_sandbox.py   # sandbox exec + chart + danger-block
python test_app.py       # upload -> ask -> insights -> health, end-to-end
```

### Roadmap

- [ ] Record a GIF demo into the README
- [ ] `docker compose up` one-command deployment
- [ ] Multi-dataset sessions per user

[⬆ Back to top](#ai-data-assistant--ai-数据分析助手)

---

## 中文

### 这是什么？

上传一份 Excel / CSV，用自然语言提问，系统自动：
1. 让 LLM 理解数据表结构（列名、类型、前几行、统计描述）
2. 生成 **Pandas / Matplotlib** 代码
3. 在**安全沙箱**（独立子进程 + 导入白名单 + 超时终结）里执行
4. 返回**文字结论 + 图表**，并展示生成的代码

### 亮点

- 🔍 **自动洞察 / 异常下探**：一键产出「数据总览 → 异常定位 → 运营建议」（基于 z-score）
- 🗄️ **等价 SQL 对照**：每个分析同时翻译成 SQL 展示（面试友好，BI 团队协作友好）
- 🛡️ **安全沙箱**：生成代码在隔离进程运行，导入白名单，禁 `os/subprocess/socket`
- 🔁 **自动纠错**：生成代码执行报错 → 报错回灌 LLM 自动修正一次
- 🌐 **自带模型**：任意 OpenAI 兼容端点（OpenAI / DeepSeek / GLM / 本地 Ollama…）

### 快速开始

```bash
pip install -r requirements.txt

# 配置 LLM（OpenAI 兼容，可用你已有的端点）
export LLM_BASE_URL="https://api.openai.com/v1"
export LLM_API_KEY="sk-..."
export LLM_MODEL="gpt-4o-mini"

python app.py
# 打开 http://127.0.0.1:5000 ，上传 sample_data/video_stats.csv 即可体验
```

示例问题：
- 哪个视频完播率最高？
- 播放量最高的 5 个视频是哪些？
- 按发布日期画播放量趋势图
- 点「🔍 自动洞察」一键异常下探

### 工程要点（面试可讲）

| 点 | 做法 |
|----|------|
| 沙箱隔离 | 独立进程 + 超时 kill，不污染主进程 |
| 安全 | 导入白名单 + 受限内置函数，禁 `os/subprocess/socket` |
| 容错 | LLM 代码报错 → 自动回灌修正一次 |
| 可解释 | 前端展示生成的代码，结果可追溯 |
| SQL 双语 | 每次分析自动附等价 SQL（对应「会 SQL 优先」） |
| 异常下探 | 一键洞察：总览 / 1.5σ 异常 / 运营建议 |

### 文件结构

```
app.py             Flask 服务（上传 / 提问 / 洞察 / 出图 / health）
analyzer.py        分析引擎：LLM 生成代码 + 沙箱执行 + 自动重试 + SQL 翻译
sandbox.py         安全沙箱（独立子进程 + 白名单 + 超时）
runner.py          沙箱子进程运行脚本（中文字体配置在此）
llm_client.py      OpenAI 兼容 LLM 客户端
templates/index.html  单页 UI（示例chips / 洞察按钮 / SQL折叠）
sample_data/       示例视频数据（对应你帮老师爬的数据）
test_sandbox.py    沙箱离线测试
test_app.py        端到端 Web 测试（假 LLM）
```

### 测试

```bash
python test_sandbox.py   # 沙箱执行 + 出图 + 危险拦截
python test_app.py       # 上传→提问→洞察→健康检查 端到端
```

### 开发计划

- [ ] README 补充演示 GIF
- [ ] `docker compose up` 一键部署
- [ ] 多数据集会话支持

[⬆ 返回顶部](#ai-data-assistant--ai-数据分析助手)

---

## License · 许可证

MIT © [lengzhanbao](https://github.com/lengzhanbao)