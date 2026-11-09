# zhihu

导出知乎收藏夹。

## 用法

```shell
eto [全局参数] zhihu -c COLLECTION -o OUTPUT [--force]
```

## 参数

| 参数 | 必需 | 说明 |
| --- | --- | --- |
| `-c`, `--collection` | 是 | 知乎收藏夹 ID |
| `-o`, `--output` | 非 `--db-only` 时必需 | 输出目录，不存在时会自动创建 |
| `--force` | 否 | 覆盖已有文件；`--db-only` 下关闭增量剪枝 |

## 凭证

通过 `COOKIES` 或 `--cookies-file` 提供 `zhihu.com` 的 Cookie。导出前会做一次凭证验活。

## 输出

每个收藏条目写成一个 Markdown 文件，文件名格式为 `<content_id>-<title>.md`。文件带 front matter，包含 `title`、`source`、`created`、`modified`、`type`、`comments`、`draft` 等字段。

```text
OUTPUT/
└── <content_id>-<title>.md
```

## 增量

目标文件已存在时，当前导出流程提前结束，本次同步标记为 `partial`。该命令不支持 `--force`。

## 示例

```shell
eto --index-file output/index/export-index.md zhihu -c your-collection-id -o output/zhihu
```

[返回命令索引](./README.md)
