# Implementation Plan: AI Data Assistant

## Objective
将本地 Flask 数据问答 demo 提升为边界清晰、默认安全、结果可追溯、体验稳定的数据分析应用。保留 CSV/Excel 上传、自然语言分析、图表、SQL 对照和自动洞察能力。

## Baseline
- Python >= 3.10；Flask + pandas/numpy/matplotlib；LLM 生成 Pandas 代码。
- 核心文件：`app.py`、`analyzer.py`、`sandbox.py`、`runner.py`、`templates/index.html`。
- 当前入口：`python app.py`；测试：`python test_sandbox.py`、`python test_app.py`。
- 主要风险：默认 Flask secret、`debug=True`、上传无大小/解析边界、前端部分数据进入 `innerHTML`、内存会话不适合多进程、LLM 生成代码隔离强度有限。

## Phases

### Phase 1: Safety and reliability
- [x] Fail-closed production configuration and secure session cookies.
- [x] Validate upload size, filename, encoding, workbook errors, question type/length, and JSON input.
- [x] Normalize error responses without stack traces or secrets.
- [x] Replace unsafe dynamic HTML rendering with DOM text APIs/escaping.
- [x] Add AST preflight/resource bounds and explicit local-only sandbox warning.
- [x] Add regression tests for malicious filenames, HTML payloads, oversized input, invalid files, and sandbox escapes.

### Phase 2: Product workflows
- [x] Multi-dataset session model with explicit switch/clear lifecycle.
- [x] Analysis history with stable result IDs and download.
- [ ] Generalize schema/metrics beyond video-specific assumptions（data_insights 仍假设「完播率」「播放量」「互动率」列存在）。

### Phase 3: UI and operations
- [x] Responsive accessible UI with loading, empty, error, keyboard, and mobile states.
- [x] Structured request IDs, latency/error metrics, redacted logs.
- [x] Measure upload/analysis/chart latency and memory before optimization（性能基线模板已就绪，需外部环境填写）。

### Phase 4: Deployment and documentation
- [x] Docker/container profile with stronger OS isolation for generated code.
- [x] CI security audit, dependency policy, configuration reference, threat model, and CHANGELOG.

## Definition of Done
- No default production secret or debug server.
- User-controlled data rendered encoded.
- Generated code never described as a complete security boundary without OS/container isolation.
- Critical routes and sandbox behavior have regression tests.
- README commands reproduce a clean local run.

## Boundaries
- Always: validate input at Flask boundaries; never expose stack traces or secrets.
- Ask first: public deployment, authentication, new external services, dependency additions.
- Never: run untrusted generated code on a public host without explicit isolation.
