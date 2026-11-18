---
goal: 为 V2EX 新增 --tipped 入口，从 /balance 流水增量落库所有感谢（投币）回复/主题及其详情与回复
created: 2026-11-18
modified: 2026-11-18
status: Planned
design: docs/design/v2ex-tipped-topics.md
---

# V2EX 投币（感谢）主题落库实施计划

## 目标

在现有 `v2ex` 命令上增加 `--tipped`，只写数据库，从 `/balance` 发现所有“发送谢意”的主题，复用现有主题详情/回复抓取，并通过 `v2ex_thanks` 投影支持增量续跑。

## 约束与前提

- **CON-001**：`--tipped` 只允许与 `--db-only` 一起使用；不写 Markdown、不写索引。
- **CON-002**：数据源是 `https://www.v2ex.com/balance`，raw endpoint 为 `v2ex.balance.page`。
- **CON-003**：同时抓取 `感谢 ... 的回复` 和 `感谢 ... 的主题`，用 `content_kind` 区分。
- **CON-004**：复用 `v2ex_topic` / `v2ex_reply` 实体表；每个主题回复仍最多抓 200 条。
- **CON-005**：余额页是 HTML，不占 V2EX API 2.0 配额；主题详情和回复占 600 次/小时配额。
- **CON-006**：不新增第三方依赖，沿用 `requests`、`beautifulsoup4` 和现有 SQLite 迁移机制。
- **GUD-001**：遵循现有 `v2ex/exporter.py`、`db/projections/v2ex.py` 和 `app/cli.py` 的写法，不引入 BaseExporter 或 ORM。
- **GUD-002**：只运行受影响的最小测试切片，最终再跑完整相关测试和 Ruff。

## 实施步骤

### 阶段 1：数据源与解析

完成标准：`/balance` 页面可抓取、可解析出回复/主题感谢，signin 和重复末页有防护，单测通过。

| Task     | Status  | Description | Verification Steps | Date |
| -------- | ------- | ----------- | ------------------ | ---- |
| TASK-001 | Completed | 在 `src/v2ex/api_endpoints.py` 增加 `V2EX_BALANCE`；新建 `src/v2ex/tipped.py`，实现 `ThanksEntry`、`BalancePage`、`parse_balance_page`、`get_balance_page`、`V2EX_MAX_BALANCE_PAGES`，使用 `v2ex.balance.page` endpoint，处理 signin、`max_page`、`transaction_keys`。 | `PYTHONPATH=src pytest tests/test_v2ex.py -q` 通过；新增解析测试覆盖回复感谢、主题感谢、非感谢行、空感谢页和 signin。 | 2026-11-18 |
| TASK-002 | Completed | 在 `tests/test_v2ex.py` 补充解析/抓取测试；在 `tests/test_raw_platforms.py` 增加 `v2ex.balance.page` endpoint 断言。 | `PYTHONPATH=src pytest tests/test_v2ex.py tests/test_raw_platforms.py -q` 通过。 | 2026-11-18 |

#### TASK-001 执行记录
- **状态**: 已完成（2026-11-18）
- **变更摘要**: 新增 V2EX 余额流水抓取与解析模块，可识别“发送谢意”的回复/主题记录。
- **逻辑变更**:
  - **新增**: `src/v2ex/tipped.py` 提供 `ThanksEntry`、`BalancePage`、`parse_balance_page`、`get_balance_page` 和 `V2EX_MAX_BALANCE_PAGES`；`V2EX_BALANCE` 端点常量；解析测试覆盖回复感谢、主题感谢、非感谢行、缺主题链接、空页、页数上限和 signin。
  - **修改**（及原因）: 无既有逻辑改动；`api_endpoints.py` 仅追加余额页 URL。
- **相关代码**: `src/v2ex/tipped.py`、`src/v2ex/api_endpoints.py`
- **验证结果**: `PYTHONPATH=src .venv/bin/pytest tests/test_v2ex.py -q`，21 项通过。

#### TASK-002 执行记录
- **状态**: 已完成（2026-11-18）
- **变更摘要**: 为余额页抓取补齐 raw endpoint 断言测试。
- **逻辑变更**:
  - **新增**: `test_v2ex_balance_endpoint` 验证 `v2ex.balance.page` 记录、`max_page` 和感谢主题解析。
  - **修改**（及原因）: 无生产代码改动；TASK-001 已包含抓取层单测。
