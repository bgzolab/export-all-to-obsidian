# twitter

导出当前用户的 Twitter（X）点赞。

## 用法

```shell
eto [全局参数] twitter -o OUTPUT [--force] [--max-pages N]
```

## 参数

| 参数 | 必需 | 说明 |
| --- | --- | --- |
| `-o`, `--output` | 非 `--db-only` 时必需 | 输出目录，不存在时会自动创建 |
| `--force` | 否 | 覆盖已存在的文件并继续导出 |
| `--max-pages` | 否 | 最大分页数，必须大于等于 `1`；默认 `50`，约 1000 条点赞 |

## 凭证

通过 `COOKIES` 或 `--cookies-file` 提供 `x.com` 或 `twitter.com` 的 Cookie。

以下环境变量可选：

- `TWITTER_CSRF_TOKEN`：未设置时从 Cookie 的 `ct0` 推导。
- `TWITTER_USER_ID`：未设置时从 Cookie 的 `twid` 推导。

推导失败会视为凭证不可用，跳过导出。导出前会做一次凭证验活。

注意：验活会真实请求一次 Likes 接口，消耗一次 X 的限流配额；频繁启动导出可能更容易触发 `429`。

## 输出

每条点赞写成一个 Markdown 文件，文件名格式为 `<screen_name>-<tweet_id>.md`。文件带 front matter，包含 `title`、`source`、`created`、`modified`、`type`、`comments`、`draft` 等字段。

```text
OUTPUT/
└── <screen_name>-<tweet_id>.md
```

## 增量与截断

默认遇到已存在文件时，当前导出流程提前结束，本次同步标记为 `partial`。传入 `--force` 后会覆盖已有文件并继续导出。

以下情况也会把本次同步标记为 `partial`：

- 达到 `--max-pages` 上限。
- Likes 接口请求或解析失败。
- 分页游标未推进。

## 示例

默认导出：

```shell
eto --index-file output/index/export-index.md twitter -o output/twitter
```

限制分页数：

```shell
eto twitter --max-pages 5 -o output/twitter
```

强制重新导出：

```shell
eto twitter --force -o output/twitter
```

[返回命令索引](./README.md)
