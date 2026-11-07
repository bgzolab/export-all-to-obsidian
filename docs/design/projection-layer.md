# Projection Layer Design

- Issue: [#16](https://github.com/bgzolab/export-all-to-obsidian/issues/16)
- Status: Proposed
- Date: 2026-11-07
- Related: [raw-response-layer.md](raw-response-layer.md), [#18](https://github.com/bgzolab/export-all-to-obsidian/issues/18)

## 1. 目标

从 raw 层解析出平台实体，落成可查询、可导出、可幂等重建的投影表。投影层是 Markdown
导出的主要数据源；raw 层只负责保存、灾难恢复和全量重放。

本层不做统一模型，不为一个平台建立超过三张表，不引入 ORM。

非目标：

- 不做跨平台统一 `item` 表。
- 不做删除检测；v1 只记录观察水位，删除策略以后再加。
- 不做多账号；当前所有表都假设每个平台只有一个认证账号。
- 不把分页、状态码、`code` / `message` / `has_more` / `ttl` 等响应信封存进实体表。
- 不承诺上游字段 100% 落列；`raw_json` 兜底。

## 2. 核心约定

1. 一张表对应一个实体，不是一次响应。每平台 1-3 张表。
2. 表名使用 `<platform>_<entity>`，例如 `bangumi_collection`、`zhihu_collection_item`。
3. 业务自然键做主键；关系表用复合主键；不使用自增 id 做业务主键。
4. 顶层标量字段落列；对象/数组字段落 `*_json` 列，并用
   `CHECK (json_valid(...))` 约束。
5. 每个实体行保留 `raw_json`，保存最近一次观察到的实体 JSON。
6. 溯源列固定为 `response_id`、`last_seen_run_id`、`first_seen_at`、`last_seen_at`。
   时间取对应 `sync_response.fetched_at`，run 取 `sync_run.id`，不取当前时间，保证重放可复现。
7. 正常查询和导出不 join `sync_run` / `sync_response`；raw 层只在全量重建时读取。
8. 时间保持 API 原生类型：epoch 用 `INTEGER`，字符串用 `TEXT`；格式化留给导出层。
9. 新表使用 SQLite `STRICT`，要求 SQLite >= 3.37；当前运行环境 3.45.1。
10. 单账号假设。以后要多账号时，增加账号列并调整主键，不在 v1 提前设计。

### 2.1 列选择规则

列按下述优先级选取，其余字段留在 `raw_json`：

1. 当前平台 dataclass/entity 的全部字段。
2. 自然键、创建/更新时间、收藏/保存时间、状态、计数。
3. 现有或计划中的导出模板会读取的字段。
4. 明显会用于过滤或排序的字段。

以后需要新列时，用 `ALTER TABLE ADD COLUMN` 加迁移，再从 `raw_json` 回填：

```sql
ALTER TABLE github_star ADD COLUMN watchers_count INTEGER NOT NULL DEFAULT 0;
UPDATE github_star
SET watchers_count = COALESCE(json_extract(raw_json, '$.repo.watchers_count'), 0);
```

这是“尽量全但不强求全”的边界。GitHub 这类上游对象字段过多，不逐个铺列。

### 2.2 通用列

实体表统一追加：

```sql
response_id INTEGER NOT NULL REFERENCES sync_response(id),
last_seen_run_id INTEGER NOT NULL REFERENCES sync_run(id),
first_seen_at TEXT NOT NULL,
last_seen_at TEXT NOT NULL,
raw_json TEXT NOT NULL CHECK (json_valid(raw_json))
```

语义：

- `response_id`：最近一次主响应的 id。
- `last_seen_run_id`：最近一次观察到该实体的 run，留给未来的完整 run 删除扫描。
- `first_seen_at`：第一次观察时间，只在插入时写。
- `last_seen_at`：最近一次主响应观察时间，每次主响应更新。
- `raw_json`：实体 JSON，不含响应信封；序列化使用紧凑格式，保证重放字节稳定。

`raw_json` 例外：

- 纯载荷表 `cnblog_post`、`qireader_article`：`body` / `content` 列本身就是原始载荷，不再重复存
  `raw_json`。
- 关系表 `bilibili_fav_item`、`v2ex_favorite`、`zhihu_collection_item`：没有独立实体 JSON，
  通过 `response_id` 回溯。

### 2.3 主响应与辅助响应

一个实体可能由多个接口共同补全：

- 主响应：列表或详情响应，决定 `response_id`、`last_seen_run_id`、`last_seen_at`。
- 辅助响应：README、长文、正文、角色列表等，只更新自己的列和 `*_response_id`，
  不覆盖主响应的溯源列。

这样 `raw_json` 始终与 `response_id` 对应，不会被辅助响应打乱。

## 3. 平台表

迁移 `002_projection_layer.sql` 一次建好下列 16 张表和索引。解析器按平台逐步实现，
未实现的平台表保持为空。

### 3.1 Bangumi（pilot）

来源接口：

- `bangumi.collections.page` -> `bangumi_collection`
- `bangumi.subject.detail` -> `bangumi_subject`
- `bangumi.subject.characters` -> 辅助更新 `bangumi_subject.characters_json`

说明：

- `bangumi_collection.subject_id` 是自然主键；`collection_id` 是 API 的收藏记录 id，
  可以为空，只做唯一约束。
- `type` 是收藏类型（想看/看过/在看等），`subject_type` 是条目类型。
- `subject_json` 保存列表里的 slim subject。
- 角色列表是集合元素，按约定存 `characters_json`，不单独建表。
  `characters_response_id` 单独记录，不覆盖主响应溯源列。

```sql
CREATE TABLE bangumi_collection (
    subject_id INTEGER PRIMARY KEY,
    collection_id INTEGER UNIQUE,
    updated_at TEXT,
    comment TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(tags_json)),
    vol_status INTEGER NOT NULL DEFAULT 0,
    ep_status INTEGER NOT NULL DEFAULT 0,
    subject_type INTEGER NOT NULL,
    rate INTEGER NOT NULL DEFAULT 0,
    type INTEGER NOT NULL,
    private INTEGER NOT NULL DEFAULT 0 CHECK (private IN (0, 1)),
    subject_json TEXT NOT NULL CHECK (json_valid(subject_json)),
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    last_seen_run_id INTEGER NOT NULL REFERENCES sync_run(id),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    raw_json TEXT NOT NULL CHECK (json_valid(raw_json))
) STRICT;

CREATE INDEX idx_bangumi_collection_type
    ON bangumi_collection(type, subject_type);

CREATE TABLE bangumi_subject (
    subject_id INTEGER PRIMARY KEY,
    date TEXT,
    platform TEXT,
    images_json TEXT CHECK (json_valid(images_json)),
    summary TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    name_cn TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(tags_json)),
    infobox_json TEXT CHECK (json_valid(infobox_json)),
    rating_json TEXT CHECK (json_valid(rating_json)),
    total_episodes INTEGER NOT NULL DEFAULT 0,
    collection_json TEXT CHECK (json_valid(collection_json)),
    eps INTEGER NOT NULL DEFAULT 0,
    meta_tags_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(meta_tags_json)),
    volumes INTEGER NOT NULL DEFAULT 0,
    series INTEGER NOT NULL DEFAULT 0 CHECK (series IN (0, 1)),
    locked INTEGER NOT NULL DEFAULT 0 CHECK (locked IN (0, 1)),
    nsfw INTEGER NOT NULL DEFAULT 0 CHECK (nsfw IN (0, 1)),
    type_id INTEGER NOT NULL DEFAULT 0,
    redirect INTEGER,
    characters_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(characters_json)),
    characters_response_id INTEGER REFERENCES sync_response(id),
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    last_seen_run_id INTEGER NOT NULL REFERENCES sync_run(id),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    raw_json TEXT NOT NULL CHECK (json_valid(raw_json))
) STRICT;

CREATE INDEX idx_bangumi_subject_type
    ON bangumi_subject(type_id);
```

### 3.2 Bilibili

来源接口：

- `bilibili.favlist.page` -> `bilibili_fav` + `bilibili_media` + `bilibili_fav_item`

说明：

- `bilibili_fav` 来自每页响应的 `data.info`，主键 `fav_id` 取 `info.id`。
- `bilibili_media` 来自 `data.medias[]`，主键 `media_id` 取视频的 `id`。
- `bilibili_fav_item` 是收藏夹与视频的多对多关系。`fav_time` 放在关系表，因为同一视频
  可以出现在多个收藏夹，收藏时间不同。
- `code` / `message` / `ttl` / `has_more` 不落表。

```sql
CREATE TABLE bilibili_fav (
    fav_id INTEGER PRIMARY KEY,
    fid INTEGER NOT NULL,
    mid INTEGER NOT NULL,
    attr INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT '',
    cover TEXT NOT NULL DEFAULT '',
    upper_json TEXT CHECK (json_valid(upper_json)),
    cover_type INTEGER NOT NULL DEFAULT 0,
    cnt_info_json TEXT CHECK (json_valid(cnt_info_json)),
    type INTEGER NOT NULL DEFAULT 0,
    intro TEXT NOT NULL DEFAULT '',
    ctime INTEGER NOT NULL DEFAULT 0,
    mtime INTEGER NOT NULL DEFAULT 0,
    state INTEGER NOT NULL DEFAULT 0,
    fav_state INTEGER NOT NULL DEFAULT 0,
    like_state INTEGER NOT NULL DEFAULT 0,
    media_count INTEGER NOT NULL DEFAULT 0,
    is_top INTEGER NOT NULL DEFAULT 0 CHECK (is_top IN (0, 1)),
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    last_seen_run_id INTEGER NOT NULL REFERENCES sync_run(id),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    raw_json TEXT NOT NULL CHECK (json_valid(raw_json))
) STRICT;

CREATE INDEX idx_bilibili_fav_fid
    ON bilibili_fav(fid);

CREATE TABLE bilibili_media (
    media_id INTEGER PRIMARY KEY,
    type INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT '',
    cover TEXT NOT NULL DEFAULT '',
    intro TEXT NOT NULL DEFAULT '',
    page INTEGER NOT NULL DEFAULT 0,
    duration INTEGER NOT NULL DEFAULT 0,
    upper_json TEXT CHECK (json_valid(upper_json)),
    attr INTEGER NOT NULL DEFAULT 0,
    cnt_info_json TEXT CHECK (json_valid(cnt_info_json)),
    link TEXT NOT NULL DEFAULT '',
    ctime INTEGER NOT NULL DEFAULT 0,
    pubtime INTEGER NOT NULL DEFAULT 0,
    bv_id TEXT NOT NULL DEFAULT '',
    bvid TEXT NOT NULL DEFAULT '',
    ugc_json TEXT CHECK (json_valid(ugc_json)),
    media_list_link TEXT NOT NULL DEFAULT '',
    season_json TEXT CHECK (json_valid(season_json)),
    ogv_json TEXT CHECK (json_valid(ogv_json)),
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    last_seen_run_id INTEGER NOT NULL REFERENCES sync_run(id),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    raw_json TEXT NOT NULL CHECK (json_valid(raw_json))
) STRICT;

CREATE INDEX idx_bilibili_media_bvid
    ON bilibili_media(bvid);

CREATE TABLE bilibili_fav_item (
    fav_id INTEGER NOT NULL REFERENCES bilibili_fav(fav_id),
    media_id INTEGER NOT NULL REFERENCES bilibili_media(media_id),
    fav_time INTEGER NOT NULL DEFAULT 0,
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    last_seen_run_id INTEGER NOT NULL REFERENCES sync_run(id),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (fav_id, media_id)
) STRICT;

CREATE INDEX idx_bilibili_fav_item_media
    ON bilibili_fav_item(media_id);
```

### 3.3 CNBlog

来源接口：

- `cnblog.bookmarks.page` -> `cnblog_bookmark`
- `cnblog.post.body` -> `cnblog_post`

说明：

- `cnblog_bookmark` 主键 `wz_link_id` 对应 API 的 `WzLinkId`。
- `cnblog_post` 主键是从正文请求 URL 中解析出的 post id；`body` 是 HTML 原始载荷，
  所以不设 `raw_json`。

```sql
CREATE TABLE cnblog_bookmark (
    wz_link_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    link_url TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(tags_json)),
    date_added TEXT,
    from_cnblogs INTEGER NOT NULL DEFAULT 0 CHECK (from_cnblogs IN (0, 1)),
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    last_seen_run_id INTEGER NOT NULL REFERENCES sync_run(id),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    raw_json TEXT NOT NULL CHECK (json_valid(raw_json))
) STRICT;

CREATE INDEX idx_cnblog_bookmark_link_url
    ON cnblog_bookmark(link_url);

CREATE TABLE cnblog_post (
    post_id INTEGER PRIMARY KEY,
    source_url TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL,
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    last_seen_run_id INTEGER NOT NULL REFERENCES sync_run(id),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
) STRICT;
```

### 3.4 GitHub

来源接口：

- `github.stars.list` -> `github_star`
- `github.repo.readme` -> 辅助更新 `github_star.readme`

说明：

- 主键 `repo_id` 取 API 的 `repo.id`。当前 dataclass 没有这个字段，投影解析器直接读
  `raw_json` 补上；仓库改名时仍能按 id 更新同一行。
- `full_name` 唯一，用于展示和文件名。
- 当前 entity 字段全部落列；上游其余字段留在 `raw_json`，以后按 2.1 的规则加列。
- README 是辅助响应，只更新 `readme` 和 `readme_response_id`。

```sql
CREATE TABLE github_star (
    repo_id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL UNIQUE,
    html_url TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    owner_login TEXT NOT NULL DEFAULT '',
    repo_name TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT '',
    topics_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(topics_json)),
    stargazers_count INTEGER NOT NULL DEFAULT 0,
    forks_count INTEGER NOT NULL DEFAULT 0,
    open_issues_count INTEGER NOT NULL DEFAULT 0,
    fork INTEGER NOT NULL DEFAULT 0 CHECK (fork IN (0, 1)),
    archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
    private INTEGER NOT NULL DEFAULT 0 CHECK (private IN (0, 1)),
    homepage TEXT NOT NULL DEFAULT '',
    license TEXT NOT NULL DEFAULT '',
    created_at TEXT,
    updated_at TEXT,
    pushed_at TEXT,
    starred_at TEXT,
    readme TEXT NOT NULL DEFAULT '',
    readme_response_id INTEGER REFERENCES sync_response(id),
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    last_seen_run_id INTEGER NOT NULL REFERENCES sync_run(id),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    raw_json TEXT NOT NULL CHECK (json_valid(raw_json))
) STRICT;

CREATE INDEX idx_github_star_owner
    ON github_star(owner_login);

CREATE INDEX idx_github_star_starred_at
    ON github_star(starred_at);
```

### 3.5 QiReader

来源接口：

- `qireader.readlater.page` -> `qireader_entry`
- `qireader.article` -> `qireader_article`

说明：

- 正文接口只按 URL 取内容，不返回 entry id，所以正文单独一张表，按 URL 与 entry 关联。
- `timestamp` 是 API 的纳秒字符串，也是分页游标，保持 `TEXT`。
- `published_at` / `crawled_at` 是毫秒 epoch，保持 `INTEGER`。
- `content` 是正文原始载荷，不设 `raw_json`。

```sql
CREATE TABLE qireader_entry (
    entry_id TEXT PRIMARY KEY,
    is_saved INTEGER NOT NULL DEFAULT 0 CHECK (is_saved IN (0, 1)),
    source_entry_id TEXT NOT NULL DEFAULT '',
    origin_json TEXT CHECK (json_valid(origin_json)),
    title TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    published_at INTEGER NOT NULL DEFAULT 0,
    crawled_at INTEGER NOT NULL DEFAULT 0,
    timestamp TEXT NOT NULL DEFAULT '',
    attachments_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(attachments_json)),
    tag_ids_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(tag_ids_json)),
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    last_seen_run_id INTEGER NOT NULL REFERENCES sync_run(id),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    raw_json TEXT NOT NULL CHECK (json_valid(raw_json))
) STRICT;

CREATE INDEX idx_qireader_entry_url
    ON qireader_entry(url);

CREATE INDEX idx_qireader_entry_timestamp
    ON qireader_entry(timestamp);

CREATE TABLE qireader_article (
    url TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    last_seen_run_id INTEGER NOT NULL REFERENCES sync_run(id),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
) STRICT;
```

### 3.6 Twitter

来源接口：

- `twitter.likes.page` -> `twitter_tweet`

说明：

- 主键 `tweet_id` 对应 `Tweet.id_str`。
- `author_json` 存归一化后的作者对象（`screen_name` / `name` / `id`）；完整 GraphQL
  节点留在 `raw_json`。
- 点赞列表不提供点赞时间，不造 `liked_at`。
- 单账号，表内每一行都表示当前账号的点赞，不另建关系表。

```sql
CREATE TABLE twitter_tweet (
    tweet_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT '',
    full_text TEXT NOT NULL DEFAULT '',
    author_json TEXT NOT NULL CHECK (json_valid(author_json)),
    favorite_count INTEGER NOT NULL DEFAULT 0,
    retweet_count INTEGER NOT NULL DEFAULT 0,
    reply_count INTEGER NOT NULL DEFAULT 0,
    view_count INTEGER NOT NULL DEFAULT 0,
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    last_seen_run_id INTEGER NOT NULL REFERENCES sync_run(id),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    raw_json TEXT NOT NULL CHECK (json_valid(raw_json))
) STRICT;

CREATE INDEX idx_twitter_tweet_created_at
    ON twitter_tweet(created_at);
```

### 3.7 V2EX

来源接口：

- `v2ex.fav.page` -> `v2ex_favorite`
- `v2ex.topic.detail` -> `v2ex_topic`

说明：

- 收藏列表是 HTML，没有对应实体 JSON；`v2ex_favorite` 只保存 membership 和溯源列。
- 不建 `v2ex_favorite.topic_id -> v2ex_topic.topic_id` 外键：收藏列表先到，主题详情可能
  抓取失败，外键会让合法收藏无法入库。
- `member_json` / `node_json` / `supplements_json` 保存嵌套结构。

```sql
CREATE TABLE v2ex_topic (
    topic_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    syntax INTEGER NOT NULL DEFAULT 0,
    url TEXT NOT NULL DEFAULT '',
    replies INTEGER NOT NULL DEFAULT 0,
    last_reply_by TEXT NOT NULL DEFAULT '',
    created INTEGER NOT NULL DEFAULT 0,
    last_modified INTEGER NOT NULL DEFAULT 0,
    last_touched INTEGER NOT NULL DEFAULT 0,
    member_json TEXT CHECK (json_valid(member_json)),
    node_json TEXT CHECK (json_valid(node_json)),
    supplements_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(supplements_json)),
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    last_seen_run_id INTEGER NOT NULL REFERENCES sync_run(id),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    raw_json TEXT NOT NULL CHECK (json_valid(raw_json))
) STRICT;

CREATE INDEX idx_v2ex_topic_last_touched
    ON v2ex_topic(last_touched);

CREATE TABLE v2ex_favorite (
    topic_id INTEGER PRIMARY KEY,
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    last_seen_run_id INTEGER NOT NULL REFERENCES sync_run(id),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
) STRICT;
```

### 3.8 Weibo

来源接口：

- `weibo.likes.page` -> `weibo_post`
- `weibo.longtext` -> 辅助更新 `weibo_post.long_text`

说明：

- 主键 `post_id` 用 `idstr`，避免大整数在跨语言工具里失真；`numeric_id` 保留原 `id`。
- `mblogid` 用于构造微博 URL，唯一但允许为空。
- `user_json`、`pic_ids_json`、`pic_infos_json` 保存嵌套结构。
- 长文是辅助响应，只更新 `long_text` 和 `long_text_response_id`。

```sql
CREATE TABLE weibo_post (
    post_id TEXT PRIMARY KEY,
    numeric_id INTEGER UNIQUE,
    mid TEXT NOT NULL DEFAULT '',
    mblogid TEXT UNIQUE,
    created_at TEXT NOT NULL DEFAULT '',
    user_json TEXT CHECK (json_valid(user_json)),
    text TEXT NOT NULL DEFAULT '',
    text_raw TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    favorited INTEGER NOT NULL DEFAULT 0 CHECK (favorited IN (0, 1)),
    pic_num INTEGER,
    pic_ids_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(pic_ids_json)),
    pic_infos_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(pic_infos_json)),
    reposts_count INTEGER NOT NULL DEFAULT 0,
    comments_count INTEGER NOT NULL DEFAULT 0,
    attitudes_count INTEGER NOT NULL DEFAULT 0,
    is_long_text INTEGER NOT NULL DEFAULT 0 CHECK (is_long_text IN (0, 1)),
    region_name TEXT NOT NULL DEFAULT '',
    long_text TEXT,
    long_text_response_id INTEGER REFERENCES sync_response(id),
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    last_seen_run_id INTEGER NOT NULL REFERENCES sync_run(id),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    raw_json TEXT NOT NULL CHECK (json_valid(raw_json))
) STRICT;

CREATE INDEX idx_weibo_post_created_at
    ON weibo_post(created_at);
```

### 3.9 Zhihu

来源接口：

- `zhihu.collection.page` -> `zhihu_content` + `zhihu_collection_item`

说明：

- 内容可能同时属于多个收藏夹，所以内容表和 membership 表分开。
- `content_json` 保存原始 `content` 字段：普通回答是 HTML 字符串，文章可能是数组；
  统一 `json.dumps` 后入库，保证 `json_valid` 成立。
- `body_html` 和 `title` 是为导出准备的派生列。
- `collection_id` 不在响应 body 里，从 `sync_response.request` 的 URL/query 解析；
  投影解析器可以读 request 元数据，但实体表不依赖 raw 层做日常查询。

```sql
CREATE TABLE zhihu_content (
    content_id TEXT PRIMARY KEY,
    type TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    body_html TEXT NOT NULL DEFAULT '',
    content_json TEXT NOT NULL CHECK (json_valid(content_json)),
    voteup_count INTEGER NOT NULL DEFAULT 0,
    comment_count INTEGER NOT NULL DEFAULT 0,
    created_time INTEGER NOT NULL DEFAULT 0,
    updated_time INTEGER NOT NULL DEFAULT 0,
    author_json TEXT CHECK (json_valid(author_json)),
    question_json TEXT CHECK (json_valid(question_json)),
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    last_seen_run_id INTEGER NOT NULL REFERENCES sync_run(id),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    raw_json TEXT NOT NULL CHECK (json_valid(raw_json))
) STRICT;

CREATE INDEX idx_zhihu_content_type
    ON zhihu_content(type);

CREATE INDEX idx_zhihu_content_updated_time
    ON zhihu_content(updated_time);

CREATE TABLE zhihu_collection_item (
    collection_id TEXT NOT NULL,
    content_id TEXT NOT NULL REFERENCES zhihu_content(content_id),
    saved_at TEXT NOT NULL DEFAULT '',
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    last_seen_run_id INTEGER NOT NULL REFERENCES sync_run(id),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (collection_id, content_id)
) STRICT;

CREATE INDEX idx_zhihu_collection_item_content
    ON zhihu_collection_item(content_id);
```

## 4. 重建

实现放在 `src/db/projections/`：

- `__init__.py`：`rebuild_platform(connection, platform)` 分发器。
- `_upsert.py`：主实体 upsert 通用函数。
- `<platform>.py`：每个平台的响应解析和字段映射。

### 4.1 重建流程

```text
rebuild_platform(conn, platform):
    BEGIN
    按子表到父表顺序删除该平台所有投影行
    按固定接口顺序遍历 sync_response
        body 为 NULL -> 记错误，整体回滚
        JSON 解析失败 -> 记错误，整体回滚
        upsert 实体/关系/辅助字段
    COMMIT
    返回处理的响应数和行数
```

固定接口顺序，不按全局 `fetched_at` 排序：

| platform | 顺序 |
| --- | --- |
| bangumi | `bangumi.collections.page` -> `bangumi.subject.detail` -> `bangumi.subject.characters` |
| bilibili | `bilibili.favlist.page` |
| cnblog | `cnblog.bookmarks.page` -> `cnblog.post.body` |
| github | `github.stars.list` -> `github.repo.readme` |
| qireader | `qireader.readlater.page` -> `qireader.article` |
| twitter | `twitter.likes.page` |
| v2ex | `v2ex.fav.page` -> `v2ex.topic.detail` |
| weibo | `weibo.likes.page` -> `weibo.longtext` |
| zhihu | `zhihu.collection.page` |

同一接口内按 `iter_responses` 的 `(fetched_at, id)` 顺序回放。

### 4.2 Upsert 规则

```sql
INSERT INTO <table> (...) VALUES (...)
ON CONFLICT(<natural key>) DO UPDATE SET
    ...,
    response_id = excluded.response_id,
    last_seen_run_id = excluded.last_seen_run_id,
    last_seen_at = excluded.last_seen_at
WHERE excluded.response_id > <table>.response_id;
```

- 插入时 `first_seen_at = last_seen_at = response.fetched_at`。
- 更新时保留 `first_seen_at`。
- `WHERE` 防止旧响应覆盖新响应；全量重建按顺序回放，不依赖增量游标。
- 辅助响应只更新自己的列：

```sql
UPDATE <table>
SET readme = ?, readme_response_id = ?
WHERE <natural key> = ?;
```

不修改 `response_id` / `last_seen_run_id` / `last_seen_at`。

### 4.3 幂等性

时间全部来自 `sync_response`，不使用 `datetime.now()`。同一份 raw 数据连续重建两次，
所有投影行逐列相等。测试必须覆盖这一点。

### 4.4 失败处理

- 任何响应 body 无法解析、字段无法满足非空约束、JSON 校验失败，整个平台重建回滚。
- 不静默跳过单条坏响应；否则会得到“看起来完整”的投影。
- 命令输出失败接口、`sync_response.id` 和原因。

## 5. 删除与多账号

### 5.1 删除

v1 不删除。`last_seen_run_id` 已经足够支持以后实现：

1. 只允许 `sync_run.status = 'success'` 的完整列表 run 驱动删除。
2. 删除条件是 `last_seen_run_id < 当前 run_id`。
3. `partial` / `failed` run 一律跳过。
4. 删除范围由 `sync_run.scope` 决定，例如 Bangumi 的
   `<subject_type>:<collection_type>`。

### 5.2 多账号

当前主键不带账号维度。以后需要多账号时，统一迁移：

- 增加 `account_id TEXT NOT NULL`。
- 主键改为 `(account_id, <natural key>)` 或给单列主键加 `account_id`。
- 所有唯一约束同步调整。

不在 v1 预留空列，避免每张表多一列无用数据。

## 6. 迁移与实现顺序

1. `002_projection_layer.sql`：一次创建 16 张表、索引，全部使用 `STRICT`。
2. 更新 `tests/test_db_schema.py` 的 `user_version` 断言到 2；增加建表、JSON 约束、
   外键约束测试。
3. pilot：Bangumi 解析器 + `rebuild_platform` + 幂等测试。
4. CLI：`eto --db data/eto.db db rebuild bangumi`，输出处理响应数和行数。
5. 其余平台一次一个：解析器 + 测试，不改表结构。
6. 全部完成后更新 `AGENTS.md` / `README.md` 的数据流说明。

分层理由：表结构先固定，解析器逐个交付，避免九个平台的解析逻辑同时半成品。

## 7. 风险与待确认

- 宽表会随上游 API 增加字段而需要迁移；`raw_json` + `json_extract` 回填是兜底路径。
- `STRICT` 和 JSON1 要求 SQLite >= 3.37；当前 3.45.1，Python 3.12 环境满足。
- GitHub `repo_id` 需要解析器直接读 raw JSON，不复用现有 dataclass 的字段集合。
- Bangumi `characters_json` 把两个响应合到一行，已用 `characters_response_id` 单独溯源。
- QiReader 正文按 URL 关联；同一 URL 对应多个 entry 时共享同一份正文，这是预期行为。
- v1 不删除，取消收藏/取消点赞的旧行会保留到删除策略实现。
- 单账号假设；换账号同步会混入同一张表，直到多账号迁移完成。
