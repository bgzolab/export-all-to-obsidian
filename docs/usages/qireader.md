# qireader

导出 QiReader 的稍后读列表。

## 用法

```shell
eto [全局参数] qireader -t TAG -o OUTPUT
```

## 参数

| 参数 | 必需 | 说明 |
| --- | --- | --- |
| `-t`, `--tag` | 是 | 稍后读收藏夹 ID，形如 `tag-xxxxxxxx` |
| `-o`, `--output` | 非 `--db-only` 时必需 | 输出目录，不存在时会自动创建 |

## 凭证

通过 `COOKIES` 或 `--cookies-file` 提供 QiReader Cookie，支持 `www.qireader.com` 或 `qireader.com` 域名。导出前会做一次凭证验活。

## 输出

每个条目写成一个 Markdown 文件，文件名取自条目标题。文件带 front matter，包含 `title`、`source`、`created`、`modified`、`type`、`comments`、`draft` 等字段。

```text
OUTPUT/
└── <title>.md
```

正文会从原链接抓取并转换为 Markdown。源页面不可访问时会打印提示，条目仍会写入。

## 增量

目标文件已存在时，当前导出流程提前结束，本次同步标记为 `partial`。该命令不支持 `--force`。

## 示例

```shell
eto qireader -t tag-xxxxxxxx -o output/qireader
```

[返回命令索引](./README.md)
