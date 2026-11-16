---
goal: 支持 X 书签入库，提供增量剪枝、全量断点续抓、独立 CLI flag 与统一 Tweet 投影
created: 2026-11-13
modified: 2026-11-16
status: Completed
design: docs/design/twitter-bookmarks-ingest.md
---

# Twitter 书签入库实现计划

## 目标

在 `twitter` 模块中新增 X 书签数据入库：抓取 `Bookmarks` GraphQL 接口并写入 raw 层；把点赞和书签统一到 `twitter_tweet` 实体表，新增 `twitter_like`、`twitter_bookmark` 关系表；提供默认增量、`--full` 全量断点续抓和 `--force` 重开全量的 CLI 语义；处理限流和 queryId 失效提示。

## 约束与前提

- **CON-001**：本阶段只做入库，不做书签 Markdown 导出；`--bookmarks` 必须与 `--db-only` 同时使用。
- **CON-002**：不新增运行时依赖；使用现有 `requests`、`sqlite3`、`click`。
- **CON-003**：现有 `twitter_tweet` 行全部视为点赞；迁移 `003` 回填 `twitter_like`。
- **CON-004**：Bookmarks queryId 初始值使用 `Fy0QMy4q_aZCpkO0PnyLYw`；失效后按维护提示手工更新。
- **CON-005**：保持单账号假设；不做删除检测、多账号、官方 API。
- **CON-006**：全量断点只读取 `sync_run.scope='full'` 的 `twitter.bookmarks.page` 响应，避免增量响应污染。
- **GUD-001**：遵循现有 raw/projection/upsert 模式；新逻辑必须有单元测试。
- **GUD-002**：不 commit、不 push；实现完成后由用户决定提交和 PR。

## 实施步骤

### 阶段 1：raw 与抓取解析

完成标准：底层 helper、接口常量、Bookmarks 页面解析和抓取结果均有测试。

| Task | Status | Description | Verification Steps | Date |
| --- | --- | --- | --- | --- |
| TASK-001 | Completed | 在 `src/db/raw.py` 增加 `latest_response(connection, endpoint, *, scope=None)`：按 `sync_response.id DESC` 返回最近一条响应并解压 body；`scope` 非空时 join `sync_run` 过滤 `scope`。复用现有解压逻辑，补充 `tests/test_db_raw.py` 用例。 | `PYTHONPATH=src pytest tests/test_db_raw.py -q` | 2026-11-16 |
| TASK-002 | Completed | 在 `src/twitter/api_endpoints.py` 增加 `TWITTER_BOOKMARKS_PATH`、`TWITTER_BOOKMARKS_PAGE_SIZE = 100`、`TWITTER_BOOKMARKS_FIELD_TOGGLES`；在 `src/twitter/entity.py` 增加 `BookmarksPage`，抽取 Likes/Bookmarks 共用的 instruction/entry 解析，支持 `bookmark_timeline_v2` 和 `bookmark_timeline` 两种根路径。补充 `tests/test_twitter.py` 解析用例，确保 Likes 现有用例通过。 | `PYTHONPATH=src pytest tests/test_twitter.py -q` | 2026-11-16 |
| TASK-003 | Completed | 新建 `src/twitter/bookmark.py`：实现 `build_bookmarks_params`、`BookmarksFetch`、`get_twitter_bookmark_list`；使用 `export_runtime.http.get` 记录 `twitter.bookmarks.page`；解析 `x-rate-limit-remaining` / `x-rate-limit-reset`；覆盖 200、429、400、404、非 JSON、非 dict、缺少 `data`。补充 `tests/test_twitter.py` 与 `tests/test_raw_platforms.py` 的 endpoint 记录用例。 | `PYTHONPATH=src pytest tests/test_twitter.py tests/test_raw_platforms.py -q` | 2026-11-16 |
| TASK-004 | Completed | 在 `src/twitter/bookmark.py` 增加 `BookmarkCheckpoint` 和 `latest_bookmark_checkpoint(connection)`：按 `endpoint='twitter.bookmarks.page'`、`scope='full'` 读取最近响应；处理无响应、200 带 cursor、200 无 cursor、非 200、body 为空、非法 JSON；从 `request.params.variables.cursor` 提取请求游标。补充 `tests/test_twitter.py` 用例。 | `PYTHONPATH=src pytest tests/test_twitter.py -q` | 2026-11-16 |

