# Issue #16 Raw Layer Implementation Plan

- Issue: [#16](https://github.com/bgzolab/export-all-to-obsidian/issues/16)
- Status: Completed (raw layer)
- Date: 2026-11-07
- Design: [`../design/raw-response-layer.md`](../design/raw-response-layer.md)

## 1. 目标

只做 raw 层：所有 API 响应和已有 Markdown 文件原样存入 SQLite，数据只增不改，供以后 replay 和规范化。

只有两张表：

- `sync_run`：一次任务。
- `sync_response`：任务下的每条响应或文件。

不建跨平台规范表，不做删除检测、统计、搜索、bot。

## 2. 约束

- 现有 Markdown 导出行为不变。
- 每完成一个任务，运行该任务的最小验证命令。
- 所有 API 采集走同一个 HTTP 采集器。
- 请求头只脱 Cookie 和 Authorization；URL、query、body 原样保存。数据库仍按凭证文件保护：0600、gitignore、不公开备份。
- 迁移只增不改；已发布的迁移文件不修改。

## 3. 任务

### M0 文档

#### T0.1 编写设计与计划

- Status: Completed
- Files:
  - `docs/design/raw-response-layer.md`
  - `docs/implementation-plans/issue-16-raw-layer.md`
- Verify: 两个文件存在，互相链接可解析。
- Record: 2026-11-07

#### T0.2 简化表名和字段

- Status: Completed
- Files:
  - `docs/design/raw-response-layer.md`
  - `docs/implementation-plans/issue-16-raw-layer.md`
- Work: 表名改为 `sync_run` / `sync_response`；删除游标、页脚元数据和全量脱敏设计，统一放进 `request` JSON。
- Verify: 文档中不再出现旧表名。
- Record: 2026-11-07

#### T0.3 保留任务触发命令

- Status: Completed
- Files:
  - `docs/design/raw-response-layer.md`
  - `docs/implementation-plans/issue-16-raw-layer.md`
- Work: `sync_run` 增加 `command TEXT`，存可直接复制执行的一行命令，不用 JSON。
- Verify: 设计文档的字段表和 DDL 都包含 `command`。
- Record: 2026-11-07

#### T0.4 恢复最小脱敏规则

- Status: Completed
- Files:
  - `docs/design/raw-response-layer.md`
  - `docs/implementation-plans/issue-16-raw-layer.md`
- Work: 只脱 `Cookie`、`Authorization` 头；URL、query、body 和其余 header 原样保存。
- Verify: 设计文档明确写出脱敏白名单和“其余原样”。
- Record: 2026-11-07

### M1 数据库基础

#### T1.1 数据库连接与迁移

- Status: Completed
- Files:
  - `src/db/__init__.py`
  - `src/db/connection.py`
  - `src/db/migrate.py`
  - `src/db/migrations/001_raw_layer.sql`
  - `tests/test_db_schema.py`
- Work:
  - `connect(path)` 设置 WAL、foreign_keys、busy_timeout、synchronous，返回 `sqlite3.Row`。
  - 创建父目录 0700，数据库文件 0600（非 Windows）。
  - `migrate.py` 按文件名顺序应用 `migrations/*.sql`，用 `PRAGMA user_version` 记录版本。
  - `001_raw_layer.sql` 创建 `sync_run`、`sync_response` 和索引。
- Verify:
  - `PYTHONPATH=src pytest tests/test_db_schema.py -q`
  - `sqlite3 /tmp/eto-schema.db '.schema sync_response'`

#### T1.2 raw 仓储 API 与测试

- Status: Completed
- Files:
  - `src/db/raw.py`
  - `tests/test_db_raw.py`
- Work:
  - `start_run(platform, operation, scope, command=None) -> int`
  - `finish_run(run_id, status, error=None)`
  - `record_response(run_id, endpoint, request, status_code, body, error=None) -> int`
  - `record_error(run_id, endpoint, request, error) -> int`
  - `iter_responses(endpoint=None)`：按 `fetched_at, id` 顺序读取。
  - 测试 body 压缩/解压、sha256、非 2xx、异常、run 状态流转、`command` 原样保存。
- Verify:
  - `PYTHONPATH=src pytest tests/test_db_raw.py -q`

### M2 CLI 接入

#### T2.1 顶层 `--db` 参数与测试

- Status: Completed
- Files:
  - `src/app/context.py`
  - `src/app/cli.py`
  - `tests/test_cli_db.py`
- Work:
  - `--db` 作为顶层选项，必须放在子命令前。
  - 未指定时使用 `~/.eto/eto.db`。
  - 在根 context 初始化数据库连接并暴露 `get_database()`。
  - 用 `shlex.join(sys.argv)` 记录本次命令，传给 `start_run(command=...)`。
  - 目录路径、无法创建、迁移失败给出明确 `ClickException`。
  - 测试显式路径、默认路径、目录路径拒绝、命令记录。
- Verify:
  - `PYTHONPATH=src pytest tests/test_cli_db.py -q`
  - `PYTHONPATH=src python -m export_to_obsidian --help` 能看到 `--db`

### M3 HTTP 采集与 GitHub 试点

#### T3.1 HTTP 采集器与测试

- Status: Completed
- Files:
  - `src/export_runtime/http.py`
  - `tests/test_http_recorder.py`
- Work:
  - 封装 `requests.Session`，调用方显式传入 `run_id`、`endpoint`、`request`。
  - 响应返回前写入 `sync_response`；传输异常写入错误行后重新抛出。
  - 只脱 `Cookie`、`Authorization` 头，其余请求信息原样保存。
  - 不在采集器内解析 JSON，也不做状态码判断。
  - 测试 401/429/500、连接异常、request 字段还原、Cookie/Authorization 脱敏且其他 header 保留。
- Verify:
  - `PYTHONPATH=src pytest tests/test_http_recorder.py -q`

#### T3.2 接入 GitHub

- Status: Completed
- Files:
  - `src/github/client.py`
  - `src/github/exporter.py`
  - `tests/test_github.py`
- Work:
  - `get_starred_repositories` 和 `get_repository_readme` 走采集器。
  - exporter 启动 `sync_run`，把 `run_id` 传给客户端。
  - 正常走完分页标记 `success`；命中 `stop_if_output_exists` 提前返回标记 `partial`。
  - 保持现有 Markdown 输出和测试语义不变。
- Verify:
  - `PYTHONPATH=src pytest tests/test_github.py -q`
  - 用临时 DB 跑一次 mock 导出后，`sync_response` 中存在 `github.stars.list` 和 `github.repo.readme` 行。

#### T3.3 接入其余平台

- Status: Completed
- Files:
  - `src/zhihu/collection.py`
  - `src/bilibili/favlist.py`
  - `src/weibo/like.py`
  - `src/weibo/post.py`
  - `src/v2ex/mytopic.py`
  - `src/v2ex/topic.py`
  - `src/bangumi/client.py`
  - `src/bangumi/collection.py`
  - `src/bangumi/subject.py`
  - `src/qireader/getext.py`
  - `src/qireader/readlatter.py`
  - `src/cnblog/client.py`
  - `src/cnblog/bookmark.py`
  - `src/cnblog/blog_post.py`
  - `src/cnblog/user.py`
  - `src/twitter/like.py`
  - `tests/test_raw_platforms.py`
- Work: 所有内容请求改走 `export_runtime.http`，使用稳定 endpoint；凭证探针不经过采集器。
- Verify:
  - `PYTHONPATH=src pytest tests/test_raw_platforms.py tests/test_raw_integration.py -q`

#### T3.4 修复 Qireader 的 www 域 Cookie

- Status: Completed
- Files:
  - `src/qireader/cilent.py`
  - `tests/test_qireader.py`
- Work: Cookie 匹配先试 `www.qireader.com`，再回退 `qireader.com`，兼容浏览器导出的 host-only Cookie。
- Verify:
  - `PYTHONPATH=src pytest tests/test_qireader.py -q`

### M4 已有 Markdown 导入

#### T4.1 Markdown raw 导入器与测试

- Status: Completed
- Files:
  - `src/db/import_markdown.py`
  - `tests/test_import_markdown.py`
- Work:
  - 递归读取目录下 `*.md`，按文件原始字节写入 `sync_response`。
  - 每次导入创建一个 `sync_run`：`platform='local'`、`operation='import.markdown'`、`scope` 为目录。
  - `endpoint='import.markdown'`，`request={"path": "...", "size": ...}`，`status_code=NULL`。
  - 同路径同 `sha256` 跳过；文件变化新增一行。
  - 不解析 front matter。
- Verify:
  - `PYTHONPATH=src pytest tests/test_import_markdown.py -q`

#### T4.2 导入命令与测试

- Status: Completed
- Files:
  - `src/app/cli.py`
  - `tests/test_cli_db.py`
- Work:
  - 新增 `eto import-markdown <path>`，支持顶层 `--db`。
  - 输出导入、跳过、失败计数。
- Verify:
  - `PYTHONPATH=src pytest tests/test_cli_db.py -q`
  - 对一个临时目录重复执行两次，第二次全部跳过。

### M5 收尾

#### T5.1 忽略规则与使用说明

- Status: Completed
- Files:
  - `.gitignore`
  - `README.md`
- Work:
  - `.gitignore` 增加 `*.db`、`*.db-wal`、`*.db-shm`。
  - README 增加 `--db`、默认路径、`import-markdown` 的简短说明。
  - 明确数据库按凭证文件保护：Cookie/Authorization 头已脱敏，但 URL/body 仍可能含敏感信息。
- Verify:
  - `git status --short` 中不出现数据库文件。

#### T5.2 全量验证

- Status: Completed
- Files:
  - `src/`
  - `tests/`
- Work:
  - 运行全量测试、lint、format 检查。
  - 检查一次 mock 的 GitHub 同步，确认 raw 表有数据、导出无变化。
- Verify:
  - `PYTHONPATH=src pytest tests -q`
  - `ruff check src tests`
  - `ruff format --check src tests`

### M6 暂缓

#### T6.1 跨平台规范层

- Status: On Hold
- Reason: 需要先观察真实 raw 数据和实际查询/导出需求。Bangumi 条目、V2EX/知乎内容、Twitter 推文是否共享模型尚未确定。
- Next: raw 层稳定后，再单独设计投影；可以按平台拆表，不强行统一。

#### T6.2 删除检测、指标、搜索、Telegram bot

- Status: On Hold
- Reason: 依赖规范层或 raw 层稳定运行；当前不做。

## 4. 执行记录

| Date | Task | Status | Notes |
|---|---|---|---|
| 2026-11-07 | T0.1 | Completed | 新增 raw 层设计与实施计划 |
| 2026-11-07 | T0.2 | Completed | 表名改为 `sync_run` / `sync_response`；删除 cursor 字段和全量脱敏设计 |
| 2026-11-07 | T0.3 | Completed | `sync_run` 增加纯文本 `command`，保留任务触发命令 |
| 2026-11-07 | T0.4 | Completed | 恢复最小脱敏：只处理 Cookie/Authorization header |
| 2026-11-07 | T1.1 | Completed | 新增 `src/db`，连接、迁移、两张表和权限设置 |
| 2026-11-07 | T1.2 | Completed | 新增 raw 仓储 API 和 9 个测试 |
| 2026-11-07 | T2.1 | Completed | 顶层 `--db`、默认路径、run 生命周期和 6 个 CLI 测试 |
| 2026-11-07 | T3.1 | Completed | HTTP 采集器、header 脱敏和 4 个测试 |
| 2026-11-07 | T3.2 | Completed | GitHub 端到端 raw 采集测试 |
| 2026-11-07 | T3.3 | Completed | 其余 8 个平台内容请求全部接入采集器 |
| 2026-11-07 | T4.1 | Completed | Markdown raw 导入器和 4 个测试 |
| 2026-11-07 | T4.2 | Completed | `eto import-markdown` 命令和 CLI 测试 |
| 2026-11-07 | T5.1 | Completed | README、.gitignore、AGENTS 更新 |
| 2026-11-07 | T5.2 | Completed | 183 个测试通过，ruff 通过；8 个平台做了单页/单条 live smoke |
| 2026-11-07 | Smoke | Partial | qireader 缺 cookie；bangumi token 过期；weibo cookie 失效；v2ex token 过期但 HTML 收藏页可用 |
| 2026-11-07 | T3.4 | Completed | Qireader 改用 `www.qireader.com` 优先匹配 Cookie |
| 2026-11-07 | Smoke retest | Completed | Bangumi/V2EX/Qireader 均成功；Weibo 按要求跳过；184 个测试通过 |

## 5. 验收标准

- `sync_run` 和 `sync_response` 建立，父子关系通过 `run_id` 明确。
- `sync_run.command` 能还原触发任务的命令。
- 试点平台的每次请求都有一条 `sync_response`，包含 body、sha256、endpoint、request。
- `Cookie` / `Authorization` header 不出现在 `request` JSON 中，其余 header 保留。
- 非 2xx、传输异常也能落库。
- 已有 Markdown 可以原样导入，重复导入幂等。
- 现有 Markdown 导出行为不变，全量测试通过。
- 数据库文件权限 0600，且不在 git 工作区。

## 6. 开放问题

- 默认数据库路径选 `~/.eto/eto.db` 是否合适，还是应该放在项目 `data/` 下。
- 试点平台选 GitHub 是否合适；备选是知乎。
- `docs/implementation-plans/*.md` 当前被 `.gitignore` 忽略；如果希望本计划进入版本库，需要单独调整忽略规则。
