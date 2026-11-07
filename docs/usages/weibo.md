# weibo

导出指定用户的微博点赞。

## 用法

```shell
eto [全局参数] weibo -u UID -o OUTPUT [--force]
```

## 参数

| 参数 | 必需 | 说明 |
| --- | --- | --- |
| `-u`, `--uid` | 是 | 微博用户 ID |
| `-o`, `--output` | 是 | 输出目录，不存在时会自动创建 |
| `--force` | 否 | 覆盖已存在的文件并继续导出 |

## 凭证

通过 `COOKIES` 或 `--cookies-file` 提供微博 Cookie。`weibo.com` 优先，`weibo.cn` 作为旧域回退。导出前会做一次凭证验活。

## 输出

每条点赞写成一个 Markdown 文件，文件名格式为 `<user_id>-<post_id>.md`。文件带 front matter，包含 `title`、`source`、`created`、`modified`、`type`、`comments`、`draft` 等字段。

```text
OUTPUT/
└── <user_id>-<post_id>.md
```

长微博会额外请求全文；图片会以 Markdown 图片语法追加到正文。

## 增量

默认遇到已存在文件时，当前导出流程提前结束，本次同步标记为 `partial`。传入 `--force` 后会覆盖已有文件并继续导出。

## 示例

```shell
eto --index-file output/index/export-index.md \
  weibo -u your-user-id -o output/weibo
```

强制重新导出：

```shell
eto weibo -u your-user-id -o output/weibo --force
```

[返回命令索引](./README.md)
