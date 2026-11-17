# twitter

导出当前用户的 Twitter（X）点赞，或把 X 书签写入数据库。

## 用法

```shell
# 导出点赞 Markdown
eto [全局参数] twitter -o OUTPUT [--force] [--max-pages N]

# 书签入库（不写 Markdown）
eto [全局参数] --db-only twitter --bookmarks [--full] [--force] [--max-pages N]
```

## 参数

| 参数 | 必需 | 说明 |
| --- | --- | --- |
| `-o`, `--output` | 点赞导出时必需 | 输出目录，不存在时会自动创建 |
| `--bookmarks` | 否 | 把 X 书签写入数据库；必须与 `--db-only` 一起使用，本阶段不导出书签 Markdown |
| `--full` | 否 | 全量抓取书签，并从上次全量断点续抓；仅能与 `--bookmarks` 一起使用 |
| `--force` | 否 | 点赞模式覆盖已存在文件；书签模式隐含 `--full` 并忽略断点，从顶部重新抓取 |
| `--max-pages` | 否 | 最大分页数，必须大于等于 `1`；默认 `50`。点赞约 20 条/页，书签约 100 条/页 |

## 凭证

通过 `COOKIES` 或 `--cookies-file` 提供 `x.com` 或 `twitter.com` 的 Cookie。

以下环境变量可选：

- `TWITTER_CSRF_TOKEN`：未设置时从 Cookie 的 `ct0` 推导。
- `TWITTER_USER_ID`：未设置时从 Cookie 的 `twid` 推导。

推导失败会视为凭证不可用，跳过导出。

点赞导出前会验活 Likes 接口；书签入库前会单独验活 Bookmarks 接口。两次验活都会真实请求 X 并消耗限流配额，书签模式不会复用点赞验活结果。频繁启动可能更容易触发 `429`。

## 点赞输出

每条点赞写成一个 Markdown 文件，文件名格式为 `<screen_name>-<tweet_id>.md`。文件带 front matter，包含 `title`、`source`、`created`、`modified`、`type`、`comments`、`draft` 等字段。

```text
OUTPUT/
└── <screen_name>-<tweet_id>.md
```

## 书签入库

书签只写入数据库的 raw 层和投影表，不写 Markdown、不写索引，因此必须使用 `--db-only`。同一条 Tweet 同时被点赞和书签时，`twitter_tweet` 只有一行，来源分别记录在 `twitter_like` / `twitter_bookmark`。

三种模式：

| 模式 | 命令 | 行为 |
| --- | --- | --- |
| 增量（默认） | `eto --db-only twitter --bookmarks` | 从顶部开始；整页都已在 `twitter_bookmark` 时停止，本次 run 标记 `partial` |
| 全量 | `eto --db-only twitter --bookmarks --full` | 从顶部开始；若上次全量中断，则从其断点游标继续；不因整页已知停止 |
| 强制重来 | `eto --db-only twitter --bookmarks --force` | 隐含 `--full`；忽略断点，从顶部开始新一轮全量抓取 |

补充行为：

- 增量模式发现存在未完成的全量轮次时只打印提示，不自动续抓；继续全量请加 `--full`。
- 全量轮次达到 `--max-pages`、触发限流或请求失败时标记 `partial`，下一次 `--full` 从断点继续。
- 全量断点只读取 `sync_run.scope='full'` 的响应；增量响应不会污染断点。
- 游标不推进、连续 3 页为空、游标可能失效等异常都会停止并标记 `partial`。
- `401` / `403` 表示 Cookie 失效；`400` / `404` 表示 queryId 可能已轮换。
- 本阶段不做删除检测；取消书签后的旧关系行会保留。

## 限流与 queryId

- 响应头 `x-rate-limit-remaining` 降到 `0` 或遇到 HTTP `429` 时，本次抓取停止并打印 `x-rate-limit-reset` 时间戳；不会在单次运行内 sleep 等待。
- 全量模式稍后再次执行 `--full` 即可从断点继续；增量模式下次仍从顶部开始。
- 若请求返回 `400` / `404`，按提示从 `x.com/i/bookmarks` 的网络请求中获取新的 `Bookmarks` queryId，并更新 `src/twitter/api_endpoints.py` 的 `TWITTER_BOOKMARKS_PATH`。
- 断点游标可能过期；全量模式遇到 `400` 时可用 `--force` 从顶部重来。

## 点赞增量与截断

默认遇到已存在文件时，当前导出流程提前结束，本次同步标记为 `partial`。传入 `--force` 后会覆盖已有文件并继续导出。

以下情况也会把本次同步标记为 `partial`：

- 达到 `--max-pages` 上限。
- Likes 接口请求或解析失败。
- 分页游标未推进。

`--db-only` 不会因为目标文件存在而停止，但 `--max-pages`（未传时为默认 50 页）仍然生效；需要抓更多页时请显式传更大的值。

## 示例

默认导出点赞：

```shell
eto --index-file output/index/export-index.md twitter -o output/twitter
```

限制点赞分页数：

```shell
eto twitter --max-pages 5 -o output/twitter
```

强制重新导出点赞：

```shell
eto twitter --force -o output/twitter
```

书签增量入库：

```shell
eto --db-only twitter --bookmarks
```

书签首次全量或断点续抓：

```shell
eto --db-only twitter --bookmarks --full
```

书签强制从头重来：

```shell
eto --db-only twitter --bookmarks --force --max-pages 10
```

[返回命令索引](./README.md)
