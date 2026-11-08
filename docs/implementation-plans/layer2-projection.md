# Layer 2 Projection Implementation Plan

- Issue: [#16](https://github.com/bgzolab/export-all-to-obsidian/issues/16)
- Design: [projection-layer.md](../design/projection-layer.md)
- Branch: `feature/db-stage-2-projection-layer`
- Status: Completed

## Goal

从 raw 层重建平台实体表，先交付 Bangumi pilot，再按平台逐个补齐解析器。
表结构一次固定，解析器分阶段实现。

## Tasks

### T1. 投影层迁移

- Status: Completed
- Files: `src/db/migrations/002_projection_layer.sql`
- Work:
  - 创建设计文档第 3 节的 17 张表、索引，全部使用 `STRICT`。
  - 每张表包含 `response_id`、`db_created_at`、`db_updated_at`。
  - 平台时间字段按原名、原类型保留，不造 `fav_at`。
  - 外键指向 `sync_response(id)`；`sync_run` 通过 `sync_response.run_id` 关联。
- Verify:
  - 空库和已有 layer 1 数据的库都能迁移到 `PRAGMA user_version = 2`。
  - `PYTHONPATH=src pytest tests/test_db_schema.py -q`。

### T2. Schema 测试更新

- Status: Completed
- Files: `tests/test_db_schema.py`, `tests/test_projection_schema.py`
- Work:
  - 把现有 `user_version == 1` 断言更新到 2。
  - 断言 17 张投影表和关键索引存在。
  - 断言每张表都有 `response_id` / `db_created_at` / `db_updated_at`。
  - 断言平台时间字段存在（如 `github_star.created_at`、`v2ex_topic.last_touched`），
    且没有 `fav_at` / `raw_json`。
  - 断言 JSON `CHECK`、`STRICT` 类型、自然键唯一约束、外键约束会拒绝非法写入。
- Verify: `PYTHONPATH=src pytest tests/test_db_schema.py tests/test_projection_schema.py -q`。

### T3. 重建基础设施

- Status: Completed
- Files: `src/db/projections/__init__.py`, `src/db/projections/_upsert.py`
- Work:
  - `rebuild_platform(connection, platform)` 分发器。
  - 平台级事务：删除投影行 -> 按固定接口顺序回放 -> upsert。
  - `upsert` 更新业务列和 `response_id`；插入写 `db_created_at` / `db_updated_at`，
    更新只刷新 `db_updated_at`。
  - 传输错误和非 200 响应跳过并计数；200 响应解析失败回滚并抛出带 endpoint /
    response id 的异常。
  - 删除顺序：子表先于父表。
- Verify: 单元测试覆盖 upsert 插入、更新、旧响应不覆盖新响应、200 异常回滚、
  传输错误/非 200 跳过计数、重建两次除 `db_*` 外逐列一致。

### T4. Bangumi pilot

- Status: Completed
- Files: `src/db/projections/bangumi.py`, `tests/test_projection_bangumi.py`
- Work:
  - 解析 `bangumi.collections.page` -> `bangumi_collection`。
  - 解析 `bangumi.subject.detail` -> `bangumi_subject`。
  - 解析 `bangumi.subject.characters` -> 辅助更新
    `characters_json` / `characters_response_id`，不覆盖主溯源列。
  - 平台时间 `collection.updated_at`、`subject.date` 原样保留。
  - `collection_id` 缺失时写 `NULL`，不写 0。
- Verify:
  - 用固定 raw fixture 连续 `rebuild_platform` 两次，除 `db_*` 外逐列结果相等。
  - 坏 JSON 触发回滚，投影表行数不变。
  - 角色更新后 `response_id` 仍指向 subject detail，`db_updated_at` 刷新。

### T5. `--db-only` 模式

- Status: Completed
- Files: `src/app/cli.py`, `src/app/context.py`,
  `src/export_runtime/exporter_support.py`, `src/export_runtime/index_writer.py`,
  `tests/test_cli_db.py`
- Work:
  - 增加顶层 `--db-only` flag；`initialize_context` 写入 `ctx.obj['db_only']`。
  - 增加 `is_db_only()`，供 exporter_support 查询；IndexWriter 不反向依赖 app.context，
    由 `initialize_context` 传入 `enabled` 开关。
  - `-o` / `-t` 改为可选；非 db-only 时缺失报 `UsageError`。
  - db-only 下把缺失的 `output` / `template` 归一为空字符串，避免 exporter 里出现 None 路径。
  - `--index-file` + `--db-only` 直接报错；`--force` / `--prefix` 在 db-only 下忽略。
  - 输出抑制集中到 `exporter_support`：`stop_if_output_exists` 返回 False，
    写文件 / 写索引函数直接返回。
  - `IndexWriter` 增加 `enabled` 开关，db-only 下 `flush` 不写文件、不打印空索引。
  - Bangumi 的 `write_subject_markdown` 要跳过模板读取、文件存在检查和写入。
  - GitHub 不读取模板；`-t` 在 db-only 下可为空。
  - 在 `sync_run` 内、抓取结束后调用 `rebuild_platform`；平台无解析器时打印提示并保留 raw。
  - 投影失败标记 run 为 `partial` 并非零退出，提示可执行 `eto db rebuild <platform>`。
- Verify:
  - `eto --db-only bangumi ...` 不产生任何 `.md` / index 写入。
  - 不传 `-o` / `-t` 可运行；不带 `--db-only` 时仍强制要求。
  - db-only 下 `stop_if_output_exists` 不提前结束，所有分页都被抓取。
  - 投影失败时命令非零退出，raw 数据仍可查。

### T6. 重建 CLI

- Status: Completed
- Files: `src/app/cli.py`, `tests/test_cli_db.py`
- Work:
  - 增加 `eto --db data/eto.db db rebuild <platform>`。
  - `platform` 用 `click.Choice`，当前可用值随已实现解析器增加。
  - 输出处理响应数和写入行数；失败转成 `click.ClickException`。
- Verify: CLI 测试覆盖成功、未知平台、数据库错误。

### T7. 其余平台

- Status: Completed
- 每个平台一个任务、一个解析器文件、一个测试文件；不改表结构。
- Order:
  1. `bilibili`：`bilibili.favlist.page` -> 3 张表。
  2. `github`：`github.stars.list` + `github.repo.readme`。
  3. `zhihu`：`zhihu.collection.page` -> 内容 + membership。
  4. `v2ex`：收藏 HTML + 主题详情 + 回复分页；回复全量入 `v2ex_reply`，
     后续按 `(topic_id, thanks DESC)` 取热门。
  5. `weibo`：点赞列表 + 长文。
  6. `qireader`：稍后读列表 + 正文。
  7. `cnblog`：收藏列表 + 正文。
  8. `twitter`：点赞时间线。
- Verify per platform:
  - `rebuild_platform` 两次结果除 `db_*` 外逐列相等。
  - 200 异常 body 回滚；传输错误/非 200 跳过并计数。
  - 平台时间字段按设计文档 2.3 原样保留。
  - `PYTHONPATH=src pytest tests/test_projection_<platform>.py -q`。

### T8. 文档收尾

- Status: Completed
- Files: `AGENTS.md`, `README.md`, `docs/usages/`（如新增命令）
- Work:
  - 记录投影层的数据流、命令和“raw 只在重建时读取”的边界。
  - 把 layer 2 状态从 Proposed 更新为 Implemented。

## Acceptance

- `PYTHONPATH=src pytest tests -q` 通过。
- `ruff check src tests` 通过。
- `ruff format --check src tests` 通过。
- 同一份 raw 数据重建两次，除 `db_created_at` / `db_updated_at` 外逐列一致。
- 平台时间字段保持原类型：epoch 是 `INTEGER`，字符串是 `TEXT`。
- `v2ex_reply` 与 `v2ex_topic` 独立入库，可按 `(topic_id, thanks DESC)` 查询热门回复。
- 日常导出只读投影表，不读 `sync_run` / `sync_response`。
- 传输错误和非 200 响应不阻塞重建，跳过数量会出现在命令输出里。
- `--db-only` 只入库：不写 Markdown、不写索引、不要求 `-o` / `-t`。
- `--db-only` 下 raw 层和投影层都有数据；投影失败时 run 为 `partial`，命令非零退出。
- v1 不做删除；`response_id` 已写入，供后续完整 run 删除扫描回查。

## Execution records

- 2026-11-08: T1/T2 completed. Added `002_projection_layer.sql` with 17 `STRICT`
  tables and indexes; updated `user_version` assertions to 2; added
  `tests/test_projection_schema.py` covering common provenance columns, platform
  time columns, JSON checks, strict types, natural keys, foreign keys and migration
  from a layer 1 database.
- 2026-11-08: T3/T4 completed. Added `db.projections` dispatcher, shared
  `_upsert` helpers and the Bangumi parser. Rebuilds run in one transaction,
  skip stale responses, keep the main `response_id` on auxiliary updates and roll
  back on invalid or missing raw bodies.
- 2026-11-08: T5/T6 completed. Added top-level `--db-only`, optional `-o` / `-t`
  with runtime validation, centralized output suppression, disabled `IndexWriter`,
  Bangumi/GitHub output exceptions, projection after fetch with partial/failed run
  handling, and `eto db rebuild <platform>`.
- 2026-11-08: T7 bilibili/github/zhihu parsers completed, with idempotency,
  multi-membership, README auxiliary and rollback tests.
- 2026-11-08: T7 v2ex/weibo parsers completed. V2EX now fetches all reply pages
  under `--db-only` and stores them independently from topic details; Weibo long
  text is applied by `mblogid` without overwriting the main response provenance.
- 2026-11-08: T7 qireader/cnblog/twitter parsers completed. All nine platforms
  are registered in `SUPPORTED_PLATFORMS`; non-200 auxiliary bodies are skipped
  instead of being stored as content.
- 2026-11-08: T8 completed. Updated design status, `AGENTS.md`, `README.md`,
  `docs/usages/README.md` and per-command pages; added `docs/usages/db.md`.
- 2026-11-08: Review follow-up. Transport errors and non-200 responses are now
  skipped and counted instead of poisoning rebuilds; JSON non-200 handling moved
  into the shared iterators; V2EX reply pagination got a page cap and session
  reuse; empty/null list pages are tolerated; live Bangumi tests skip without
  `BGM_ACCESS_TOKEN`.
- 2026-11-08: Second review follow-up. CNBlog only backfills `source_url` on a
  unique `/<post_id>.html` bookmark match; V2EX reply page-limit path has a test;
  the design doc now states that `null` list values are empty pages while missing
  keys are structural errors.
- 2026-11-08: Third review follow-up. V2EX signin pages are detected during fetch
  and projection so favorites are not cleared; auxiliary `update_aux` misses are
  reported; auxiliary endpoints skip invalid 200 JSON while main entities still
  roll back.
- 2026-11-08: Fourth review follow-up. Auxiliary endpoints now also skip 200 JSON
  with missing business fields via `SkipResponse`; Weibo warns when a long post
  has no `mblogid`.
- 2026-11-08: Fifth review follow-up. Added a V2EX favorite-page cap; clarified
  that `--max-pages` still applies under `--db-only`; documented the V2EX
  signin-template limitation and raw-layer accumulation.
- 2026-11-08: Sixth review follow-up. Removed GitHub `full_name` UNIQUE (slug can
  be inherited) and indexed it instead; V2EX favorite pages now reuse one client;
  documented how a recorded signin page blocks rebuild.
- 2026-11-08: Seventh review follow-up. V2EX topic responses with a null result
  are now marked partial and skipped instead of raising outside the item loop.
- 2026-11-08: Eighth review follow-up. GitHub README updates require a unique
  `full_name` match; `RebuildResult.aux_missed` surfaces auxiliary misses in the
  summary; Weibo/Bilibili treat null `data` as an empty page; V2EX per-topic write
  errors mark partial and continue; replies without an id are skipped.
- 2026-11-08: Ninth review follow-up. Handler-skipped responses no longer remain
  in the `responses` count; db-only Bangumi character capture has a regression
  test; main-entry error messages clarify invalid payload shapes; remaining
  exporter pagination caps are recorded as follow-up risk.
- 2026-11-08: Tenth review follow-up. zhihu/cnblog/qireader exporters isolate
  per-item failures and mark partial; zhihu list-content parsing matches the
  projection parser; Weibo items without `idstr` are skipped.
- 2026-11-08: Eleventh review follow-up. Weibo/Bilibili/Twitter item-level
  failures now mark the run partial, matching AGENTS.md; added an auxiliary
  replay-order invariant test.
- 2026-11-08: Twelfth review follow-up. GitHub README skips HTML error pages and
  JSON without `content`; V2EX reply fetching reuses the exporter client; Bangumi
  no longer prints “处理完成” after a skipped subject.
- 2026-11-08: Thirteenth review follow-up (BLOCK fix). Main-entity business-level
  no-data payloads (V2EX `result: null`, Twitter errors-only/empty data, Weibo
  `ok != 1`) are skipped and counted instead of poisoning rebuilds; missing keys
  and type violations still roll back. Qireader article downgrade marks partial;
  docs note db-only still requires credentials.
- 2026-11-08: Fourteenth review follow-up (BLOCK fix). Also skip V2EX missing
  `result`, Bilibili `code != 0` and non-object V2EX replies; add top-level shape
  checks for bangumi/zhihu/weibo/github; projection failure output points to the
  bad-response procedure in db.md. Full suite: 306 passed, 2 skipped; ruff passes.

## Notes

- 新增迁移会让现有 `test_db_schema.py` 的 `user_version` 断言失败，T2 必须同步修改。
- `STRICT` + `json_valid` 依赖 SQLite >= 3.37；当前环境 3.45.1。
- 投影解析器需要从 raw JSON 读取当前 dataclass 没有的字段（如 GitHub `repo.id`），
  不要为了复用 dataclass 而丢失主键。
- 平台时间字段全部保留，不做统一格式；导出层以后自己决定用哪个。
- `db_created_at` / `db_updated_at` 是数据库操作时间，全量重建会重写；幂等测试排除这两列。
- V2EX V2 回复接口文档未明确列出 `thanks`；解析器有就写，没有就保留 0。
  如果实测确认没有又必须严格按感谢数排序，改用 V1 `/api/replies/show.json` 或在后续补字段。
- `--output-only` 属于第三层，本计划不实现，只保留设计文档 5.2 的语义。
