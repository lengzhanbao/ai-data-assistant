# AI 数据分析助手 CHANGELOG

本仓库使用 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Security
- **Flask 配置：**
  - 生产环境未设置 `FLASK_SECRET` 时启动失败。
  - `SESSION_COOKIE_HTTPONLY=True`、`SESSION_COOKIE_SAMESITE="Lax"`、`SESSION_COOKIE_SECURE` 由环境变量控制。
  - 增加响应头 `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: no-referrer`。
  - 上传大小上限 `MAX_CONTENT_LENGTH`（默认 25 MB），超过返回 `413 PAYLOAD_TOO_LARGE`。
  - `/health` 不再返回 `base`（避免 LLM endpoint 泄露）。
- **上传：**
  - 文件名、扩展名、解析、空数据均统一校验。
  - 解析失败返回 `422 INVALID_FILE`，不泄露堆栈。
  - 空数据返回 `422 EMPTY_DATA`。
- **`/ask` 与 `/insights`：**
  - 强制 `application/json`；非 JSON 返回 `400 INVALID_REQUEST`。
  - `question` 必须是非空字符串，超过 `MAX_QUESTION_LENGTH=2000` 返回 `422 QUESTION_TOO_LONG`。
  - 异常统一为 `500 ANALYSIS_ERROR`，不再泄露原始异常文本。
- **沙箱：**
  - 新增 AST 预检 `_preflight`：拒绝 import、动态执行、文件/网络访问、危险 dunder；允许受控 Pandas/NumPy/Matplotlib 分析 API。
  - 禁止生成代码调用 `savefig` 写任意路径；图表统一由 runner 内部捕获。
  - 结果文本上限 12,000 字符，图表上限 5MB。
  - 错误文案明确本地演示定位；公网部署必须叠加容器 / OS 级隔离。
- **分析引擎：**
  - LLM 代码生成失败返回稳定错误。
  - 自动重试限制 0-2 次；回灌错误/代码截断；前端不再收到内部 traceback。

### XSS Fix
- `templates/index.html`:
  - 移除 `schemaBox`、`uploadMeta`、`addCodeBlock`、`renderChips` 中的 `innerHTML`。
  - 改为 `textContent + createElement`，所有用户数据、列名、单元格、错误信息、生成代码、SQL 都按字符串处理。

### Tests
- `test_sandbox.py` 新增：
  - `__import__('os').system(...)`
  - `df.__class__` 属性访问
  - `def f(): return 1`
  - `lambda x: x`
  - `open('secret.txt').read()`
  - 超长代码
- `test_app.py` 新增：
  - 上传损坏文件 → `422 INVALID_FILE`
  - 上传空文件 → `422`
  - `/ask` 非 JSON → `400 INVALID_REQUEST`
  - `/ask` 超长问题 → `422 QUESTION_TOO_LONG`
  - `/ask` 非字符串问题 → `400`

### Docs
- 新增 `.env.example`：Flask secret、host/port、cookie、上传限制、LLM、sandbox 超时。
- 新增本 CHANGELOG。
- README 后续补充 `本地演示 vs 公网部署` 区别说明（详见 README）。

### Compatibility
- Flask 路由 `/`、`/upload`、`/ask`、`/insights`、`/chart/<name>`、`/health` 全部保留。
- 接口响应字段：`{result, chart, code, sql}` 兼容。

## [0.1.0] - 初始发布

- 上传 CSV/Excel、自然语言分析、图表、SQL 对照、自动洞察；Flask 单进程；本地单用户演示。
