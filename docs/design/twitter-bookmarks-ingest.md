---
status: 已实现
created: 2026-11-13
modified: 2026-11-17
tags: [feature, data]
---

# Twitter 书签入库设计

- Issue: [#7](https://github.com/bgzolab/export-all-to-obsidian/issues/7)
- PR: [#27](https://github.com/bgzolab/export-all-to-obsidian/pull/27)
- Status: 已实现
- Date: 2026-11-13
- Implemented: 2026-11-16
- Related: [projection-layer.md](projection-layer.md)、[incremental-pruning.md](incremental-pruning.md)、[raw-response-layer.md](raw-response-layer.md)

## 背景与目标

当前 `twitter` 模块已经支持点赞导出，并把点赞回放进 `twitter_tweet`。X 书签是另一类私有收藏数据，接口按收藏时间倒序返回，但没有书签时间字段。X 内部 GraphQL 接口存在限流，单轮可能抓不完所有书签。

本阶段只做**书签数据入库**，不做 Markdown 导出。目标是：

- 用现有 Cookie 鉴权抓取 `Bookmarks` GraphQL 接口，响应写入 raw 层。
- 把书签和点赞统一到一张 Tweet 实体表，来源关系分表保存。
- 支持两种运行模式：默认增量剪枝，适合定时任务；`--full` 全量抓取并支持跨运行断点续抓。
- 限流时停止并保留断点，下一次全量运行继续，不在单次运行内长时间 sleep。
- queryId 失效时打印明确的维护提示。

非目标：

- 不导出书签 Markdown，不写索引。
- 不抓取书签文件夹（Bookmark folders）。
- 不保存书签收藏时间或收藏顺序。
- 不做删除检测、多账号、官方 API v2、自动发现 queryId。
- 不在单次运行内 sleep 到限流窗口重置。
- 不为 queryId 失效新增 Telegram 通知；只在终端打印维护提示。

## 范围

- 包含：
  - `twitter.bookmarks.page` 抓取与 raw 记录。
  - `twitter_tweet` 共享 Tweet 实体，新增 `twitter_like`、`twitter_bookmark` 关系表。
  - `eto --db-only twitter --bookmarks [--full] [--force] [--max-pages N]`。
  - 增量剪枝、全量断点续抓、限流停止、queryId 维护提示。
  - `eto db rebuild twitter` 同时回放点赞和书签响应。
  - 相关测试与文档同步。
- 不包含：
  - 书签 Markdown 导出。
  - 书签文件夹、收藏时间、收藏顺序。
  - 删除检测、多账号、官方 API。
  - 自动 queryId 发现和自动重试调度。

约束：

- 复用现有 `requests`、`sqlite3`、`click`，不新增运行时依赖。

## 报文调研结论

Likes 和 Bookmarks 的 Tweet 节点结构一致，可以共用 `Tweet.from_dict` 和 Tweet 实体表：

- 都是 `TimelineAddEntries` → `entry.content.itemContent` → `TimelineTweet` → `tweet_results.result`。
- 都可能是 `TweetWithVisibilityResults` 包装。
- `legacy`、作者 `core.user_results.result`、计数、时间字段相同。
- 分页都用 `TimelineTimelineCursor` 的 `Bottom` cursor。

差异只在响应信封和请求参数：

| 项目 | Likes | Bookmarks |
| --- | --- | --- |
| 响应根路径 | `data.user.result.timeline_v2.timeline.instructions` | `data.bookmark_timeline_v2.timeline.instructions`，兼容 `bookmark_timeline` |
| 请求变量 | 需要 `userId` | 不需要 `userId`，需要 `withV2Timeline: true` |
| field toggles | `withArticlePlainText` | `graphql_timeline_v2_bookmark_timeline` |
| 每页条数 | 20 | 参考实现支持到 100 |
| queryId | 已有硬编码 | 需要新增硬编码，X 会周期性轮换 |

因此采用“一张 Tweet 实体表 + 两张来源关系表”，不复制 Tweet 内容。

## 方案设计

### CLI 与运行模式

`--bookmarks` 是 `twitter` 子命令上的独立 flag，必须与 `--db-only` 同时使用；默认行为仍是点赞。

| 模式 | 命令 | 行为 |
| --- | --- | --- |
| 增量（默认） | `eto --db-only twitter --bookmarks` | 从顶部开始；整页都已存在于 `twitter_bookmark` 时停止，标记 `partial`；适合定时任务 |
| 全量 | `eto --db-only twitter --bookmarks --full` | 从顶部开始；如果上次全量中断，从 full run 的断点游标继续；不做整页已知停止；到末尾、限流或页数上限停止 |
| 强制重来 | `eto --db-only twitter --bookmarks --force` | 隐含 `--full`；忽略断点，从顶部开始一轮新的全量抓取 |

补充规则：

- `--full` 只能与 `--bookmarks` 一起使用，否则报 `UsageError`。
- `--bookmarks` 非 `--db-only` 时报 `UsageError`，避免普通导出模式静默不写 Markdown。
- `--max-pages` 两种模式都生效；书签默认每页请求 100 条，默认 50 页。
- `--force` 在点赞模式下保持现有语义；在书签模式下表示从顶部重开全量。
- 书签运行的 `sync_run.operation` 为 `bookmarks`，`sync_run.scope` 为 `full` 或 `incremental`。
- 增量模式如果发现存在未完成的全量轮次，只打印提示“如需继续全量请加 `--full`”，不自动续抓。
- 全量模式达到页数上限或限流时标记 `partial`；下一次 `--full` 从断点继续。

### 抓取流程

```text
cursor = None
if full and not force:
    checkpoint = latest_bookmark_checkpoint(connection)
    cursor = checkpoint.cursor
    if checkpoint.in_progress:
        print("从上次断点继续全量书签抓取")
if not full:
    if latest_bookmark_checkpoint(connection).in_progress:
        print("存在未完成的全量书签抓取，如需继续请加 --full")

while pages < max_pages:
    result = get_twitter_bookmark_list(client, count=100, cursor=cursor)
    处理错误：429 / 400 / 404 / 401 / 403 / 5xx / JSON 解析失败
    if not full:
        整页 tweet_id 都在 twitter_bookmark 中 -> 停止并标记 partial
    next_cursor = result.page.cursor_bottom
    if next_cursor 为空: 正常结束
    if next_cursor 与当前游标重复:
        若本页无 Tweet: 正常结束（终止空页）
        否则: 标记 partial 并停止
    if next_cursor 命中本轮已出现过的游标: 标记 partial 并停止
    if rate_limit_remaining <= 0: 标记 partial 并停止
    cursor = next_cursor
```

分页保护：

- 游标重复（等于当前请求游标或本轮已出现过的游标）时停止，避免死循环；唯一例外是
  只有 cursor、bottom cursor 等于当前请求游标且本页无 Tweet 的空页，这是列表末尾，
  正常结束且不标记 `partial`。
- 连续 3 页没有 Tweet 且仍有 cursor 时停止并标记 `partial`，避免空页循环。
- 全量模式不做整页已知停止；增量模式整页 `tweet_id` 都已知时停止并标记 `partial`。
- 无 Tweet 且无 cursor 视为正常结束。

### 跨运行断点续抓

不新增游标状态表，直接从 raw 层推导。每次 bookmarks 请求都已经写入 `sync_response`，`request.params.variables.cursor` 和响应 body 都在库中。

`src/db/raw.py` 新增 `latest_response(connection, endpoint, *, scope=None)`：按 `sync_response.id DESC` 取最近一条响应并解压 body，`scope` 非空时 join `sync_run` 过滤；`iter_responses` 复用同一解压 helper。

`latest_bookmark_checkpoint(connection)` 返回 `BookmarkCheckpoint(cursor, in_progress)`：

1. 查询最近一条 `endpoint = 'twitter.bookmarks.page'` 且 `sync_run.scope = 'full'` 的响应。
2. 没有响应：返回 `(None, False)`。
3. 最新响应非 200、body 为空、有 transport error 或 JSON 非法：
   返回 `(该请求的 cursor, True)`，下次重试这一页。
4. 最新 200 响应能解析出 bottom cursor：
   返回 `(next_cursor, True)`；但如果该页没有 Tweet 且 `next_cursor` 等于请求 cursor，
   说明这是上面提到的终止空页，返回 `(None, False)`。
5. 最新 200 响应没有 bottom cursor：
   返回 `(None, False)`，表示上一轮已经到末尾，下一次全量从顶部重新开始。

使用 `sync_run.scope = 'full'` 过滤，避免增量模式产生的响应污染全量断点。增量模式始终从顶部开始，不读取断点。

已知限制：

- 全量轮次被限流或页数上限打断后，必须再次运行 `--full` 才会继续；默认增量不会自动补旧书签。
- 断点游标可能过期；全量模式遇到 400 且当前有游标时，提示使用 `--force` 从顶部重来，不自动回退。

### 限流策略

- 读取响应头 `x-rate-limit-remaining` 和 `x-rate-limit-reset`。
- 处理完当前页后，如果 `remaining <= 0` 且仍有 cursor，标记 `partial`，打印重置时间并停止。
- 遇到 HTTP 429 直接停止并标记 `partial`，从响应头打印重置时间。
- 不在单次运行内 sleep 等待 15 分钟；通过跨运行续抓消化限流。
- 全量模式下次 `--full` 从断点继续；增量模式下次从顶部重新开始。
- 书签每页请求 100 条，减少请求数；如果上游只返回 20 条，分页仍然正确。
- 默认 `--max-pages 50`，用户可按配额调小或调大。
- 限流数值以实际响应为准；官方 API 的 180 次/15 分钟仅供参考，不适用于内部 GraphQL 接口。

### 投影模型

新增迁移 `003_twitter_sources.sql`：

```sql
CREATE TABLE twitter_like (
    tweet_id TEXT PRIMARY KEY REFERENCES twitter_tweet(tweet_id),
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE twitter_bookmark (
    tweet_id TEXT PRIMARY KEY REFERENCES twitter_tweet(tweet_id),
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
) STRICT;

INSERT INTO twitter_like (tweet_id, response_id, db_created_at, db_updated_at)
SELECT tweet_id, response_id, db_created_at, db_updated_at
FROM twitter_tweet;
```

`twitter_tweet` 保持现有结构，作为共享 Tweet 实体表：

- `twitter.likes.page` 写入 `twitter_tweet` + `twitter_like`。
- `twitter.bookmarks.page` 写入 `twitter_tweet` + `twitter_bookmark`。
- 同一条 Tweet 被点赞和书签时，`twitter_tweet` 只有一行，两张关系表各一行。
- `twitter_tweet.response_id` 指向最近一次更新该 Tweet 内容的主响应；关系表的 `response_id` 指向观察到该关系的响应。
- `known_tweet_ids` 改为查询 `twitter_like`；新增 `known_bookmark_ids` 查询 `twitter_bookmark`，两者互不污染剪枝。
- 重建删除顺序：`twitter_like`、`twitter_bookmark`、`twitter_tweet`。
- 重建回放顺序：先 `twitter.likes.page`，再 `twitter.bookmarks.page`；`response_id` 的 upsert 守卫保证旧响应不会覆盖新响应。
- 迁移把现有 `twitter_tweet` 全部回填为点赞，因为当前表只由点赞接口写入。

`user_version` 从 2 升到 3。

### 解析与接口

在 `src/twitter/api_endpoints.py` 增加：

- `TWITTER_BOOKMARKS_PATH`：硬编码 `https://x.com/i/api/graphql/Fy0QMy4q_aZCpkO0PnyLYw/Bookmarks`。
- `TWITTER_BOOKMARKS_PAGE_SIZE = 100`。
- `TWITTER_BOOKMARKS_FIELD_TOGGLES = {'graphql_timeline_v2_bookmark_timeline': True}`。
- features 复用现有 timeline features；如果上游要求独立集合，再单独拆常量。

在 `src/twitter/entity.py` 增加 `BookmarksPage`：

- `tweets: list[Tweet]`
- `cursor_bottom: TimelineCursor | None`
- `from_dict` 优先读 `bookmark_timeline_v2.timeline.instructions`，回退到 `bookmark_timeline.timeline.instructions`。
- 与 `LikesPage` 共用 instruction/entry 解析；不再要求 `entryId` 以 `tweet-` 开头，只跳过 `cursor-`、`messageprompt-`、`module-`、`who-to-follow-` 等非内容 entry。
- 支持 `content.itemContent` 和旧版 `content.content.itemContent`。

在 `src/twitter/bookmark.py` 增加：

- `build_bookmarks_params(count, cursor=None)`：变量包含 `count`、`includePromotedContent=False`、`withClientEventToken=False`、`withBirdwatchNotes=False`、`withVoice=True`、`withV2Timeline=True`，有 cursor 时加入 `cursor`。
- `BookmarksFetch`：`page`、`status_code`、`rate_limit_remaining`、`rate_limit_reset`、`error`。
- `get_twitter_bookmark_list(client, count=100, cursor=None)`：走 `export_runtime.http.get`，endpoint 为 `twitter.bookmarks.page`，记录 raw 响应。
- 非 200 返回带状态码的结果；200 非 JSON、非 dict、缺少 `data` 返回 `error`。

### 错误处理

| 情况 | 行为 |
| --- | --- |
| 200 + 正常数据 | 处理当前页 |
| 200 + 空 data | 视为本页无数据；无 cursor 时正常结束 |
| 200 + 非 JSON / 非 dict | 标记 `partial`，打印原因，停止 |
| HTTP 429 | 标记 `partial`，打印重置时间，停止 |
| HTTP 400 且当前有游标 | 标记 `partial`，提示“游标可能失效，请加 `--force` 从顶部重来” |
| HTTP 400 且当前无游标 | 标记 `partial`，打印 queryId/features 维护提示 |
| HTTP 404 | 标记 `partial`，打印 queryId 轮换维护提示 |
| HTTP 401 / 403 | 标记 `partial`，提示 Cookie 失效 |
| 5xx / 传输异常 | 标记 `partial`，打印原因；全量下次从该请求游标重试 |
| 游标不推进 | 标记 `partial`，打印原因，停止 |
| 连续 3 页空页 | 标记 `partial`，打印原因，停止 |
| 达到 `--max-pages` | 标记 `partial`，打印提示，停止 |

queryId 维护提示必须包含：

- 当前 HTTP 状态码。
- “X 的 GraphQL queryId 可能已轮换”。
- 从 `x.com/i/bookmarks` 的网络请求中获取新的 `Bookmarks` queryId。
- 更新 `src/twitter/api_endpoints.py` 的 `TWITTER_BOOKMARKS_PATH`。

### 凭证

- 新增 `probe_twitter_bookmarks_credentials`，请求 Bookmarks 接口 `count=1`。
- 200 且 `data` 为对象（含空对象 `{}`）判为 `valid`；`data` 缺失或非对象但含 `errors` 数组判为 `unknown`，原因记录错误摘要；其余 200 无 `data` 判为 `invalid`；401/403 判为 `invalid`；400/404 判为 `unknown` 并在原因中包含 queryId 维护提示；其他状态判为 `unknown`。
- Likes 验活仅把 200 + errors-only 归为 `unknown`；`data` 为空仍按点赞抓取语义判为 `invalid`。
- 书签验活独立于点赞验活，多消耗一次配额；这是为了能单独判断书签端点是否可用。
- Cookie、`TWITTER_CSRF_TOKEN`、`TWITTER_USER_ID` 的现有规则不变。

## 关键决策

- **DEC-001**：`twitter_tweet` 作为共享 Tweet 实体，新增 `twitter_like` 和 `twitter_bookmark` 关系表。理由：两种报文 Tweet 节点一致，同一条 Tweet 不应重复存正文；关系分表可以隔离剪枝和来源溯源。
- **DEC-002**：`--bookmarks` 必须与 `--db-only` 一起使用。理由：本阶段只做入库；普通导出模式下没有书签 Markdown 输出，静默无输出会误导用户。
- **DEC-003**：提供默认增量、`--full` 全量断点续抓、`--force` 重开全量三种语义。理由：定时任务需要从顶部剪枝，首次回填需要跨运行续抓，强制刷新需要从头重来。
- **DEC-004**：断点从 raw 层推导，不新增游标状态表。理由：raw 已经保存请求游标和响应 body；用 `sync_run.scope='full'` 过滤，零 schema 变更。
- **DEC-005**：限流时停止而不是 sleep。理由：15 分钟级等待不适合 CLI 和 cron；跨运行续抓更可控。
- **DEC-006**：书签每页请求 100 条。理由：减少请求数，直接缓解限流；上游若只返回 20 条，分页逻辑不受影响。
- **DEC-007**：queryId 硬编码，失效时打印维护提示，不做自动发现。理由：与现有 Likes 实现一致；自动抓取网页 bundle 维护成本高。
- **DEC-008**：不保存书签时间/顺序。理由：接口不提供书签时间；顺序只保留在 raw 响应中，投影层不造伪字段。
- **DEC-009**：独立书签验活。理由：Likes 接口正常不代表 Bookmarks 接口可用；多一次请求可以接受。
- **DEC-010**：限流、400/404、投影失败都标记 `partial`。理由：`success` 只表示完整观察，便于将来做删除检测。

## 备选方案

- **ALT-001**：单表 `twitter_tweet` 加 `liked` / `bookmarked` 布尔列。未采用：无法分别记录两个来源的 `response_id`，剪枝会互相污染，删除/刷新时布尔状态难以维护。
- **ALT-002**：新建独立宽表 `twitter_bookmark`，复制 Tweet 全部字段。未采用：同一条 Tweet 会在两张表重复存正文；用户明确要求报文一致时统一一张表。
- **ALT-003**：新增 `sync_state` 游标表。未采用：多一张基础设施表和迁移；raw 已经包含足够信息。
- **ALT-004**：单次运行内 sleep 到限流重置。未采用：可能挂起十几分钟，cron 不友好，进程中断后状态也不好恢复。
- **ALT-005**：改用官方 X API v2。未采用：需要开发者账号和付费额度，且有 800 条书签上限；当前项目使用 Cookie 方案。
- **ALT-006**：自动发现 Bookmarks queryId。未采用：需要解析 X 网页 bundle，复杂度和维护成本高，超出本阶段。
- **ALT-007**：抓取书签文件夹。未采用：用户没有会员，且 issue 未要求。

## 风险与限制

- **RISK-001**：X 内部 Bookmarks 接口的限流数值未公开；首次全量可能需要多轮。设计依赖响应头和 429，不依赖固定配额。
- **RISK-002**：queryId 会轮换；404/400 时只能打印维护提示，需要手工更新常量。
- **RISK-003**：断点游标可能过期；全量模式遇到 400 时要求 `--force` 重来。
- **RISK-004**：全量轮次期间新增的书签不会立即入库；轮次完成后由下一次增量运行从顶部补齐。
- **RISK-005**：没有书签时间/顺序；投影层无法按收藏时间排序，raw 保留原始顺序。
- **RISK-006**：不做删除检测；取消书签后的旧关系行会保留。
- **RISK-007**：迁移回填假设现有 `twitter_tweet` 全部来自点赞；当前代码确实如此，若未来有其他写入方需要重新评估。
- **RISK-008**：断点推导依赖单账号和最近一条 full run 响应；多账号前必须重新设计。
- **RISK-009**：限流响应头缺失时，只能在 429 之后停止。
- **RISK-010**：`--force` 会重新抓取全部书签，消耗配额。
- **RISK-011**：如果上游忽略 `count=100`，只是退化为更小的页，不影响正确性。
- **RISK-012**：恢复型 full run 的 `success` 表示本轮跑到末尾，但不代表一次从顶部到底部的完整观察；将来做删除检测时需要额外标记完整轮次。

## 验证方式

- **TEST-001**：迁移后 `user_version=3`，存在 `twitter_like` / `twitter_bookmark`，现有 `twitter_tweet` 行回填为点赞。
- **TEST-002**：点赞响应写入 `twitter_tweet` + `twitter_like`；书签响应写入 `twitter_tweet` + `twitter_bookmark`；同一条 Tweet 同时出现时实体只有一行。
- **TEST-003**：`db rebuild twitter` 幂等；错误负载跳过或回滚符合现有投影规则。
- **TEST-004**：Likes/Bookmarks 两种信封都能解析出 Tweet 和 bottom cursor。
- **TEST-005**：断点函数覆盖无响应、成功带 cursor、成功无 cursor、失败响应按请求游标重试、终止空页，且增量响应不参与，并且只读取 `scope='full'` 的响应。
- **TEST-006**：增量模式整页已知停止并标记 `partial`；全量模式不因整页已知停止；`--force` 从顶部开始；限流停止后下一次 `--full` 从断点继续；400/404 打印维护提示。
- **TEST-007**：CLI 的 `--bookmarks` / `--full` / `--force` / `--max-pages` 组合正确，非 `--db-only` 被拒绝，书签验活独立于点赞。
- **TEST-008**：`PYTHONPATH=src pytest tests -q`、`ruff check src tests`、`ruff format --check src tests` 全部通过；有 Cookie 时手工跑一轮 `--full --max-pages 1` 并检查 raw/投影。

## 后续工作

- 书签 Markdown 导出与索引。
- 书签文件夹（会员功能）。
- 删除检测与完整轮次标记。
- 官方 API v2 作为可选后端。
- queryId 失效/限流的 Telegram 提醒。
- 自适应限流、`--wait` 或外部调度。
- 书签顺序列（如果将来需要按收藏顺序导出，可从 raw 最近一轮重建）。