- **相关代码**: `tests/test_raw_platforms.py`
- **验证结果**: `PYTHONPATH=src .venv/bin/pytest tests/test_v2ex.py tests/test_raw_platforms.py -q`，43 项通过。

### 阶段 2：迁移与投影

完成标准：`v2ex_thanks` 表可创建，余额页可从 raw 重建，页级已知判断和已感谢主题查询可用。

| Task     | Status  | Description | Verification Steps | Date |
| -------- | ------- | ----------- | ------------------ | ---- |
| TASK-003 | Completed | 新建 `src/db/migrations/004_v2ex_thanks.sql`，创建 `v2ex_thanks` 表、主键和 `idx_v2ex_thanks_topic` 索引；更新 `tests/test_projection_schema.py` 的表集合、索引集合、平台时间列和 `user_version = 4`。 | `PYTHONPATH=src pytest tests/test_projection_schema.py -q` 通过。 | 2026-11-18 |
| TASK-004 | Completed | 修改 `src/db/projections/v2ex.py`：增加 `THANKS_ENDPOINT`，把 `v2ex_thanks` 加入 `DELETE_ORDER`，回放 `v2ex.balance.page`，实现 `_upsert_thanks`、`thanks_page_known`、`tipped_topic_ids`；signin 页抛出 `ValueError` 触发整体回滚。 | `PYTHONPATH=src pytest tests/test_projection_v2ex.py -q` 通过；新增测试覆盖两种 `content_kind`、字段落库、重复页幂等、signin 回滚和两个 helper。 | 2026-11-18 |

#### TASK-004 执行记录
- **状态**: 已完成（2026-11-18）
- **变更摘要**: 余额页 raw 响应可投影到 `v2ex_thanks`，并提供页级已知判断和已感谢主题查询。
- **逻辑变更**:
  - **新增**: `THANKS_ENDPOINT`、`_upsert_thanks`、`thanks_page_known`、`tipped_topic_ids`；余额页 signin 检测触发整体回滚。
  - **修改**（及原因）: `DELETE_ORDER` 加入 `v2ex_thanks`，全量重建时先清空旧投影；测试表集合同步。
- **相关代码**: `src/db/projections/v2ex.py`、`tests/test_projection_v2ex.py`
- **验证结果**: `PYTHONPATH=src .venv/bin/pytest tests/test_projection_v2ex.py -q`，15 项通过。

#### TASK-003 执行记录
- **状态**: 已完成（2026-11-18）
- **变更摘要**: 新增 `v2ex_thanks` 迁移表及索引，迁移版本升至 4。
- **逻辑变更**:
  - **新增**: `src/db/migrations/004_v2ex_thanks.sql`，包含交易级主键、`content_kind` 约束和 `topic_id` 索引。
  - **修改**（及原因）: `tests/test_projection_schema.py` 登记新表/索引/时间列和版本；`tests/test_db_schema.py` 的版本断言同步改为 4，否则迁移生效后既有 schema 测试会失败。
- **相关代码**: `src/db/migrations/004_v2ex_thanks.sql`
- **验证结果**: `PYTHONPATH=src .venv/bin/pytest tests/test_projection_schema.py tests/test_db_schema.py -q`，18 项通过。

### 阶段 3：导出器与 CLI

完成标准：`eto --db-only v2ex --tipped` 可发现感谢主题、补抓详情/回复，增量停止后仍扫描旧主题，且不写 Markdown。

| Task     | Status  | Description | Verification Steps | Date |
| -------- | ------- | ----------- | ------------------ | ---- |
| TASK-005 | Completed | 从 `src/v2ex/exporter.py` 的收藏路径抽取 `_ensure_topic_data(topic_id, client, force)`，收藏导出改为调用该 helper，保持原有 Markdown、索引和失败处理行为不变。 | `PYTHONPATH=src pytest tests/test_cli_db.py -q -k v2ex` 通过，确认现有收藏剪枝测试无回归。 | 2026-11-18 |
| TASK-006 | Completed | 在 `src/v2ex/exporter.py` 实现 `export_tipped(force=False)`：余额页循环、`max_page`/重复页/1000 页保护、`thanks_page_known` 停止并标记 `partial`、合并新主题与 `tipped_topic_ids`、逐主题调用 `_ensure_topic_data`。 | `PYTHONPATH=src pytest tests/test_cli_db.py -q -k tipped` 通过。 | 2026-11-18 |

