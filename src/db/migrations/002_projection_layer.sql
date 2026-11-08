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
