---
status: 已实现
created: 2026-11-18
modified: 2026-11-18
tags: [feature]
---

# V2EX 投币（感谢）主题落库

## 背景与目标

V2EX 当前的 `v2ex` 命令只抓 `/my/topics` 收藏。用户希望对所有“投过币”的回复和主题建立同样的主题详情与回复数据，供未来导出或分析。

V2EX 没有“我的投币”API。实际可用的完整来源是登录后的 `/balance` 账户流水页：

- 每次投币记为 `发送谢意`，金额通常为 `-10`，感谢主题也出现过 `-15`；
- 描述形如 `感谢 <member> 的回复 › <topic title>` 或 `感谢 <member> 的主题 › <topic title>`；
- 每行提供主题链接 `/t/<topic_id>`、时间、金额、余额、被感谢人和主题标题；
- **不提供回复 ID**，因此只能把“投币回复”定位到主题，不能定位到具体回复；
- 分页从新到旧，最后一页会重复返回；页面包含 `input.page_input[max]` 可读取总页数。

2026-11-18 调研快照：

- 156 个真实页、3105 条去重流水；
- 797 条 `发送谢意`：673 条回复感谢 + 124 条主题感谢；
- 去重后 630 个主题：523 个来自回复感谢，124 个来自主题感谢，17 个重叠；
- 当前库已有 8 个，首次需要补 515 个以上主题的详情和回复。

目标：

- 新增 `eto --db-only v2ex --tipped`，把 `/balance` 中所有 `发送谢意` 记录落库；
- 复用现有 V2EX 主题详情与回复抓取逻辑；
- 支持增量：余额页整页感谢记录都已入库时停止翻页，但随后仍检查所有已入库感谢主题的详情/回复缺口；
- 保留交易级字段，为未来扩展留足数据。

## 范围

- 包含：
  - `/balance` HTML 分页抓取与 `发送谢意` 解析；
  - 回复感谢和主题感谢两种类型；
  - 新增 raw endpoint `v2ex.balance.page`；
  - 新增投影表 `v2ex_thanks`；
  - `--tipped` CLI flag 与 `--db-only` 校验；
  - 复用 `v2ex_topic` / `v2ex_reply` 的详情与回复抓取；
  - 增量剪枝、失败隔离、测试与文档。
- 不包含：
  - `--tipped` 的 Markdown 或索引导出；
  - 精确到回复 ID 的投币关系（余额页不提供）；
  - 删除检测、多账号、投币余额对账；
  - 修改现有收藏导出行为；
  - 提高 V2EX API 配额或引入异步任务系统。

## 方案设计

### 1. CLI 契约

新增：

```shell
eto --db-only v2ex --tipped
```

规则：

- `--tipped` 只允许与 `--db-only` 一起使用；否则抛出 `click.UsageError('--tipped requires --db-only')`。
- `--tipped` 替代默认收藏源，不与 `/my/topics` 同时抓取。
- `--tipped` 不写 Markdown、不写索引，不需要 `-o`。
- `--force` 仍然可用：关闭余额页剪枝和主题详情/回复剪枝，重新抓取完整范围。
- `sync_run.operation` 使用 `'tipped'`，与默认收藏的 `'favorites'` 区分。

### 2. 数据源与解析

新增 `src/v2ex/tipped.py`：

- `V2EX_BALANCE = 'https://www.v2ex.com/balance'`
- `V2EX_MAX_BALANCE_PAGES = 1000`
- `ThanksEntry`：`thanked_at`、`topic_id`、`content_kind`、`member`、`amount`、`balance`、`topic_title`、`description`
- `BalancePage`：`max_page`、`thanks`、`transaction_keys`、`has_table`
- `parse_balance_page(html) -> BalancePage`
- `get_balance_page(page, client=None) -> BalancePage`

抓取行为：

- 使用 `export_runtime.http.get`，endpoint 为 `v2ex.balance.page`，`params={'p': page}`；
- 非 200 调用 `raise_for_status()`；
- 检测跳转到 `/signin` 或 signin 表单，抛出 `RuntimeError('V2EX login required')`；
- 解析 `table.data` 的每一行，只保留类型为 `发送谢意` 的行；
- 描述必须以 `感谢 <member> 的(回复|主题)` 前缀开头（`re.Pattern.match`）；标题里出现“的回复”等字样不影响分类；
- 没有 `table.data` 的页面（维护页、风控页）返回 `has_table=False` 的空页；`export_tipped` 视为异常，标记 `partial` 并结束翻页，避免把“没抓到流水”当成“空流水”；
- 时间保留原字符串，金额和余额解析为 `float`；
- `transaction_keys` 保存该页全部流水的文本签名，用于最后一页重复检测；
- `max_page` 从 `input.page_input[max]` 读取；缺失时返回 `None`，由调用方使用重复页检测和页数上限兜底。

