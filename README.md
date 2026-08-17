# AI 数据分析助手（vibecoding 项目 ①）

> 匹配目标：**小米 · 小爱音箱策略运营实习生 JD** ——「数据分析 / 异常下探 / 会 SQL 优先 / 了解 AI agent 搭建优先」
> 复用资产：你「帮老师爬视频数据 + 处理数据」的真实场景。

## 它能做什么
上传一份 Excel / CSV，用自然语言提问，系统自动：
1. 让 LLM 理解数据表结构（列、类型、前几行、统计描述）
2. 生成 Pandas / Matplotlib 代码
3. 在**安全沙箱**（独立子进程 + 导入白名单 + 超时终结）里执行
4. 返回**文字结论 + 图表**，并展示生成的代码

**新增（对应小爱JD）：**
- 🔍 **自动洞察 / 异常下探**：一键按钮，自动产出「数据总览 + 异常点定位 + 运营建议」（JD 关键词：数据分析 / 异常下探）
- 🗄️ **等价 SQL 对照**：每个分析同时翻译成 SQL 展示（JD 关键词：会 SQL 优先）
- ⚠️ LLM 未配置时页面顶部友好提示（/health 探测）
- 💡 示例问题一键点击（chips），无需打字

示例问题（用 `sample_data/video_stats.csv` 直接试）：
- 哪个视频完播率最高？
- 播放量最高的 5 个视频是哪些？
- 按发布日期画播放量趋势图
- 互动率和完播率的相关性如何？
- 点「🔍 自动洞察」看异常下探效果

## 运行
```bash
pip install -r requirements.txt

# 配置 LLM（OpenAI 兼容协议，可用你已有的 opencode / glm / deepseek 端点）
export LLM_BASE_URL="https://你的端点/v1"
export LLM_API_KEY="你的key"
export LLM_MODEL="模型名"

python app.py
# 打开 http://127.0.0.1:5000 ，上传 sample_data/video_stats.csv 即可体验
```

自检 LLM 连通性：`python llm_client.py`

## 工程要点（面试可讲）
| 点 | 做法 |
|----|------|
| 沙箱隔离 | `multiprocessing` 独立进程，超时 `terminate`，不污染主进程 |
| 安全 | 导入白名单 + 受限内置函数，禁 `os/subprocess/socket` |
| 容错 | LLM 生成代码执行报错 → 自动把报错回灌 LLM 修正一次 |
| 可解释 | 前端展示生成的代码，结果可追溯 |
| 数据接口 | 数据集以变量 `df` 注入，代码无法读磁盘其他文件 |

## 对应小米 JD 的话术
- 「数据分析 / 异常下探」→ 一键「自动洞察」：上传业务表，自动产出 总览/异常/建议（z-score 定位低完播率视频等）
- 「会 SQL 优先」→ 每个分析自动附**等价 SQL**，展示你懂结构化查询（Pandas ↔ SQL 双语能力）
- 「了解 AI agent 搭建优先」→ 本项目是 Agent 范式：LLM 决策 → 调用工具（代码执行）→ 观察结果 → 修正重试，与你的 QQBot Agent 同源

## 文件结构
```
app.py             Flask 服务（上传 / 提问 / 自动洞察 / 出图 / health）
analyzer.py        分析引擎：LLM 生成代码 + 沙箱执行 + 自动重试 + SQL 翻译
sandbox.py         安全沙箱（独立子进程 + 白名单 + 超时）
runner.py          沙箱子进程运行脚本（中文字体配置在此）
llm_client.py      OpenAI 兼容 LLM 客户端
templates/index.html  单页 UI（示例chips / 洞察按钮 / SQL折叠）
sample_data/       示例视频数据（对应你帮老师爬的数据）
test_sandbox.py    沙箱离线测试
test_app.py        端到端 Web 测试（假 LLM）
```