#### TASK-001 执行记录
- **状态**: 已完成（2026-11-16）
- **变更摘要**: 在 raw 层新增按接口（可选 run scope）读取最新响应的 helper，并抽出共享解压函数。
- **逻辑变更**:
  - **新增**: `latest_response` 支持按 `sync_response.id` 倒序取最近一条响应，`scope` 过滤通过 join `sync_run` 实现；`_decompress_body` 统一处理缺失 body。
  - **修改**（及原因）: `iter_responses` 改用 `_decompress_body`，避免两处重复解压逻辑。
- **相关代码**: `src/db/raw.py` 的 `latest_response`、`_decompress_body`；`tests/test_db_raw.py`。
- **验证结果**: `PYTHONPATH=src .venv/bin/pytest tests/test_db_raw.py -q`，8 个用例通过。

#### TASK-002 执行记录
- **状态**: 已完成（2026-11-16）
- **变更摘要**: 增加 Bookmarks 接口常量和页面模型，并把 Likes/Bookmarks 的时间线解析合并为共享函数。
- **逻辑变更**:
  - **新增**: `TWITTER_BOOKMARKS_PATH`、`TWITTER_BOOKMARKS_PAGE_SIZE`、`TWITTER_BOOKMARKS_FIELD_TOGGLES`；`BookmarksPage` 支持 `bookmark_timeline_v2` 与 `bookmark_timeline` 两种根路径。
  - **修改**（及原因）: `LikesPage.from_dict` 改用 `_parse_timeline_instructions`；去掉 `entryId` 必须以 `tweet-` 开头的限制，改为只跳过已知非内容前缀，避免上游改 entry 前缀后丢 Tweet。
- **相关代码**: `src/twitter/api_endpoints.py`、`src/twitter/entity.py`、`tests/test_twitter.py`。
- **验证结果**: `PYTHONPATH=src .venv/bin/pytest tests/test_twitter.py -q`，37 个用例通过（含新增 Bookmarks 与无前缀 entry 用例）。

#### TASK-003 执行记录
- **状态**: 已完成（2026-11-16）
- **变更摘要**: 新增 Bookmarks 抓取模块，统一构造请求、记录 raw 响应并返回带状态码/限流信息的抓取结果。
- **逻辑变更**:
  - **新增**: `build_bookmarks_params`（无 userId、含 `withV2Timeline`）、`BookmarksFetch`、`get_twitter_bookmark_list` 和 queryId 维护提示 helper；通过 `export_runtime.http.get` 记录 `twitter.bookmarks.page`。
  - **修改**（及原因）: 无；新文件独立承接 Bookmarks 逻辑，Likes 流程保持不变。
- **相关代码**: `src/twitter/bookmark.py`、`tests/test_twitter.py`、`tests/test_raw_platforms.py`。
- **验证结果**: `PYTHONPATH=src .venv/bin/pytest tests/test_twitter.py tests/test_raw_platforms.py -q`，68 个用例通过。

#### TASK-004 执行记录
- **状态**: 已完成（2026-11-16）
- **变更摘要**: 从 full scope 的 raw 响应推导书签全量断点，支持失败请求按原游标重试。
- **逻辑变更**:
  - **新增**: `BookmarkCheckpoint(cursor, in_progress)`、`latest_bookmark_checkpoint`、请求游标提取 helper；非 200、body 缺失、非法 JSON 或结构异常时保留请求游标并标记未完成。
  - **修改**（及原因）: 无；断点完全从 raw 层推导，不新增状态表。