#### TASK-006 执行记录
- **状态**: 已完成（2026-11-18）
- **变更摘要**: 新增 `export_tipped`，按余额页发现投币主题并合并历史投币主题后补齐详情/回复。
- **逻辑变更**:
  - **新增**: 余额页循环、`max_page` 终止、重复页保护、整页已知停止并标记 `partial`、新主题与 `tipped_topic_ids` 去重合并、逐主题调用 `_ensure_topic_data`。
  - **修改**（及原因）: 无既有逻辑改动；`--force` 关闭页级剪枝并交由 helper 重抓详情/回复。
- **相关代码**: `src/v2ex/exporter.py`、`tests/test_cli_db.py`
- **验证结果**: `PYTHONPATH=src .venv/bin/pytest tests/test_cli_db.py -q -k tipped`，1 项通过。

#### TASK-005 执行记录
- **状态**: 已完成（2026-11-18）
- **变更摘要**: 收藏导出中的详情/回复补抓逻辑提取为 `_ensure_topic_data`，行为保持不变。
- **逻辑变更**:
  - **新增**: `_ensure_topic_data` 统一处理已知主题的回复缺口、详情抓取、`--force` 重抓和单主题失败隔离。
  - **修改**（及原因）: 收藏循环改为调用 helper；异常打印和 `mark_run_partial` 移入 helper，收藏侧的 Markdown/索引异常仍由外层捕获。
- **相关代码**: `src/v2ex/exporter.py`
- **验证结果**: `PYTHONPATH=src .venv/bin/pytest tests/test_cli_db.py -q -k v2ex`，10 项通过。
| TASK-007 | Completed | 在 `src/app/cli.py` 为 `v2ex` 增加 `--tipped`，校验必须 `--db-only`，并用 `run_action('v2ex', 'tipped', None, ...)` 调用 `export_tipped`；不创建索引写入器。 | `PYTHONPATH=src pytest tests/test_cli_db.py -q -k v2ex` 通过；新增测试覆盖无 `--db-only` 时退出码非 0、`sync_run.operation='tipped'`、页级停止后仍补旧主题、`--force` 全量、无 Markdown 写入。 | 2026-11-18 |

#### TASK-007 执行记录
- **状态**: 已完成（2026-11-18）
- **变更摘要**: `eto v2ex --tipped` 已可用，且强制要求 `--db-only`。
- **逻辑变更**:
  - **新增**: `--tipped` 选项与 `run_action('v2ex', 'tipped', ...)` 分支；测试覆盖缺 `--db-only`、页级停止补旧主题、`--force` 全量、`operation='tipped'` 和无 Markdown 写入。
  - **修改**（及原因）: `v2ex` 命令的 operation 由 tip 状态决定，收藏路径行为保持不变。
- **相关代码**: `src/app/cli.py`、`tests/test_cli_db.py`
- **验证结果**: `PYTHONPATH=src .venv/bin/pytest tests/test_cli_db.py -q -k v2ex`，14 项通过。

### 阶段 4：文档与收尾

完成标准：用户文档、内部约定和既有设计文档同步，完整相关测试与 Ruff 通过。

| Task     | Status  | Description | Verification Steps | Date |
| -------- | ------- | ----------- | ------------------ | ---- |
| TASK-008 | Completed | 更新 `docs/usages/v2ex.md`：增加 `--tipped` 参数、示例、只写库说明、增量与配额限制，并修正现有“该命令不支持 --force”的错误描述。 | 人工核对文档中的命令与 `eto v2ex --help` 输出一致。 | 2026-11-18 |

#### TASK-008 执行记录
- **状态**: 已完成（2026-11-18）
- **变更摘要**: `docs/usages/v2ex.md` 同步 `--tipped` 用法、增量语义和配额限制。
- **逻辑变更**:
  - **新增**: `--tipped` 参数、只写库说明、示例、余额页增量/全量行为、600 次/小时配额和主题级投币限制。
  - **修改**（及原因）: 删除“该命令不支持 --force”的错误描述，改为说明 `--force` 覆盖文件并关闭剪枝。
