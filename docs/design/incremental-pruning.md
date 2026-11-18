# Incremental Pruning Design

- Issue: [#16](https://github.com/bgzolab/export-all-to-obsidian/issues/16)
- Follow-up: [#20](https://github.com/bgzolab/export-all-to-obsidian/issues/20)
- PR: [#21](https://github.com/bgzolab/export-all-to-obsidian/pull/21)
- Status: 已实现
- Date: 2026-11-09
- Related: [projection-layer.md](projection-layer.md)

## 1. 目标

在 `--db-only` 下复用投影表已有数据，减少 API 调用。列表页仍然是范围和顺序的
事实来源，只跳过已经完成的工作。

分两阶段交付：

1. **条目级详情剪枝**：仍抓取全部列表页，但跳过主行和辅助 provenance 都已存在的
   详情/辅助请求。
2. **整页已知停止分页**：处理完一页后，如果该页所有条目都已知，停止后续分页。

普通导出保持现有的 Markdown 文件剪枝，不受本设计影响。否则数据库里已有行、但
Markdown 文件缺失时，会被错误跳过。

## 2. 默认行为与 `--force`

- `--db-only` 默认剪枝。
- `--force` 关闭剪枝，重新抓取并 upsert 完整范围；所有导出子命令都提供该选项。
- Stage 1 只跳过详情/辅助请求，列表页仍完整，因此 run 可以保持 `success`。它不是
  可变详情的完整刷新。
- Stage 2 会提前停止分页，这些 run 必须标记为 `partial`，且不得用于将来的删除检测。
  例外：v2ex 在收藏页整页重复上一页时停止，表示越界分页已枚举完，run 保持
  `success`。
- 完整的 `--force` run 可以是 `success`，将来可以用于删除检测。
- 普通导出下，`--force` 仍然表示覆盖已有 Markdown。
- V2EX 每个主题最多抓 200 条回复，expected = `min(topic.replies, 200)`；超过部分
  有意不抓。

## 3. “已知”的定义

“已知”按实体和 scope 判断，不能只看主键全局存在：

| Platform | Entity key | Scope |
| --- | --- | --- |
| bangumi | `subject_id` | `type` + `subject_type` |
| bilibili | `media_id` | `fav_id` membership |
| cnblog | `wz_link_id` | single account |
| github | `repo_id` | single account |
| qireader | `entry_id` | single account (global `entry_id`; tag membership not modeled) |
| twitter | `tweet_id` | single account |
| twitter bookmarks | `tweet_id` | single account; checked in `twitter_bookmark` |
| v2ex | `topic_id` | single account |
| weibo | `post_id` | single account (uid scope) |
| zhihu | `content_id` | `collection_id` membership |

Stage 1 使用同一组 key 判断详情/辅助数据：

- bangumi：`bangumi_subject` 存在则跳过 `subject.detail`；`characters_response_id`
  非空则跳过 `subject.characters`。
- github：`readme_response_id` 非空则跳过 `repo.readme`；star 实体保存 `repo_id`
  用于 scope 匹配。页级停止还要求 `readme_pending_count == 0`，否则继续翻页，让
  逐条处理修复缺失 README。
- weibo：`long_text_response_id` 非空则跳过 `longtext`。页级停止还要求
  `long_text_pending_count == 0`；缺少 `mblogid` 的条目无法修复，直接跳过长文
  请求，也不计入 pending。
- qireader：`qireader_article.url` 存在则跳过 `article`。页级停止还要求
  `article_pending_count == 0`；空 `url` 的条目跳过正文抓取，也不计入 pending。
- cnblog：`link_url` 能解析出数字 `post_id` 且 `cnblog_post` 存在则跳过
  `post.body`。页级停止要求“本轮未见过”的 pending 为 0，本轮已处理页里的缺口不再
  阻塞停止；pending 只统计能解析 `post_id` 的 `from_cnblogs` 书签，空 `link_url` 或
  slug-only URL 跳过正文抓取，也不计入 pending。
- v2ex：`v2ex_topic` 存在则跳过 `topic.detail`；回复分页只在投影回复数达到
  `min(topic.replies, 200)` 时跳过。中断的回复抓取只留下页面前缀，计数必然不足，
  下一轮会重抓。

Bilibili、Twitter、Zhihu 在 Stage 1 没有详情/辅助请求，只参与 Stage 2。

## 4. 顺序假设与页级停止

Stage 2 假设每个列表按平台时间稳定地新数据在前，且已有行不会移动到新行之后：

| Platform | Order | Risk |
| --- | --- | --- |
| twitter | cursor, reverse chronological | low |
| twitter bookmarks | cursor, bookmark order | low (no bookmark timestamp column) |
| qireader | `olderThan` timestamp cursor | low (global entry id check) |
| github | default `created` desc | low |
| bilibili | `order=mtime` desc | low |
| weibo | time desc (verify) | medium |
| zhihu | collection time desc (verify) | medium |
| cnblog | DateAdded desc (verify) | medium |
| bangumi | likely updated_at desc (verify) | medium |

Stage 2 已接入 github、bilibili、twitter、weibo、zhihu、cnblog、bangumi、qireader。
v2ex 收藏页只在整页重复上一页时停止（越界分页，视为列表已枚举完），run 保持
`success`；收藏的“整页已知”式停止仍暂缓：停止收藏页分页需要全局 replies pending gate，
否则可能把未完成的回复抓取永久锁在更深页。`v2ex --tipped` 的余额页级停止不受此限制，
见下。

因为存在 medium-risk 平台，Stage 2 使用“整页已知”而不是“遇到第一个已知条目”：

- 一页里只要有一条新数据，就继续下一页。
- 这样能容忍新旧交错和分页位移。
- 如果某平台顺序后来被确认不稳定，禁用其 Stage 2，只保留 Stage 1。

github/weibo/bangumi/qireader 的页级停止还要求各自的详情/辅助 pending
count 为 0；存在缺口时继续翻页，由逐条处理补抓，避免页级停止把缺口锁死。
cnblog 只要求“本轮未见过”的 pending 为 0：已处理页里的缺口本轮已经重试过，
继续翻页也不会再修，因此不阻塞停止。

### Twitter 书签模式

书签只在 `--db-only` 下入库，不参与 Markdown 导出：

- 默认增量：从顶部开始；整页 `tweet_id` 都已在 `twitter_bookmark` 时停止，run 标记
  `partial`，下次仍从顶部开始。
- `--full`：从 `latest_bookmark_checkpoint` 推导的断点继续；不触发整页已知停止；到列表
  末尾的 run 为 `success`，限流、页数上限、游标停滞或失败为 `partial`。
- `--force`：隐含 `--full` 并忽略断点，从顶部重开一轮全量抓取。
- 断点只读取 `sync_run.scope='full'` 的 `twitter.bookmarks.page` 响应，增量响应不参与。
- 只有 cursor、且 bottom cursor 与请求 cursor 相同的空页表示列表末尾，按 `success` 结束。
- 点赞剪枝查 `twitter_like`，书签剪枝查 `twitter_bookmark`，两者互不污染。
- 关系表 `twitter_bookmark` 是剪枝事实来源；`twitter_tweet` 仅保存共享 Tweet 内容。

### V2EX 投币模式（--tipped）

投币主题只入库，不参与 Markdown 导出：

- 余额页按时间倒序且分页稳定；当整页 `发送谢意` 交易都已存在 `v2ex_thanks` 时停止
  翻页，run 标记 `partial`，下次仍从第 1 页开始。
- 页级停止只负责发现新感谢，不判断主题详情/回复是否完整。停止翻页后必须继续扫描
  `tipped_topic_ids` 的全部主题；否则第 1 页全部命中时，上一轮因 600 次/小时 API
  配额未补齐的旧主题会被永久跳过。这是与收藏页剪枝最关键的区别。
- `--force` 关闭余额页和主题详情/回复剪枝，重抓完整余额页及全部主题。
- 余额页没有 `max_page` 时，用 `transaction_keys` 与上一页比较检测重复末页，并用
  1000 页上限兜底。
- 余额页是 HTML，不占 V2EX API 2.0 配额；主题详情和回复占配额。
- 余额页缺少流水表（维护/风控页）时同样按 `partial` 结束翻页，但**主题扫描照常执行**：
  HTML 异常不一定意味着 API 也异常，继续扫描仍可能补齐详情/回复，且连续失败中止会
  限制空转；若 API 也异常，本轮在阈值处停止，剩余主题留给下一轮。
- 永不补齐的回复缺口（例如被删除的回复）每轮都会重新抓取该主题的回复页，append-only
  raw 因此每轮新增一批重复响应。投币模式把这个成本从收藏集合扩大到全部投币主题。

## 5. 与投影层、raw 层的交互

- 列表页始终抓取并写入 raw；Stage 1 只跳过详情/辅助请求。
- 投影在 `--db-only` run 的抓取结束后、同一个 `sync_run` 内重建。下一轮 run 看到
  的是上一轮重建后的投影。
- 投影重建失败时保留旧行；缺行会在下一轮重新抓取。最坏情况只是 raw 追加重复响应，
  不影响正确性。
- `--force` 完整抓取会为已有实体追加重复 raw 响应；raw 保持 append-only，投影
  upsert 保证每个自然键只有一行。
- 不引入 raw 删除或去重。
- pending gate 惰性求值：只有整页已知、准备停止分页时才查询 pending count。
- V2EX 回复上限为 200。若平台计数包含已删除/不可见回复，投影计数可能低于
  expected；此时该主题每轮都会重抓，200 上限限制最坏成本，空页 provenance 完成
  标记暂缓。
- 所有页级停止平台都采用乐观顺序假设，不做逐平台顺序验证。
- Qireader 使用全局 `qireader_entry.entry_id`；tag membership 未建模，同一 entry
  出现在另一个 tag 时也视为已知。当前单账号场景接受该取舍。

## 6. 删除与多账号

- Stage 2 剪枝 run 为 `partial`，只有完整的 `success` run 才能驱动删除检测。
- Stage 1 保持列表完整，所以 run 可以是 `success`；它不是完整详情刷新，完整刷新
  使用 `--force`。
- `--force` 是产生完整全量刷新的受支持方式。
- 单账号假设不变。

## 7. 已知限制与后续工作

- 不可修复的 pending 行（例如条目已取消收藏/删除，但详情仍缺失）会永久禁用
  github/weibo/bangumi/qireader 的页级停止。run 会回退到 Stage 1，安全但更慢；清理
  这类行需要删除检测或手工处理，均不在当前范围。cnblog 例外：pending 只统计“本轮
  未见过”的书签，已处理页里的缺口不会永久阻塞停止，只在运行末尾的缺口报告中出现。
- V2EX 不可见回复导致的重复抓取由 200 条上限约束；空页 provenance marker 暂缓。
- v2ex 收藏的“整页已知”式页级停止暂缓，需要全局 replies pending gate；重复页停止已启用。
  v2ex --tipped 的余额页级停止不受此限制，因为停止后仍会全量扫描投币主题。
- Qireader tag membership 未建模，使用全局 entry id。
- 不做多账号。

## 8. 验证

- `PYTHONPATH=src pytest tests -q`、`ruff check src tests`、
  `ruff format --check src tests` 通过。
- 回归覆盖：
  - 第二次 `--db-only` 不再请求已存在的详情/辅助端点，列表端点仍然请求。
  - `--force` 重新请求详情/辅助端点，且不触发页级停止。
  - 整页已知时停止分页并标记 `partial`；页内混合新旧数据时继续。
  - github/weibo/bangumi/qireader 存在详情/辅助缺口时继续翻页并补抓，run 保持
    `success`。
  - cnblog 只对“本轮未见过”的书签要求 pending 为 0；页级停止 run 为 `partial`。
  - V2EX 回复中断后重抓；达到 200 条上限后跳过；低于 capped expected 时重抓。
  - V2EX 收藏页整页重复上一页时停止分页，run 保持 `success`。
  - v2ex --tipped 整页已知时停止余额翻页并标记 `partial`，但仍补齐历史投币主题；
    `--force` 重抓完整余额页和全部主题。
  - weibo/qireader/cnblog 缺少身份字段的条目不再发起注定无效的请求。

## 9. 非目标

- 不做 HTTP ETag / Last-Modified 缓存。
- 不做 raw 响应去重。
- 本阶段不做删除检测。
- 普通 Markdown 导出不做页级停止，仍使用文件存在性剪枝。
