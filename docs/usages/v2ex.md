# v2ex

导出 V2EX 收藏主题。

## 用法

```shell
eto [全局参数] v2ex -o OUTPUT
```

## 参数

| 参数 | 必需 | 说明 |
| --- | --- | --- |
| `-o`, `--output` | 是 | 输出目录，不存在时会自动创建 |

## 凭证

需要同时提供：

- 环境变量 `V2EX_ACCESS_TOKEN`
- `v2ex.com` 的 Cookie（通过 `COOKIES` 或 `--cookies-file`）

导出前会做一次凭证验活。

## 输出

每个主题写成一个 Markdown 文件，文件名格式为 `<topic_id>-<title>.md`。文件带 front matter，包含 `title`、`source`、`created`、`modified`、`type`、`comments`、`draft` 等字段。

```text
OUTPUT/
└── <topic_id>-<title>.md
```

## 增量

目标文件已存在时，当前导出流程提前结束，本次同步标记为 `partial`。该命令不支持 `--force`。

## 示例

```shell
eto v2ex -o output/v2ex
```

[返回命令索引](./README.md)
