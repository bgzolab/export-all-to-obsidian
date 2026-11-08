# v2ex

导出 V2EX 收藏主题。

## 用法

```shell
eto [全局参数] v2ex -o OUTPUT [--force]
```

## 参数

| 参数 | 必需 | 说明 |
| --- | --- | --- |
| `-o`, `--output` | 非 `--db-only` 时必需 | 输出目录，不存在时会自动创建 |
| `--force` | 否 | 覆盖已有文件；`--db-only` 下关闭增量剪枝 |

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

登录失效时 V2EX 可能返回 200 的 signin 页面；导出会直接报错而不是把它当成空收藏，
`--db-only` 的投影重建也会回滚，不会清空已有 `v2ex_favorite`。如果 signin 页已经被
记入 raw，修复登录后 rebuild 仍会失败；按 [db.md](./db.md) 的“定位坏行”步骤处置该
响应后再重建。

## 示例

```shell
eto v2ex -o output/v2ex
```

[返回命令索引](./README.md)