- **相关代码**: `src/twitter/bookmark.py`、`tests/test_twitter.py`。
- **验证结果**: `PYTHONPATH=src .venv/bin/pytest tests/test_twitter.py -q`，54 个用例通过。

### 阶段 2：数据库与投影

完成标准：迁移、关系表、投影回放和迁移回填测试通过。

| Task | Status | Description | Verification Steps | Date |
| --- | --- | --- | --- | --- |
| TASK-005 | Completed | 新增 `src/db/migrations/003_twitter_sources.sql`：创建 `twitter_like`、`twitter_bookmark`，从 `twitter_tweet` 回填点赞；更新 `tests/test_db_schema.py` 的 `user_version=3`、表断言和 v2→v3 回填用例；更新 `tests/test_projection_schema.py` 的 `PROJECTION_TABLES`、`PLATFORM_TIME_COLUMNS` 和 `user_version=3` 断言。 | `PYTHONPATH=src pytest tests/test_db_schema.py tests/test_projection_schema.py -q` | 2026-11-16 |
| TASK-006 | Completed | 更新 `src/db/projections/twitter.py`：Likes 写入 `twitter_tweet` + `twitter_like`；Bookmarks 写入 `twitter_tweet` + `twitter_bookmark`；`DELETE_ORDER` 改为关系表优先；`known_tweet_ids` 查询 `twitter_like`，新增 `known_bookmark_ids`；重建顺序为先 likes 后 bookmarks。更新 `tests/test_projection_twitter.py`（点赞/书签/重叠/幂等/错误负载）和 `tests/test_cli_db.py` 中直接插入 `twitter_tweet` 的点赞剪枝 fixture，改为同时插入 `twitter_like`。 | `PYTHONPATH=src pytest tests/test_projection_twitter.py tests/test_cli_db.py -q` | 2026-11-16 |

#### TASK-005 执行记录
- **状态**: 已完成（2026-11-16）
- **变更摘要**: 新增迁移 `003` 建立 Twitter 点赞/书签关系表，并把现有 Tweet 行回填为点赞。
- **逻辑变更**:
  - **新增**: `twitter_like`、`twitter_bookmark` 两张 STRICT 关系表，均以 `tweet_id` 外键引用 `twitter_tweet`；迁移内回填 `twitter_like`。
  - **修改**（及原因）: schema 测试的 `user_version` 断言升到 3，并补充 v2→v3 回填用例；投影 schema 测试登记两张新表，时间列集合为空。
- **相关代码**: `src/db/migrations/003_twitter_sources.sql`、`tests/test_db_schema.py`、`tests/test_projection_schema.py`。
- **验证结果**: `PYTHONPATH=src .venv/bin/pytest tests/test_db_schema.py tests/test_projection_schema.py -q`，18 个用例通过。

#### TASK-006 执行记录
- **状态**: 已完成（2026-11-16）
- **变更摘要**: 投影层改为共享 Tweet 实体 + 点赞/书签关系表，并分别维护两种来源的剪枝查询。
- **逻辑变更**:
  - **新增**: `known_bookmark_ids`；Bookmarks 响应回放到 `twitter_tweet` + `twitter_bookmark`；通用的 `_parse_page` / `_upsert_page`。
  - **修改**（及原因）: `known_tweet_ids` 改查 `twitter_like`，避免书签行污染点赞剪枝；`DELETE_ORDER` 改为先删关系表再删 `twitter_tweet`；重建固定先 likes 后 bookmarks，借助 `response_id` 守卫防止旧响应覆盖新内容。
- **相关代码**: `src/db/projections/twitter.py`、`tests/test_projection_twitter.py`、`tests/test_cli_db.py`。
- **验证结果**: `PYTHONPATH=src .venv/bin/pytest tests/test_projection_twitter.py tests/test_cli_db.py -q`，68 个用例通过。

### 阶段 3：入库流程与 CLI

