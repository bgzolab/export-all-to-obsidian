# Projection Layer Design

- Issue: [#16](https://github.com/bgzolab/export-all-to-obsidian/issues/16)
- Status: Implemented
- Date: 2026-11-07
- Implemented: 2026-11-08
- Related: [raw-response-layer.md](raw-response-layer.md), [#18](https://github.com/bgzolab/export-all-to-obsidian/issues/18)

## 1. 目标

从 raw 层解析出平台实体，落成可查询、可导出、可幂等重建的投影表。投影层是 Markdown
导出的主要数据源；raw 层只负责保存、灾难恢复和全量重放。

本层不做统一模型，不为一个平台建立超过三张表，不引入 ORM。

非目标：

- 不做跨平台统一 `item` 表。
- 不做删除检测；v1 只记录 `response_id`，删除策略以后再加。
- 不做多账号；当前所有表都假设每个平台只有一个认证账号。
- 不把分页、状态码、`code` / `message` / `has_more` / `ttl` 等响应信封存进实体表。
- 不承诺上游字段 100% 落列；未落列字段留在 raw 层，需要时再迁移。

## 2. 核心约定

1. 一张表对应一个实体，不是一次响应。每平台 1-3 张表。
2. 表名使用 `<platform>_<entity>`，例如 `bangumi_collection`、`zhihu_collection_item`。
3. 业务自然键做主键；关系表用复合主键；不使用自增 id 做业务主键。
4. 顶层标量字段落列；对象/数组字段落 `*_json` 列，并用
   `CHECK (json_valid(...))` 约束。
5. 溯源列固定为 `response_id`，指向产生该行最新主数据的 `sync_response.id`，
   不是 `sync_run.id`。一次 run 可以包含很多次 HTTP 请求。
6. 正常查询和导出不 join `sync_run` / `sync_response`；raw 层只用于全量重建、补列和删除扫描。
7. 数据库时间与平台时间分开：
   - 数据库时间：`db_created_at`、`db_updated_at`，每张投影表都有，只表示行在数据库里的
     插入/更新时间。
   - 平台时间：按平台字段原名、原类型全部保留，不造统一 `fav_at`，不在这里决定导出用哪个。
8. 新表使用 SQLite `STRICT`，要求 SQLite >= 3.37；当前运行环境 3.45.1。
9. 单账号假设。以后要多账号时，增加账号列并调整主键，不在 v1 提前设计。

### 2.1 列选择规则

列按下述优先级选取，其余字段留在 raw 层：

1. 当前平台 dataclass/entity 的全部字段。
2. 自然键、平台提供的全部时间字段、状态、计数。
3. 现有或计划中的导出模板会读取的字段。
4. 明显会用于过滤或排序的字段。

以后需要新列时，改对应平台的投影解析器，加 `ALTER TABLE ADD COLUMN`，再
`rebuild_platform` 从 raw 响应全量回填：

```sql
ALTER TABLE github_star ADD COLUMN watchers_count INTEGER NOT NULL DEFAULT 0;
-- 解析器补字段后执行 rebuild_platform('github')
```

这是“尽量全但不强求全”的边界。GitHub 这类上游对象字段过多，不逐个铺列。

### 2.2 通用列

每张投影表统一追加：

```sql
response_id INTEGER NOT NULL REFERENCES sync_response(id),
db_created_at TEXT NOT NULL,
db_updated_at TEXT NOT NULL
```

语义：

- `response_id`：最近一次主响应的 `sync_response.id`。不是 `sync_run.id`；一次 run 可以包含
  很多次 HTTP 请求，这里记录的是具体哪一条响应产生了这行数据。
- `db_created_at`：这行第一次写入投影表的时间，插入后再不修改。
- `db_updated_at`：这行最后一次被 upsert 更新的时间。

实体字段不在投影表里再存一份完整 JSON。需要未落列字段时：

1. 用 `response_id` 取出 `sync_response.body`，解压并解析。
2. 按自然键在该响应的实体列表/对象里定位这一行。
3. 新增列走“改解析器 + `ALTER TABLE` + `rebuild_platform`”，不靠行内 JSON 回填。

`response_id` 是响应级，不是实体级：一次列表响应可能包含多个实体。定位逻辑由各平台
投影解析器负责，全量重建时它本来就要遍历这些实体。

### 2.3 数据库时间与平台时间

**数据库时间**：

```sql
db_created_at TEXT NOT NULL,
db_updated_at TEXT NOT NULL
```

- 统一 UTC ISO 8601，例如 `2026-11-07T08:30:00+00:00`。
- 写入时取当前时间，只描述数据库操作，不表示平台上的创建/更新/收藏时间。
- 全量重建会重写这两列；幂等测试比较业务列时排除它们。
- `db_created_at` 只在插入时写；`db_updated_at` 每次 upsert 更新。

**平台时间**：

- 按平台字段原名保留，平台给 epoch 就存 `INTEGER`，给字符串就存 `TEXT`。
- 不做时区/格式归一化；导出层以后再决定用哪个时间、怎么格式化。
- 删除统一 `fav_at`。收藏/保存时间用平台自己的字段，例如 `starred_at`、`fav_time`、
  `date_added`、`created`。

平台时间字段清单：

| 表 | 平台时间字段 |
| --- | --- |
| `bangumi_collection` | `updated_at` |
| `bangumi_subject` | `date` |
| `bilibili_fav` | `ctime`, `mtime` |
| `bilibili_media` | `ctime`, `pubtime` |
| `bilibili_fav_item` | `fav_time` |
| `cnblog_bookmark` | `date_added` |
| `cnblog_post` | 无 |
| `github_star` | `created_at`, `updated_at`, `pushed_at`, `starred_at` |
| `qireader_entry` | `published_at`, `crawled_at`, `timestamp` |
| `qireader_article` | 无 |
| `twitter_tweet` | `created_at` |
| `v2ex_topic` | `created`, `last_modified`, `last_touched` |
| `v2ex_reply` | `created`, `last_modified`（接口提供时） |
| `v2ex_favorite` | 无 |
| `weibo_post` | `created_at` |
| `zhihu_content` | `created_time`, `updated_time` |
| `zhihu_collection_item` | `created` |

### 2.4 主响应与辅助响应

一个实体可能由多个接口共同补全：

- 主响应：列表或详情响应，决定 `response_id`。
- 辅助响应：README、长文、正文、角色列表等，只更新自己的列和 `*_response_id`，
  同时刷新 `db_updated_at`，不覆盖主响应的 `response_id`。

## 3. 平台表

迁移 `002_projection_layer.sql` 一次建好下列 17 张表和索引；解析器已覆盖全部九个平台。

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
- 平台时间：收藏记录的 `updated_at`、条目的 `date` 原样保留。

#### 为什么 collection 和 subject 分开

当前单账号、只导出收藏时，两张表是 1:1；但这是导出流程带来的，不是实体同一性。
collection 是“我-条目”的关系，subject 是条目本身。分开存的原因：

1. **详情抓取失败时，收藏事实仍然保留。** `bangumi_collection.subject_json` 已经包含
   slim subject，足够基本导出；`bangumi_subject` 抓不到只是少字段，不会丢掉“我收藏了它”。
   合并成一张表就必须让一半字段可空，或者整行不写。
2. **改收藏状态只 upsert collection。** 把“在看”改成“看过”时，列表响应只带收藏字段；
   合并表如果直接 upsert，容易把 subject 字段覆盖成默认值。
3. **上游改条目信息只 upsert subject。** 标题、简介的变化和我的评分、评论是两条独立更新线。
4. **取消收藏只删 collection。** subject 元数据可以保留；合并后要么删整行丢 subject，
   要么留一行半空数据。
5. **1:1 是有条件的。** 以后多账号、或者单独查某个条目时，subject 不需要有对应的
   collection。分开后两个方向都可以独立存在。

代价是一个 `ON subject_id` 的 join，SQLite 上很便宜。合并省一张表，但要多两个溯源列
（collection / subject 各一个），并让所有 subject 字段可空；取消收藏后还要在
“删整行”和“留半空行”之间选，边界更多，不划算。

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
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
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
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
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
- 平台时间：收藏夹 `ctime` / `mtime`，视频 `ctime` / `pubtime`，关系 `fav_time`，
  全部按原类型保留。
- `code` / `message` / `ttl` / `has_more` 不落表。

#### 为什么是 3 张表

- `bilibili_fav`：收藏夹本身，来自 `data.info`。
- `bilibili_media`：视频本身，来自 `data.medias[]`。
- `bilibili_fav_item`：收藏夹与视频的多对多关系，以及关系属性 `fav_time`。

原因：

1. **收藏夹和视频是多对多。** 一个收藏夹有多个视频，同一个视频可以出现在多个收藏夹。
   只建“收藏夹 + 视频”两张表就没有地方放 membership；把视频数组塞进收藏夹 JSON，
   查询“这个视频在哪些收藏夹”很别扭，还会在多个收藏夹里重复存视频元数据。
2. **`fav_time` 是关系属性。** 同一视频在不同收藏夹的收藏时间不同。放视频表只能保留
   一个时间，放收藏夹 JSON 又难查询和更新。
3. **收藏夹元数据独立于视频。** 空收藏夹也要能记录；标题、封面、计数变化不应该重写
   视频行。
4. **视频元数据独立于收藏夹。** 取消某个收藏夹的收藏，不应该丢掉视频本身。
5. 三张表仍在“每平台 1-3 张表”的预算内，代价只是导出时多一个 `ON (fav_id, media_id)`
   的 join。

如果只导出单个收藏夹，确实可以退化成一张宽表；但数据库要表达真实关系，三张表更稳。

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
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
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
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
) STRICT;

CREATE INDEX idx_bilibili_media_bvid
    ON bilibili_media(bvid);

CREATE TABLE bilibili_fav_item (
    fav_id INTEGER NOT NULL REFERENCES bilibili_fav(fav_id),
    media_id INTEGER NOT NULL REFERENCES bilibili_media(media_id),
    fav_time INTEGER NOT NULL DEFAULT 0,
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL,
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
- 平台时间 `DateAdded` 原样保留为 `date_added`。
- `cnblog_post` 主键是从正文请求 URL 中解析出的 post id；`body` 是 HTML 原始载荷。

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
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
) STRICT;

CREATE INDEX idx_cnblog_bookmark_link_url
    ON cnblog_bookmark(link_url);

CREATE TABLE cnblog_post (
    post_id INTEGER PRIMARY KEY,
    source_url TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL,
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
) STRICT;
```

### 3.4 GitHub

来源接口：

- `github.stars.list` -> `github_star`
- `github.repo.readme` -> 辅助更新 `github_star.readme`

说明：

- 主键 `repo_id` 取 API 的 `repo.id`。当前 dataclass 没有这个字段，投影解析器直接读
  raw JSON 补上；仓库改名时仍能按 id 更新同一行。
- `full_name` 唯一，用于展示和文件名。
- 平台时间 `created_at`、`updated_at`、`pushed_at`、`starred_at` 全部保留。
- README 是辅助响应，只更新 `readme` 和 `readme_response_id`，并刷新 `db_updated_at`。

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
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
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
- 平台时间 `published_at`（毫秒）、`crawled_at`（毫秒）、`timestamp`（纳秒字符串）
  全部按原类型保留。
- `content` 是正文原始载荷。

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
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
) STRICT;

CREATE INDEX idx_qireader_entry_url
    ON qireader_entry(url);

CREATE INDEX idx_qireader_entry_timestamp
    ON qireader_entry(timestamp);

CREATE TABLE qireader_article (
    url TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
) STRICT;
```

### 3.6 Twitter

来源接口：

- `twitter.likes.page` -> `twitter_tweet`

说明：

- 主键 `tweet_id` 对应 `Tweet.id_str`。
- `author_json` 存归一化后的作者对象（`screen_name` / `name` / `id`）；完整 GraphQL
  节点留在 raw 响应。
- 平台时间只有 `created_at`，原样保留。
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
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
) STRICT;