- **相关代码**: `docs/usages/v2ex.md`
- **验证结果**: 人工核对文档命令与 `PYTHONPATH=src .venv/bin/python -c "...v2ex --help..."` 输出一致。
| TASK-009 | Pending | 更新 `AGENTS.md`：CLI 契约加入 `v2ex(...[--tipped])`，说明 `--tipped` 仅配合 `--db-only`；增量章节加入余额页整页已知停止、随后全量主题扫描、页级停止标记 `partial`；非目标加入投币主题 Markdown 导出。 | `grep -n "tipped\|v2ex_thanks" AGENTS.md` 能看到对应条目。 |      |
| TASK-010 | Pending | 更新 `README.md` 增加 `eto --db-only v2ex --tipped` 示例；更新 `docs/design/projection-layer.md` 增加 `v2ex_thanks`、`thanked_at` 时间列和 V2EX 4 张表的例外说明；更新 `docs/design/incremental-pruning.md` 增加投币页级停止 + 主题全量扫描的理由。 | 三份文档中均能检索到 `v2ex_thanks` 或 `--tipped`，且与设计文档一致。 |      |
| TASK-011 | Pending | 运行完整相关测试与 Ruff，更新本计划任务的 Status/Date，记录执行结果。 | `ruff check src tests`、`ruff format --check src tests`、`PYTHONPATH=src pytest tests/test_v2ex.py tests/test_projection_v2ex.py tests/test_projection_schema.py tests/test_cli_db.py tests/test_raw_platforms.py -q` 全部通过。 |      |

## 涉及文件

- **FILE-001**：`src/v2ex/api_endpoints.py` — 增加 `V2EX_BALANCE`。
- **FILE-002**：`src/v2ex/tipped.py` — 新增余额页抓取、解析和数据结构。
- **FILE-003**：`src/v2ex/exporter.py` — 抽取 `_ensure_topic_data`，新增 `export_tipped`。
- **FILE-004**：`src/app/cli.py` — 增加 `--tipped` 和 `--db-only` 校验。
- **FILE-005**：`src/db/migrations/004_v2ex_thanks.sql` — 新增投影表与索引。
- **FILE-006**：`src/db/projections/v2ex.py` — 增加余额页回放、upsert 和剪枝 helper。
- **FILE-007**：`tests/test_v2ex.py` — 余额页解析/抓取测试。
- **FILE-008**：`tests/test_projection_v2ex.py` — `v2ex_thanks` 投影测试。
- **FILE-009**：`tests/test_projection_schema.py` — schema、索引、时间列和迁移版本。
- **FILE-010**：`tests/test_cli_db.py` — `--tipped` CLI 与增量行为测试。
- **FILE-011**：`tests/test_raw_platforms.py` — `v2ex.balance.page` endpoint 断言。
- **FILE-012**：`docs/usages/v2ex.md`、`AGENTS.md`、`README.md`、`docs/design/projection-layer.md`、`docs/design/incremental-pruning.md` — 文档同步。

## 测试与验证

- **TEST-001**：解析器单测覆盖回复感谢、主题感谢、金额/余额/成员/标题、非感谢行、空感谢页、重复末页、signin、`max_page`。
- **TEST-002**：投影测试覆盖字段落库、两种 `content_kind`、重复响应幂等、signin 整体回滚、`thanks_page_known`、`tipped_topic_ids` 排序。
- **TEST-003**：CLI 测试覆盖 `--tipped` 必须 `--db-only`、新主题抓取、页级停止后仍补齐旧主题、`--force` 全量、`sync_run.operation='tipped'`、不写 Markdown。
- **TEST-004**：schema 测试覆盖 `v2ex_thanks` 表、`idx_v2ex_thanks_topic`、`thanked_at` 平台时间列、`user_version = 4`。
- **TEST-005**：最终执行 `ruff check src tests` 和 `ruff format --check src tests`。

## 风险与遗留

- **RISK-001**：V2EX 余额页 HTML 结构变化会破坏解析；fixture 测试和 raw 保留提供修复路径。
- **RISK-002**：首次补齐 515+ 个主题会受 600 次/小时 API 配额限制，需要多轮 `partial` run；这是已知限制，不引入自动定时任务。
- **RISK-003**：已删除主题会持续失败并保持 `partial`；本期不做删除检测。
- **RISK-004**：余额页不提供回复 ID，只能记录主题级投币关系。
- **RISK-005**：`v2ex_thanks` 使 V2EX 表数超过原 3 张预算，需在 `projection-layer.md` 记录例外。