完成标准：三种模式、限流停止、断点续抓、queryId 提示和 CLI/验活测试通过。

| Task | Status | Description | Verification Steps | Date |
| --- | --- | --- | --- | --- |
| TASK-007 | Completed | 在 `src/twitter/exporter.py` 增加 `ingest_bookmarks(full=False, force=False, max_pages=None)`：默认增量从顶部开始并整页剪枝；`--full` 读取断点、禁用整页停止；`--force` 隐含 full 并忽略断点；处理 429/400/404/401/403/5xx、空页、游标不推进、`--max-pages`；限流时打印 `x-rate-limit-reset`；queryId 失效打印维护提示。补充 `tests/test_twitter.py` 用例，覆盖增量停止、全量续抓、force 重来、429、400、404、游标停滞。 | `PYTHONPATH=src pytest tests/test_twitter.py -q` | 2026-11-16 |
| TASK-008 | Completed | 在 `src/app/cli.py` 的 `twitter` 命令增加 `--bookmarks`、`--full`；`--bookmarks` 非 `--db-only` 或 `--full` 缺少 `--bookmarks` 时抛 `UsageError`；书签运行调用 `run_action('twitter', 'bookmarks', 'full' if full or force else 'incremental', ...)`。在 `src/app/credential_guard.py` 增加 `probe_twitter_bookmarks_credentials`，请求 Bookmarks `count=1`，区分 valid/invalid/unknown。补充 `tests/test_cli_db.py`、`tests/test_credential_guard.py` 和 `tests/test_twitter.py` 用例，确保默认点赞流程不变。 | `PYTHONPATH=src pytest tests/test_cli_db.py tests/test_credential_guard.py tests/test_twitter.py -q` | 2026-11-16 |

#### TASK-007 执行记录
- **状态**: 已完成（2026-11-16）
- **变更摘要**: 新增书签入库流程，支持默认增量、全量断点续抓、强制重来及限流/错误停止。
- **逻辑变更**:
  - **新增**: `ingest_bookmarks`、书签错误打印与限流提示 helper；增量模式按整页已存在停止，全量使用 checkpoint 且不触发整页停止，force 忽略断点；连续 3 页空页、游标停滞、页数上限、429/400/404/401/403/5xx 均标记 partial。
  - **修改**（及原因）: 复用现有 `TWITTER_MAX_PAGES` 和 `mark_run_partial`，不新增抓取抽象；Likes 导出流程保持不变。
- **相关代码**: `src/twitter/exporter.py`、`tests/test_twitter.py`。
- **验证结果**: `PYTHONPATH=src .venv/bin/pytest tests/test_twitter.py -q`，65 个用例通过。

#### TASK-008 执行记录
- **状态**: 已完成（2026-11-16）
- **变更摘要**: CLI 增加 `--bookmarks` / `--full`，书签模式使用独立验活并写入正确的 run operation/scope。
- **逻辑变更**:
  - **新增**: `probe_twitter_bookmarks_credentials` 请求 Bookmarks `count=1`；200 有 data 判 valid，401/403 判 invalid，400/404 判 unknown 且附带 queryId 维护提示；CLI 书签分支调用 `ingest_bookmarks`。
  - **修改**（及原因）: `twitter` 命令拒绝非 `--db-only` 的 `--bookmarks` 和缺少 `--bookmarks` 的 `--full`；默认点赞路径保持原有验活和导出调用不变。
- **相关代码**: `src/app/cli.py`、`src/app/credential_guard.py`、`tests/test_cli_db.py`、`tests/test_credential_guard.py`。
- **验证结果**: `PYTHONPATH=src .venv/bin/pytest tests/test_cli_db.py tests/test_credential_guard.py tests/test_twitter.py -q`，180 个用例通过。

### 阶段 4：文档与全量验证

完成标准：用户文档、内部约定和设计文档同步，全量测试和 Ruff 通过。