CREATE INDEX idx_twitter_tweet_created_at
    ON twitter_tweet(created_at);
```

### 3.7 V2EX

来源接口：

- `v2ex.fav.page` -> `v2ex_favorite`
- `v2ex.topic.detail` -> `v2ex_topic`
- `v2ex.topic.replies.page` -> `v2ex_reply`

说明：

- 收藏列表是 HTML，没有对应实体 JSON；`v2ex_favorite` 只保存 membership 和 `response_id`。
- 不建 `v2ex_favorite.topic_id -> v2ex_topic.topic_id` 外键：收藏列表先到，主题详情可能
  抓取失败，外键会让合法收藏无法入库。
- 平台时间 `created`、`last_modified`、`last_touched` 全部保留。
- `member_json` / `node_json` / `supplements_json` 保存嵌套结构。
- 回复用独立的分页接口 `GET /api/v2/topics/{topic_id}/replies?p=N`（每页 20 条），
  全部页都抓，全部入库；后续按 `v2ex_reply.thanks` 排序取“热门回复”。
- V2 回复文档未明确列出 `thanks`。解析器有就写入，没有就保留默认 0；如果实测确认没有，
  又必须严格按感谢数排序，则改用 V1 `/api/replies/show.json?topic_id=` 或在后续补字段。

#### 为什么回复单独一张表

1. 一条主题对多条回复，回复有自己的 id、作者、正文、创建时间和感谢数。
2. 把回复塞进主题行的 JSON 数组，无法按 `thanks` 排序/筛选，也无法单独 upsert 某条回复。
3. 回复走独立分页接口，有独立 `response_id` 和失败边界；主题详情失败不影响已抓到的回复入库。
4. 先全量入库，再按 `thanks` 取热门；只存热门会丢数据，无法重算。

V2EX 因此是 3 张表，仍在“每平台 1-3 张表”的预算内。

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
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
) STRICT;

CREATE INDEX idx_v2ex_topic_last_touched
    ON v2ex_topic(last_touched);

CREATE TABLE v2ex_reply (
    reply_id INTEGER PRIMARY KEY,
    topic_id INTEGER NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    content_rendered TEXT NOT NULL DEFAULT '',
    thanks INTEGER NOT NULL DEFAULT 0,
    created INTEGER NOT NULL DEFAULT 0,
    last_modified INTEGER NOT NULL DEFAULT 0,
    member_json TEXT CHECK (json_valid(member_json)),
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
) STRICT;

CREATE INDEX idx_v2ex_reply_topic_thanks
    ON v2ex_reply(topic_id, thanks DESC);

CREATE INDEX idx_v2ex_reply_created
    ON v2ex_reply(created);

CREATE TABLE v2ex_favorite (
    topic_id INTEGER PRIMARY KEY,
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
) STRICT;
```