### 3. 增量流程

`export_tipped(force=False)` 的流程：

1. 从第 1 页开始抓 `/balance`，记录 raw 响应。
2. 收集本页 `thanks`，并累加到 `new_entries`。
3. 增量停止条件：`entries` 非空，且 `thanks_page_known(connection, entries)` 为真时，标记本次 run 为 `partial`，停止翻页。
4. 没有 `max_page` 时，用 `transaction_keys` 与上一页比较；相同则停止，避免最后一页重复导致无限循环。
5. 页数超过 `V2EX_MAX_BALANCE_PAGES` 时抛错。
6. 翻页结束后再从当前投影读取所有已感谢主题 `tipped_topic_ids(connection)`，组装待检查主题：先按余额页出现顺序放 `new_entries` 的 topic_id，再追加投影中已有、但本次未出现的 topic_id（按 `MAX(thanked_at) DESC` 排序）。顺序不影响正确性，因为投影尚未在本次 run 内重建。
7. 对每个 topic_id 调用 `_ensure_topic_data(topic_id, client, force)`：详情缺失则抓详情，回复不完整则抓回复，已完成则跳过。连续 `V2EX_MAX_CONSECUTIVE_FAILURES = 10` 个主题抓取失败时停止本轮扫描，剩余主题留给下一轮。
8. 由 `run_action` 在同一个 `sync_run` 内重建 `v2ex` 投影。

关键点：**余额页停止翻页后必须继续扫描投影中的全部感谢主题**。否则第 1 页全部命中时，前面几轮因 API 配额未补齐的旧主题会被永久跳过。这是与收藏页剪枝不同的地方。

`--force` 下跳过第 3 步的页级剪枝，也不跳过任何主题详情/回复。

### 4. 数据模型

新增迁移 `004_v2ex_thanks.sql`：

```sql
CREATE TABLE v2ex_thanks (
    thanked_at TEXT NOT NULL,
    topic_id INTEGER NOT NULL,
    content_kind TEXT NOT NULL CHECK (content_kind IN ('reply', 'topic')),
    member TEXT NOT NULL DEFAULT '',
    amount REAL NOT NULL,
    balance REAL NOT NULL,
    topic_title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL,
    PRIMARY KEY (thanked_at, topic_id, content_kind, member, balance)
) STRICT;

CREATE INDEX idx_v2ex_thanks_topic
    ON v2ex_thanks(topic_id);
```

说明：

- `thanked_at` 是平台时间，保留原字符串（含 `+08:00`）。
- `content_kind` 区分回复感谢和主题感谢，满足“主题也算感谢”的需求。
- `amount` 保留 `-10` / `-15` 等实际金额；`balance` 保留交易后余额。
- `description` 保存完整描述文本，避免未来需要时再回 raw 解析。
- `balance` 进入主键，用于区分同一秒、同一成员、同一主题的两笔感谢。
- 不建 `topic_id -> v2ex_topic` 外键：感谢记录先到，主题详情可能抓取失败。
- `v2ex` 因此从 3 张表变成 4 张表。这是 `projection-layer` 中“每平台 1-3 张表”预算的有意例外，理由是投币流水是独立来源关系，不能塞进收藏、主题或回复表。

### 5. 投影重建

在 `src/db/projections/v2ex.py` 中：

- 新增 `THANKS_ENDPOINT = 'v2ex.balance.page'`；
- `DELETE_ORDER` 加入 `v2ex_thanks`；
- 用 `iter_body_responses` 按固定顺序回放余额页；
- 新增 `_upsert_thanks`：
  - HTML 是 signin 页时抛出 `ValueError`，让整个 `v2ex` 投影回滚；
  - 正常页面调用 `parse_balance_page`；
  - 逐条 `upsert` 到 `v2ex_thanks`，`response_id` 指向产生该行的 `sync_response`。
- 新增 `thanks_page_known(connection, entries) -> bool`：所有 entry 按主键存在时返回 `True`；调用方保证 `entries` 非空。
- 新增 `tipped_topic_ids(connection) -> list[int]`：按最近感谢时间倒序返回去重 topic_id。
- `rebuild` 的 `RebuildResult` 同时统计余额页响应和 thanks 行数。

