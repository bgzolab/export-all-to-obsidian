# cnblog

导出博客园收藏（bookmarks）。

## 用法

```shell
eto [全局参数] cnblog -o OUTPUT
```

## 参数

| 参数 | 必需 | 说明 |
| --- | --- | --- |
| `-o`, `--output` | 非 `--db-only` 时必需 | 输出目录，不存在时会自动创建 |

## 凭证

需要环境变量 `CNBLOG_ACCESS_TOKEN`。导出前会做一次凭证验活。

## 输出

每个收藏写成一个 Markdown 文件，文件名取自收藏标题（非法字符会被替换）。文件带 front matter，包含 `title`、`source`、`created`、`modified`、`type`、`comments`、`draft` 等字段。

```text
OUTPUT/
└── <title>.md
```

只抓取博客园站内文章（`FromCNBlogs` 为真）的正文；站外收藏会跳过正文，但仍会写入索引。

## 增量

目标文件已存在时，当前导出流程提前结束，本次同步标记为 `partial`。该命令不支持 `--force`。

## 示例

```shell
eto --prefix "" cnblog -o output/cnblog
```

[返回命令索引](./README.md)