| Task | Status | Description | Verification Steps | Date |
| --- | --- | --- | --- | --- |
| TASK-009 | Completed | 更新 `docs/usages/twitter.md`（点赞/书签两种用法、三种模式、限流与续抓、queryId 维护、示例）；更新 `docs/usages/db.md`（`twitter` 三张表、重建顺序）；更新 `docs/design/projection-layer.md` 的 Twitter 表和重建顺序；更新 `docs/design/incremental-pruning.md` 的书签模式说明；更新 `AGENTS.md` 的 CLI 契约、投影表、增量/断点行为；必要时更新 `README.md`。 | `rg -n "twitter_like|twitter_bookmark" docs/usages/db.md docs/design/projection-layer.md docs/design/incremental-pruning.md AGENTS.md`；`rg -n -- "--bookmarks|--full" docs/usages/twitter.md AGENTS.md README.md` | 2026-11-16 |
| TASK-010 | Completed | 运行全量自动化验证；有 Cookie 时执行手工冒烟：首轮 `eto --db-only twitter --bookmarks --full --max-pages 1`，再次执行确认从断点继续；再执行 `eto --db-only twitter --bookmarks --max-pages 1` 确认增量剪枝。无 Cookie 时记录“手工冒烟未执行”，不阻塞自动化测试。 | `PYTHONPATH=src pytest tests -q`；`ruff check src tests`；`ruff format --check src tests`；手工命令见描述 | 2026-11-16 |

#### TASK-009 执行记录
- **状态**: 已完成（2026-11-16）
- **变更摘要**: 同步书签入库的用户文档、数据库说明、设计文档和仓库约定。
- **逻辑变更**:
  - **新增**: `docs/usages/twitter.md` 增加 `--bookmarks` / `--full` 用法、三种模式、限流/断点/queryId 维护说明；`README.md` 增加书签入库示例。
  - **修改**（及原因）: `docs/usages/db.md` 登记三张 Twitter 表与回放顺序；`projection-layer.md` 更新 Twitter 表结构与重建顺序；`incremental-pruning.md` 增加书签模式；`AGENTS.md` 同步 CLI 契约、投影与断点行为。
- **相关代码**: `docs/usages/twitter.md`、`docs/usages/db.md`、`docs/design/projection-layer.md`、`docs/design/incremental-pruning.md`、`AGENTS.md`、`README.md`。
- **验证结果**: 两条 `rg` 检查均命中三张表名、`--bookmarks` 和 `--full`。

#### TASK-010 执行记录
- **状态**: 已完成（2026-11-16）
- **变更摘要**: 完成全量自动化验证与真实 Cookie 冒烟，确认三种书签模式行为符合设计。
- **逻辑变更**:
  - **新增**: 无代码变更；补充本执行记录与计划最终状态。
  - **修改**（及原因）: 无。
- **相关代码**: 全仓库验证；手工冒烟使用 `/tmp/opencode/eto-twitter-smoke.db`，结束后已删除。
- **验证结果**: `PYTHONPATH=src pytest tests -q` 为 409 passed、2 skipped；`ruff check src tests` 与 `ruff format --check src tests` 通过。手工冒烟：首轮 full 抓取 95 条书签后因 `--max-pages 1` 标记 partial；第二轮 full 从断点继续再抓 95 条；第三轮增量因整页已存在停止；三次 run 的 operation 均为 `bookmarks`，scope 分别为 `full`、`full`、`incremental`，状态均为 `partial`，三张表计数为 tweet=190、like=0、bookmark=190。
- **后续自测修复（2026-11-16）**: 真实全量抓取发现 X 会返回只有 cursor、bottom cursor 与请求 cursor 相同的尾部空页；原逻辑误判为游标停滞并永久保留断点。现已改为正常结束且不持久化该游标。修复后全量 22 个响应、1917 条书签，run 为 `success`；随后 `--full --max-pages 1` 从头开始，增量模式仍能整页剪枝。

## 涉及文件