重建仍是“全量删除再回放”：`v2ex_thanks` 从 raw 重建，不在投影上原地修改。

### 6. 导出器复用

从 `src/v2ex/exporter.py` 中抽取：

```python
def _ensure_topic_data(topic_id, client, force) -> tuple[Topic | None, bool]
```

它承载现有收藏路径中的以下逻辑：

- `--db-only` 且未 `--force` 时，若 `v2ex_topic` 已知，按 `min(replies, 200)` 检查回复完整性；
- 详情缺失时调用 `get_v2ex_topic_info`；
- `--db-only` 下抓取不完整的回复；
- 失败时 `mark_run_partial()` 并返回 `(None, True)`；已入库跳过或成功返回第二项 `False`。

收藏路径改为调用该 helper，Markdown 写入、索引和文件名逻辑保持不变。`export_tipped` 只调用 helper，不写 Markdown、不写索引，并用第二项统计连续失败次数。

### 7. 错误处理

- `/balance` 非 200：由 `raise_for_status()` 抛出，run 失败，不重建投影。
- signin 页：抓取阶段抛 `RuntimeError`；投影阶段抛 `ValueError` 并整体回滚，避免清空已有感谢记录。
- 缺少 `table.data` 的余额页（维护页、风控页）：抓取阶段无法区分，交由 `has_table=False` 标记；`export_tipped` 打印警告、标记 `partial` 并结束翻页。raw 仍保留该页，修好解析后可 `eto db rebuild v2ex`。翻页中止后**主题扫描照常执行**：HTML 异常不代表 API 异常，继续扫描仍可能补齐详情/回复，失败量由连续失败中止兜底。
- 有 `table.data` 但第 1 页解析出 0 条流水：只打印警告（可能是新账号的空历史，也可能是行结构变化），run 状态不变；后续页仍按 `max_page`/重复页规则翻完。
- 单个主题详情 404/403/网络错误：`_ensure_topic_data` 标记 `partial`，跳过该主题，下一轮继续。
- 连续 10 个主题抓取失败：`export_tipped` 停止本轮剩余扫描（run 已因上述失败标记为 `partial`）。客户端对 429 会走满 5 次重试退避，单个主题失败约 6 次请求、30 秒；不中止时 600+ 个主题会对着限流端点空转数小时。剩余主题在下一轮配额恢复后收敛。
- 被删除的主题：保留 `v2ex_thanks` 行，主题详情持续缺失，run 保持 `partial`；不做删除检测。
- API 配额 600 次/小时：首次补齐 515 个以上主题会跨多个小时窗口；余额页是 HTML，不占 API 2.0 配额，主题详情和回复占配额。
- 回复上限沿用 `V2EX_MAX_REPLIES = 200`。

## 关键决策

- **DEC-001**：使用 `/balance` 账户流水作为“投币”来源。V2EX 没有“我的投币”API；余额页提供完整历史、时间、金额、成员和主题链接，是当前唯一可验证的完整来源。
- **DEC-002**：回复感谢和主题感谢都抓取，用 `content_kind` 区分。用户明确要求“主题也算感谢”。
- **DEC-003**：使用交易级 `v2ex_thanks`，而不是只建 `v2ex_tipped(topic_id)`。交易级表支持页级增量判断，保留时间/成员/金额/余额/描述，满足未来扩展。
- **DEC-004**：`--tipped` 只支持 `--db-only`，替代收藏源，不做 Markdown。用户明确表示导出未来重构，本阶段只落库。
- **DEC-005**：余额页停止翻页后仍扫描全部已感谢主题。页级剪枝只负责发现新感谢，不负责判断主题详情是否完整；如果不做全量主题扫描，会永久漏掉旧主题。
- **DEC-006**：复用 `v2ex_topic` / `v2ex_reply`，不新建主题/回复实体表。同一主题被收藏和被感谢时只保留一份实体数据。
- **DEC-007**：页级增量停止标记 run 为 `partial`，遵循仓库现有“整页已知即 partial”的约定；`--force` 全量扫描才可能是 `success`。
- **DEC-008**：`content_kind` 只从 `感谢 <member> 的(回复|主题)` 这个固定前缀判定，不对整段描述做子串匹配。主题标题可能包含“的回复”，子串匹配会把主题感谢误判成回复感谢，而 `content_kind` 参与主键，误分类会随重建稳定复现。
- **DEC-009**：连续 10 个主题抓取失败即中止本轮剩余扫描。失败已在客户端层走满 429 重试退避（约 6 次请求 / 30 秒每个主题），600+ 个主题从头扫到尾会让限流窗口长期无法恢复；run 本已 `partial`，剩余主题下轮收敛。

