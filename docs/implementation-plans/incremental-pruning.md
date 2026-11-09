# Incremental Pruning Implementation Plan

- Issue: [#16](https://github.com/bgzolab/export-all-to-obsidian/issues/16)
- Follow-up: [#20](https://github.com/bgzolab/export-all-to-obsidian/issues/20)
- Design: [incremental-pruning.md](../design/incremental-pruning.md)
- Branch: `feature/db-incremental-pruning`
- Status: In progress

## Goal

在 `--db-only` 下默认复用投影表数据：先跳过已存在的详情/辅助请求，再按整页
已知停止分页。`--force` 关闭剪枝，执行完整抓取。分两阶段交付。

## Stage 1. 条目级详情剪枝

- Status: Completed
- Files: `src/db/projections/<platform>.py`, 各 `src/<platform>/exporter.py`,
  `src/app/cli.py`, `tests/test_cli_db.py`, 各平台测试
- Work:
  - 在每个投影模块增加只读查询：主实体是否存在、辅助响应是否已有 provenance。
  - 仅在 `--db-only and not force` 时跳过详情/辅助请求；列表页照常抓取并写 raw。
  - bangumi: `bangumi_subject` 存在则跳过 `subject.detail`；
    `characters_response_id` 非空则跳过 `subject.characters`。
  - github: `readme_response_id` 非空则跳过 `repo.readme`；给
    `GitHubStarredResponseItem` 补 `repo_id`。
  - weibo: `long_text_response_id` 非空则跳过 `longtext`。
  - qireader: `qireader_article.url` 存在则跳过 `article`。
  - cnblog: `cnblog_post.source_url` 存在则跳过 `post.body`。
  - v2ex: `v2ex_topic` 存在则跳过 `topic.detail`；投影回复数达到
    `v2ex_topic.replies` 才跳过回复分页（中断的分页抓取必须重抓）。
  - 给 cnblog/qireader/v2ex/zhihu 补 `--force`，并传到 exporter；`--force` 在
    `--db-only` 下关闭 Stage 1/2 剪枝。
- Verify:
  - 第二次 `--db-only` 不再请求已存在的详情端点，列表端点仍然请求。
  - `--force` 下详情端点重新请求。
  - 首次运行/投影为空时行为与现在一致。
  - Stage 1 只跳详情/辅助，列表完整，因此 run 可以保持 `success`。
  - `PYTHONPATH=src pytest tests -q`、`ruff check .`、`ruff format --check .`。

## Stage 2. 整页已知停止分页

- Status: Completed（除 v2ex 外，乐观顺序假设）
- Files: 各平台 exporter、`src/app/context.py`、`tests/test_cli_db.py`
- Work:
  - 每页处理后查询该页全部自然键是否已知（按 scope）。
  - 整页已知才停止后续分页；页内有一条新数据就继续。
  - 剪枝时 `mark_run_partial()`；`--force` 不做页级停止。
  - 接入平台：github、bilibili、twitter、weibo、zhihu、cnblog、bangumi、
    qireader。
  - v2ex 暂缓页级停止：需要全局 replies pending gate；当前只做 Stage 1
    详情/回复剪枝。
  - 采用乐观策略：假设列表稳定且新数据在前，不做逐平台顺序验证。
  - V2EX 回复最多抓 200 条，expected = `min(topic.replies, 200)`。
- Verify:
  - 第二页整页已知时停止；页内混合新旧数据时继续。
  - github/weibo/bangumi/cnblog/qireader 存在详情/辅助 provenance 缺口时
    不得页级停止，继续翻页修复详情。
  - 剪枝 run 为 `partial`；`--force` run 为 `success`。
  - 不会因为剪枝漏掉同一页里的新条目。
  - 每个接入平台一条正向和一条“详情缺口继续翻页”的负向回归测试。

## Acceptance

- 默认 `--db-only` 剪枝；`--force` 完整抓取。
- 列表页始终完整抓取到已知页边界，raw 仍可用于重建。
- 剪枝 run 不参与未来删除检测。
- Stage 1 不改变普通导出（仍按 Markdown 文件存在剪枝）。
- 所有平台测试、ruff 通过。

## Execution records

- 2026-11-08: Stage 1 completed. Added projection lookup helpers for bangumi,
  github, weibo, qireader, cnblog and v2ex; `--db-only` skips known detail/aux
  requests; `--force` disables pruning and is now available on every export
  command.
- 2026-11-08: Stage 2 completed for github/bilibili/twitter. A fully known page
  stops pagination and marks the run `partial`; `--force` disables the stop.
  qireader was initially deferred until tag membership was modeled.
- 2026-11-09: GitHub page-stop now also requires no pending README provenance;
  otherwise pagination continues to repair missing READMEs. Added mixed-page,
  `--force`, complete-reply and per-platform db-only regression tests.
- 2026-11-09: Added a run-end diagnostic for persistent GitHub README gaps,
  deduplicated CNBlog `source_url` candidates, and added Bilibili/Twitter
  `--force` page-stop regression tests.
- 2026-11-09: Stage 2 extended to all platforms except v2ex under the optimistic
  ordering assumption. V2EX replies are capped at 200 with expected =
  `min(topic.replies, 200)`. Added page-stop E2E tests for weibo/zhihu/cnblog/
  bangumi/qireader.
- 2026-11-09: Added detail/aux pending gates for weibo/bangumi/cnblog/qireader
  page-level stops, plus negative E2E tests that prove pagination continues while
  a detail gap exists. Full suite: 342 passed, 2 skipped; ruff passes.
- 2026-11-09: Deduplicated pending gates into `stop_if_page_known`. Persistent
  detail gaps and V2EX repeated refetch are documented as accepted limitations;
  no deletion detection or provenance marker is added.
- 2026-11-09: Weibo/qireader/cnblog items with missing identity fields
  (`mblogid`/`url`/`link_url`) skip unreachable aux requests; pending gates
  evaluate lazily. Corrected Stage 2 scope docs (v2ex is Stage 1 only) and
  `--force` annotations; added capped V2EX refetch test.
- 2026-11-08: v2ex reply pruning compares the projected reply count with
  `v2ex_topic.replies`, so a reply fetch interrupted mid-pagination is retried
  instead of being skipped forever; dropped the unused `topic_exists` helper.

## Notes

- `--force` 在普通导出下仍表示覆盖 Markdown；在 `--db-only` 下表示关闭剪枝。
- 不能只凭“主键存在”全局判断；必须按 scope 查询。
- Qireader 的 tag membership 未建模，Stage 2 使用全局 `entry_id`；跨 tag 的
  同一 entry 视为已知，当前单账号场景接受该取舍。
- v2ex 暂不接入 Stage 2；页级停止需要全局 replies pending gate。
- 如果某个平台顺序不稳定，禁用其 Stage 2，不强行剪枝。
