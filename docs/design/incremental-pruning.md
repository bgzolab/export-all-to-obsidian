# Incremental Pruning Design

- Issue: [#16](https://github.com/bgzolab/export-all-to-obsidian/issues/16)
- Follow-up: [#20](https://github.com/bgzolab/export-all-to-obsidian/issues/20)
- Status: Proposed
- Date: 2026-11-08
- Related: [projection-layer.md](projection-layer.md)

## 1. Goal

Reduce API calls for `--db-only` by reusing data already in the projection tables.
The list pages stay the source of truth for scope and ordering; only work that is
already present is skipped.

Two stages, delivered independently:

1. **Item-level skip**: still fetch every list page, but skip detail/aux requests
   whose projection row and auxiliary provenance already exist.
2. **Page-level stop**: after processing a list page, stop pagination when every
   item on that page is already known.

Normal export keeps its current Markdown-file pruning. This design only changes
`--db-only`; otherwise a missing Markdown file could be skipped because the DB row
already exists.

## 2. Defaults and `--force`

- Default: prune in `--db-only`.
- `--force`: disable pruning, fetch and upsert the full scope again.
- V2EX replies are capped at 200 per topic; the expected count is
  `min(topic.replies, 200)`. Replies after that are intentionally not fetched.
- Stage 1 skips only detail/aux requests; list pages are complete, so the run may stay
  `success`. It still is not a full refresh of mutable details.
- Stage 2 stops pagination early; those runs must be `partial` and must never drive future
  deletion detection.
- A `--force` full run may be `success` and can drive deletion detection later.
- `--force` keeps its existing Markdown-overwrite meaning outside `--db-only`.

`--force` must be available on every export subcommand for this reason. Platforms
that do not have detail/aux requests still need it for Stage 2.

## 3. What “known” means

Known is per entity and per scope, never globally:

| Platform | Entity key | Scope |
| --- | --- | --- |
| bangumi | `subject_id` | `type` + `subject_type` |
| bilibili | `media_id` | `fav_id` membership |
| cnblog | `wz_link_id` | single account |
| github | `repo_id` | single account |
| qireader | `entry_id` | tag (`tag_ids_json` contains the tag) |
| twitter | `tweet_id` | single account |
| v2ex | `topic_id` | single account |
| weibo | `post_id` | single account (uid scope) |
| zhihu | `content_id` | `collection_id` membership |

Stage 1 uses the same keys for detail/aux checks:

- bangumi: skip `subject.detail` if `bangumi_subject` exists; skip
  `subject.characters` if `characters_response_id IS NOT NULL`.
- github: skip `repo.readme` if `readme_response_id IS NOT NULL`.
  Page-level stop additionally requires `readme_pending_count == 0`; otherwise
  pagination continues so missing READMEs can be repaired per item.
- qireader: skip `article` if `qireader_article.url` exists.
- cnblog: skip `post.body` if `cnblog_post.source_url` exists.
- v2ex: skip `topic.detail` if `v2ex_topic` exists; skip reply pages only when the
  projected reply count reaches `v2ex_topic.replies` (an interrupted reply fetch
  leaves a partial thread and must be retried).
- weibo: skip `longtext` if `long_text_response_id IS NOT NULL` for the `mblogid`.

Bilibili, Twitter and Zhihu have no detail/aux calls in Stage 1; they participate
in Stage 2 only.

## 4. Ordering assumptions

Stage 2 assumes each list is ordered newest-first by a stable platform time, and
that existing rows do not move behind newer rows:

| Platform | Order | Risk |
| --- | --- | --- |
| twitter | cursor, reverse chronological | low |
| qireader | `olderThan` timestamp cursor | low (global entry id check) |
| github | default `created` desc | low |
| bilibili | `order=mtime` desc | low |
| weibo | time desc (verify) | medium |
| zhihu | collection time desc (verify) | medium |
| cnblog | DateAdded desc (verify) | medium |
| bangumi | likely updated_at desc (verify) | medium |
| v2ex | likely last-reply order (verify) | medium |

Because of the medium-risk rows, Stage 2 uses “the whole page is known” rather
than “the first known item”. A page with one new item still continues to the next
page. This tolerates interleaved new/old items and page shifts better than
stopping on the first match.

If a platform’s order is later found unstable, its page-level stop is disabled
and only Stage 1 remains.

## 5. Interaction with projections and raw

- List pages are always fetched and recorded in raw; only detail/aux requests are
  skipped in Stage 1.
- The projection is rebuilt after the fetch inside the same `--db-only` run. The
  next run sees the previous run’s projection.
- A failed projection leaves the previous rows in place; if a row is missing, the
  next run fetches it again. This is safe (at worst duplicate raw rows).
- `--force` full runs append duplicate raw responses for existing entities. The
  raw layer stays append-only; projection upserts keep one row per natural key.
- No raw deletion or dedupe is introduced.
- V2EX replies are capped at 200 per topic. If the platform count includes
  deleted/invisible replies, the projected count is compared against
  `min(topic.replies, 200)`, so the cap is still reachable.
- All platforms use the optimistic page-level stop: the list is assumed stable
  and ordered newest-first; no per-platform ordering verification is done.
- Qireader page-level stop uses the global `qireader_entry.entry_id`; tag
  membership is not modeled, so the same entry in another tag is considered
  known. This is accepted for the current single-account, optimistic design.

## 6. Deletion and multi-account

- Stage 2 pruned runs are `partial`; only a complete `success` run may drive deletion.
- Stage 1 keeps list completeness, so its runs can stay `success`; they are not a full
  detail refresh, which is what `--force` is for.
- `--force` is the supported way to produce a complete full refresh.
- Single-account assumption is unchanged.

## 7. Non-goals

- No HTTP ETag/Last-Modified cache yet.
- No raw response dedupe.
- No deletion detection in this stage.
- No page-level stop for normal Markdown export; file-existence pruning remains.
