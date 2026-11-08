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
| `v2ex` | `v2ex_topic`、`v2ex_reply`、`v2ex_favorite` |
| `weibo` | `weibo_post` |
| `qireader` | `qireader_entry`、`qireader_article` |
| `cnblog` | `cnblog_bookmark`、`cnblog_post` |
| `twitter` | `twitter_tweet` |

## 行为

`db rebuild` 不请求 API，只读取数据库里的 `sync_response`：

1. 在一个事务里删除该平台的全部投影行（子表先删）。
2. 按固定接口顺序回放 raw 响应并 upsert。
3. 传输错误（无 body 或 `error` 非空）和非 200 响应会被跳过并计数。
4. 辅助接口（README、角色、长文、正文、回复）的 200 非 JSON 响应或缺少业务字段时
   跳过并计数。
5. 主实体接口的 200 响应 JSON 非法或字段不满足约束时整体回滚，命令非零退出。

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
```

[返回命令索引](./README.md)
