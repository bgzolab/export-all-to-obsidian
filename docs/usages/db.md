# db

数据库维护命令。

## 用法

```shell
eto [全局参数] db rebuild PLATFORM
```

## 参数

| 参数 | 必需 | 说明 |
| --- | --- | --- |
| `PLATFORM` | 是 | 平台名，见下表 |

可选平台：

| 平台 | 投影表 |
| --- | --- |
| `bangumi` | `bangumi_collection`、`bangumi_subject` |
| `bilibili` | `bilibili_fav`、`bilibili_media`、`bilibili_fav_item` |
| `github` | `github_star` |
| `zhihu` | `zhihu_content`、`zhihu_collection_item` |
| `v2ex` | `v2ex_topic`、`v2ex_reply`、`v2ex_favorite`、`v2ex_thanks` |
| `weibo` | `weibo_post` |
| `qireader` | `qireader_entry`、`qireader_article` |
| `cnblog` | `cnblog_bookmark`、`cnblog_post` |
| `twitter` | `twitter_tweet`、`twitter_like`、`twitter_bookmark` |
| `netease` | `netease_playlist`、`netease_song`、`netease_playlist_song`、`netease_play_record` |

## 行为

`db rebuild` 不请求 API，只读取数据库里的 `sync_response`：

1. 在一个事务里删除该平台的全部投影行（子表先删）。
2. 按固定接口顺序回放 raw 响应并 upsert。
3. 传输错误（无 body 或 `error` 非空）和非 200 响应会被跳过并计数。
4. 辅助接口（README、角色、长文、正文、回复）的 200 非 JSON 响应或缺少业务字段时
   跳过并计数；GitHub README 允许纯文本，但 HTML 错误页和缺 `content` 的 JSON 会跳过。
5. 主实体的业务级无数据负载（V2EX `result` 缺失/null、Bilibili `code != 0`、
   Twitter errors-only、Weibo `ok != 1`）跳过并计数；JSON 非法或顶层类型错误时
   整体回滚，命令非零退出。

Twitter 先回放 `twitter.likes.page`，再回放 `twitter.bookmarks.page`；`twitter_tweet`
是共享实体，`twitter_like` / `twitter_bookmark` 分别记录来源关系。

V2EX 收藏页或余额页的 signin 表单会让整个 `v2ex` 投影回滚（不会清空已有收藏/感谢行），
处置步骤见 [v2ex.md](./v2ex.md)。

网易云先回放 `netease.playlists.page`、`netease.playlist.detail`、
`netease.songs.detail`，最后回放 `netease.play.recent`。歌单列表按 raw request 的
`meta.uid` 只保留自建歌单；详情按 `trackIds` 替换成员；排行响应不参与投影。
歌单列表的 301/401/403 会让整个平台回滚（避免登录失败清空歌单），其余 `code != 200`
按业务无数据跳过。

成功后输出处理的响应数和写入行数；有跳过的错误响应时额外输出“跳过 N 条错误响应”，
辅助列找不到唯一主行时输出“辅助未命中 N 条”。
投影表的 `response_id` 指向产生该行最新主数据的 `sync_response.id`，不是 `sync_run.id`。

如果 200 响应本身损坏导致重建回滚，可先定位出问题的 raw 行：

```shell
sqlite3 data/eto.db \
  "SELECT id, endpoint, status_code, error FROM sync_response WHERE endpoint = 'bangumi.collections.page';"
```

raw 层默认只增不改；确认该响应确实可以废弃后再手动处理，不要直接清空整个 run。

## 示例

```shell
eto --db ./data/eto.db db rebuild bangumi
eto --db ./data/eto.db db rebuild v2ex
eto --db ./data/eto.db db rebuild netease
```

[返回命令索引](./README.md)