### 3.8 Weibo

来源接口：

- `weibo.likes.page` -> `weibo_post`
- `weibo.longtext` -> 辅助更新 `weibo_post.long_text`

说明：

- 主键 `post_id` 用 `idstr`，避免大整数在跨语言工具里失真；`numeric_id` 保留原 `id`。
- `mblogid` 用于构造微博 URL，唯一但允许为空。
- 平台时间 `created_at` 原样保留。
- `user_json`、`pic_ids_json`、`pic_infos_json` 保存嵌套结构。
- 长文是辅助响应，只更新 `long_text` 和 `long_text_response_id`，并刷新 `db_updated_at`。

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
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
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
- 平台时间 `created_time`、`updated_time` 保留；membership 的 `created`（加入收藏时间）
  也保留。
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
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
) STRICT;

CREATE INDEX idx_zhihu_content_type
    ON zhihu_content(type);

CREATE INDEX idx_zhihu_content_updated_time
    ON zhihu_content(updated_time);

CREATE TABLE zhihu_collection_item (
    collection_id TEXT NOT NULL,
    content_id TEXT NOT NULL REFERENCES zhihu_content(content_id),
    created TEXT NOT NULL DEFAULT '',
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL,
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
        传输错误（body 为 NULL 或 error 非空）或非 200 -> 跳过并计数
        200 响应 JSON 解析失败 -> 记错误，整体回滚
        upsert 实体/关系/辅助字段
    COMMIT
    返回处理的响应数、写入行数和跳过的错误响应数
```

传输错误和非 200 响应不进入投影，但 raw 层保留它们；跳过数量会随重建结果输出，
禁止静默吞掉。200 响应本身不合法时仍视为数据损坏并整体回滚。

固定接口顺序，不按全局 `fetched_at` 排序：

| platform | 顺序 |
| --- | --- |
| bangumi | `bangumi.collections.page` -> `bangumi.subject.detail` -> `bangumi.subject.characters` |
| bilibili | `bilibili.favlist.page` |
| cnblog | `cnblog.bookmarks.page` -> `cnblog.post.body` |
| github | `github.stars.list` -> `github.repo.readme` |
| qireader | `qireader.readlater.page` -> `qireader.article` |
| twitter | `twitter.likes.page` |
| v2ex | `v2ex.fav.page` -> `v2ex.topic.detail` -> `v2ex.topic.replies.page` |
| weibo | `weibo.likes.page` -> `weibo.longtext` |
| zhihu | `zhihu.collection.page` |

同一接口内按 `iter_responses` 的 `(fetched_at, id)` 顺序回放。

### 4.2 Upsert 规则

```sql
INSERT INTO <table> (..., response_id, db_created_at, db_updated_at)
VALUES (..., :response_id, :now, :now)
ON CONFLICT(<natural key>) DO UPDATE SET
    ...,
    response_id = excluded.response_id,
    db_updated_at = excluded.db_updated_at
WHERE excluded.response_id > <table>.response_id;
```

- `response_id` 始终指向最新主响应。
- `db_created_at` 只在插入时写；冲突更新时不动。
- `db_updated_at` 每次 upsert 更新。
- `WHERE` 防止旧响应覆盖新响应；全量重建按顺序回放，不依赖增量游标。
- 辅助响应只更新自己的列：

```sql
UPDATE <table>
SET readme = ?, readme_response_id = ?, db_updated_at = ?
WHERE <natural key> = ?;
```

不修改主响应的 `response_id` 和 `db_created_at`。

### 4.3 幂等性

业务列只来自 raw 响应，不使用 `datetime.now()`。同一份 raw 数据连续重建两次，
除 `db_created_at` / `db_updated_at` 外，所有投影行逐列相等。测试必须覆盖这一点。

### 4.4 失败处理

- 传输错误（`body IS NULL` 或 `error` 非空）和非 200 响应跳过并计数，不阻塞重建；
  它们表示“这次抓取失败”，不是投影数据损坏。
- 200 响应 body 无法解析、字段无法满足非空约束、JSON 校验失败，整个平台重建回滚。
- 列表页的 `data` / `entries` 值为 `null` 时按空页处理；键缺失仍视为响应结构错误并回滚。
  这是有意区分：`null` 是合法的空页，缺键通常意味着上游返回了非预期负载。
- 不静默跳过单条坏响应：跳过的错误响应数量必须出现在命令输出里。
- 命令输出失败接口、`sync_response.id` 和原因。

## 5. CLI 运行模式

### 5.1 `--db-only`（第二层）

顶层 flag，和 `--db` / `--cookies-file` 一样放在子命令前：

```shell
eto --db-only bangumi -s 2 -c 3
eto --db-only github
eto --db-only v2ex
```

行为：

- 照常请求 API，照常写 `sync_run` / `sync_response`。
- 跳过 Markdown 输出：不要求 `-o`，不要求 `-t`，不写文件，不写索引，不创建输出目录。
- 跳过 `stop_if_output_exists` 的“文件已存在就提前结束”；db-only 必须抓完整列表。
- 抓取结束后调用 `rebuild_platform`，把该平台 raw 投影到第二层。
- 平台还没有投影解析器时：raw 照常入库，打印“projection not implemented”，退出 0。
- 投影失败：标记当前 run 为 `partial`，命令返回非零；raw 已保存，可重新执行
  `eto db rebuild <platform>`。
- `--force`、`--prefix` 在 db-only 下无意义，忽略；`--index-file` 与 `--db-only`
  同时出现直接报错。
- `--max-pages` 等抓取范围参数仍然有效。

CLI 契约：

- `-o` / `-t` 改为可选；非 db-only 时仍必须提供，缺失时报 `UsageError`。
- `--db-only` 放在子命令前，和现有全局选项一致。
- `import-markdown` 本来就是只入库，忽略该 flag。

实现约束：

- 输出抑制集中在 `export_runtime.exporter_support`：`stop_if_output_exists` 返回 False，
  `write_markdown_output` / `write_raw_markdown_output` / `add_index_entry` 直接返回。
- `IndexWriter` 增加 `enabled` 开关，`flush` 在 db-only 下不写文件、不打印空索引。
- 不要在 9 个 exporter 里复制 `if db_only` 分支。
- 两个例外必须单独处理：
  - `bangumi/exporter.py` 的 `write_subject_markdown` 自己写文件、自己检查文件是否存在、
    自己读模板；db-only 下要跳过模板读取、文件存在检查和最终写入。
  - `github/exporter.py` 启动时读模板；db-only 下不能要求模板存在，`-t` 可以为空。
- 其余平台通过共享输出函数拦截即可。
- 投影在 `sync_run` 内、抓取完成后执行；失败调用 `mark_run_partial()`，命令非零退出。

### 5.2 `--output-only`（第三层预留）

第三层引入：

- 不请求 API，不写 `sync_run` / `sync_response`。
- 只读投影表，渲染 Markdown。
- 与 `--db-only` 互斥；两者都不传时保持当前“抓取 + 导出”行为。

本层只实现 `--db-only`，`--output-only` 只保留语义，不写代码。

## 6. 删除与多账号

### 6.1 删除

v1 不删除。以后实现时不需要新增列，用 `response_id` 回查即可：

1. 只允许 `sync_run.status = 'success'` 的完整列表 run 驱动删除。
2. 行是否在本次 run 看到过，由 `response_id -> sync_response.run_id` 判断。
3. 删除条件是
   `response_id IN (SELECT id FROM sync_response WHERE run_id < :current_run_id)`。
4. `partial` / `failed` run 一律跳过。
5. 删除范围由 `sync_run.scope` 决定，例如 Bangumi 的
   `<subject_type>:<collection_type>`。

### 6.2 多账号

当前主键不带账号维度。以后需要多账号时，统一迁移：

- 增加 `account_id TEXT NOT NULL`。
- 主键改为 `(account_id, <natural key>)` 或给单列主键加 `account_id`。
- 所有唯一约束同步调整。

不在 v1 预留空列，避免每张表多一列无用数据。

## 7. 迁移与实现顺序

1. `002_projection_layer.sql`：一次创建 17 张表、索引，全部使用 `STRICT`。
2. 更新 `tests/test_db_schema.py` 的 `user_version` 断言到 2；增加建表、JSON 约束、
   外键约束测试。
3. pilot：Bangumi 解析器 + `rebuild_platform` + 幂等测试。
4. CLI：`eto --db data/eto.db db rebuild bangumi`，输出处理响应数和行数。
5. 其余平台一次一个：解析器 + 测试，不改表结构。
6. 全部完成后更新 `AGENTS.md` / `README.md` 的数据流说明。

分层理由：表结构先固定，解析器逐个交付，避免九个平台的解析逻辑同时半成品。

## 8. 风险与待确认

- 宽表会随上游 API 增加字段而需要迁移；改解析器 + 全量重建是回填路径。
- `STRICT` 和 JSON1 要求 SQLite >= 3.37；当前 3.45.1，Python 3.12 环境满足。
- GitHub `repo_id` 需要解析器直接读 raw JSON，不复用现有 dataclass 的字段集合。
- Bangumi `characters_json` 把两个响应合到一行，已用 `characters_response_id` 单独溯源。
- QiReader 正文按 URL 关联；同一 URL 对应多个 entry 时共享同一份正文，这是预期行为。
- 平台时间保持原类型（epoch 是 INTEGER，字符串是 TEXT），导出层需要按平台处理格式。
- 全量重建会改写 `db_created_at` / `db_updated_at`，幂等测试必须排除这两列。
- 传输错误与非 200 响应会被跳过并计数，因此一次重建的实体数可能少于“理想抓取”；
  raw 层仍保留失败记录，重跑成功后可再次重建补齐。
- v1 不删除，取消收藏/取消点赞的旧行会保留到删除策略实现。
- 单账号假设；换账号同步会混入同一张表，直到多账号迁移完成。