- **FILE-001**：`src/db/migrations/003_twitter_sources.sql` — 新增 `twitter_like`、`twitter_bookmark`，回填点赞。
- **FILE-002**：`src/db/raw.py` — 新增 `latest_response`。
- **FILE-003**：`src/db/projections/twitter.py` — 共享 Tweet 实体、点赞/书签关系回放、剪枝查询。
- **FILE-004**：`src/twitter/api_endpoints.py` — Bookmarks queryId、分页大小、field toggles。
- **FILE-005**：`src/twitter/entity.py` — `BookmarksPage` 与共用 timeline 解析。
- **FILE-006**：`src/twitter/bookmark.py` — 新文件，Bookmarks 请求、结果、断点。
- **FILE-007**：`src/twitter/exporter.py` — `ingest_bookmarks` 三种模式。
- **FILE-008**：`src/app/cli.py` — `--bookmarks`、`--full`。
- **FILE-009**：`src/app/credential_guard.py` — 书签独立验活。
- **FILE-010**：`tests/test_db_raw.py` — `latest_response` 测试。
- **FILE-011**：`tests/test_db_schema.py` — `user_version=3`、迁移回填。
- **FILE-012**：`tests/test_projection_schema.py` — 新投影表断言。
- **FILE-013**：`tests/test_projection_twitter.py` — 点赞/书签投影测试。
- **FILE-014**：`tests/test_twitter.py` — 解析、抓取、断点、入库模式测试。
- **FILE-015**：`tests/test_cli_db.py` — CLI 组合、剪枝 fixture。
- **FILE-016**：`tests/test_credential_guard.py` — 书签验活测试。
- **FILE-017**：`tests/test_raw_platforms.py` — bookmarks endpoint 记录测试。
- **FILE-018**：`docs/usages/twitter.md` — 用户用法。
- **FILE-019**：`docs/usages/db.md` — 投影表说明。
- **FILE-020**：`docs/design/projection-layer.md` — Twitter 表与重建顺序。
- **FILE-021**：`docs/design/incremental-pruning.md` — 书签模式说明。
- **FILE-022**：`AGENTS.md` — CLI 契约与内部行为。
- **FILE-023**：`README.md` — 必要时补充书签入库说明。

## 测试与验证

- **TEST-001**：`PYTHONPATH=src pytest tests/test_db_raw.py -q`
- **TEST-002**：`PYTHONPATH=src pytest tests/test_db_schema.py tests/test_projection_schema.py -q`
- **TEST-003**：`PYTHONPATH=src pytest tests/test_projection_twitter.py tests/test_cli_db.py -q`
- **TEST-004**：`PYTHONPATH=src pytest tests/test_twitter.py tests/test_raw_platforms.py -q`
- **TEST-005**：`PYTHONPATH=src pytest tests/test_credential_guard.py -q`
- **TEST-006**：`PYTHONPATH=src pytest tests -q`
- **TEST-007**：`ruff check src tests`
- **TEST-008**：`ruff format --check src tests`

## 风险与遗留

- **RISK-001**：内部 Bookmarks 限流数值未知；以响应头和 429 为准，首次全量可能需要多轮。
- **RISK-002**：queryId 轮换必须手工更新；测试无法覆盖真实接口。
- **RISK-003**：断点游标可能过期；全量模式提示 `--force`，不自动回退。
- **RISK-004**：全量轮次期间新增书签不会立即入库，轮次结束后由增量补齐。
- **RISK-005**：无书签时间/顺序，投影层不能按收藏时间排序。
- **RISK-006**：不做删除检测；取消书签的旧行保留。
- **RISK-007**：迁移回填假设现有 `twitter_tweet` 全部是点赞。
- **RISK-008**：`--full` 的 success 可能是恢复型轮次，不表示单次完整观察；将来做删除检测需额外标记。
- **RISK-009**：`count=100` 若被上游忽略，只退化为更小页，不影响正确性。