## 备选方案

- **ALT-001**：抓取用户主页的“感谢”列表。V2EX 没有该页面或公开接口；`/my/thanks` 返回 404。
- **ALT-002**：从 `v2ex_reply.thanks` 反推自己投过币的回复。`thanks` 只是聚合计数，不包含“谁感谢了谁”，无法反推。
- **ALT-003**：只建 `v2ex_tipped(topic_id)` 关系表。无法做余额页级增量判断，也丢失交易字段，不满足“保留最大限度字段”。
- **ALT-004**：新增独立子命令 `v2ex-tips`。用户明确要求用 flag，且复用现有 `v2ex` 凭证与主题抓取更自然。
- **ALT-005**：每轮都完整扫 156 页余额页。实现更简单，但 raw 库每轮增加约 156 页 HTML，增量收益消失，因此不采用。
- **ALT-006**：页级停止后只处理本页主题。实现更简单，但会漏掉旧页中尚未补齐详情的主题，直接否决。

## 风险与限制

- **RISK-001**：V2EX 余额页 HTML 结构变化会导致解析失败。缺少 `table.data` 时 `export_tipped` 会告警并标记 `partial`，不再静默当成空流水；解析器必须有固定 fixture 测试，原始 HTML 保留在 raw 层，修复后可 `eto db rebuild v2ex`。
- **RISK-002**：余额页最后一页重复返回。依赖 `max_page`，并用 `transaction_keys` 重复检测和 1000 页上限兜底。
- **RISK-003**：V2EX API 600 次/小时限制。首次 515 个以上主题需要多轮续跑；每轮 run 可能是 `partial`，这是预期行为。
- **RISK-004**：部分旧主题已被删除。`v2ex_thanks` 保留，主题详情抓取会持续失败并标记 `partial`；不引入删除检测。
- **RISK-005**：回复只保留前 200 条，超过部分不抓；这是现有 V2EX 设计限制。
- **RISK-006**：余额页只提供主题链接，不提供回复 ID；无法精确知道感谢的是哪条回复。
- **RISK-007**：同一秒、同一成员、同一主题的多笔感谢理论上可能主键冲突；用 `balance` 纳入主键降低概率，仍非绝对唯一。
- **RISK-008**：`v2ex_thanks` 使 V2EX 表数量超过 3 张，需要在 `projection-layer.md` 中明确记录例外，避免后续误判。
- **RISK-009**：连续失败中止是通用阈值，不区分 429 与被删除主题（`get_v2ex_topic_info` 对非 200 一律返回 `None`）。若同一时段连续 10 个不同主题被删除，其后主题每轮都会在同一位置中止；概率很低（同一主题的多次感谢已按 `topic_id` 去重），需要时再为 429 单独判定。
- **RISK-010**：已删除回复造成的回复缺口永远无法补齐，`replies_complete` 每轮都会失败并重新抓取该主题的回复页，append-only raw 每轮新增重复响应。投币模式把这项成本从收藏集合扩大到全部投币主题；如需消除，应给主题加“缺口已尝试修复”的标记，本期不做。

## 验证方式

- **TEST-001**：余额页解析 fixture 覆盖回复感谢、主题感谢、标题含“的回复”的主题感谢、非前缀描述、非感谢流水、无感谢页、无流水表页、重复末页、signin 页和 `max_page`。
- **TEST-002**：投影重建覆盖两种 `content_kind`、字段落库、重复页幂等、signin 回滚、`thanks_page_known` 和 `tipped_topic_ids`。
- **TEST-003**：CLI 覆盖 `--tipped` 必须配合 `--db-only`、新主题抓取、已知页停止后仍补旧主题、`--force` 全量、无 `max_page` 时的重复末页停止、无流水表页中止后仍扫描主题、第 1 页零流水告警、连续 10 个主题抓取失败中止扫描（含回复抓取异常计数）、`sync_run.operation='tipped'`。
- **TEST-004**：schema 测试覆盖 `v2ex_thanks` 表、索引、平台时间列和 `user_version = 4`。
- **TEST-005**：`ruff check src tests`、`ruff format --check src tests` 通过。
- **TEST-006**：真实环境 smoke（可选，注意配额）：运行 `eto --db-only v2ex --tipped`，确认页级剪枝生效、旧主题缺口继续补齐、无 Markdown 写入。
