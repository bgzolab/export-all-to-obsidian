# v2ex

导出 V2EX 收藏主题；或把余额流水中的投币（感谢）主题只写入数据库。

## 用法

```shell
eto [全局参数] v2ex -o OUTPUT [--force]
eto [全局参数] --db-only v2ex [--tipped] [--force]
```

## 参数

| 参数 | 必需 | 说明 |
| --- | --- | --- |
| `-o`, `--output` | 非 `--db-only` 时必需 | 输出目录，不存在时会自动创建 |
| `--force` | 否 | 覆盖已有文件；`--db-only` 下关闭增量剪枝并重抓完整范围 |
| `--tipped` | 否 | 从 `/balance` 发现投币主题并只写入数据库，必须与 `--db-only` 一起使用 |

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

`--tipped` 不写 Markdown、不写索引，也不需要 `-o`。它把余额流水中的
`发送谢意` 记录写入 `v2ex_thanks`，并把对应的回复感谢和主题感谢统一到
`v2ex_topic` / `v2ex_reply` 实体表。

## 增量

目标文件已存在时，当前导出流程提前结束，本次同步标记为 `partial`。`--force`
会覆盖已有文件；在 `--db-only` 下它关闭文件级和投影级剪枝。

登录失效时 V2EX 可能返回 200 的 signin 页面；导出会直接报错而不是把它当成空收藏，
`--db-only` 的投影重建也会回滚，不会清空已有 `v2ex_favorite` / `v2ex_thanks`。
如果 signin 页已经被记入 raw，修复登录后 rebuild 仍会失败；按
[db.md](./db.md) 的“定位坏行”步骤处置该响应后再重建。

`--db-only` 下每个主题最多抓前 200 条回复（约 10 页），超过部分不再抓取；回复数的
预期值按 `min(topic.replies, 200)` 计算。

### 投币主题（--tipped）

- 数据源是登录后的 `/balance` 账户流水，每次投币记为 `发送谢意`；同时收集
  “感谢 ... 的回复”和“感谢 ... 的主题”，用 `content_kind` 区分。
- 默认增量：余额页整页感谢记录都已入库时停止翻页，本次 run 标记为 `partial`。
  停止翻页后仍会扫描所有已入库的投币主题，继续补齐此前因配额中断而缺失的详情/回复。
- `--force` 关闭余额页剪枝，重新抓取完整范围，并重新检查所有投币主题。
- 余额页是 HTML，不占 V2EX API 2.0 配额；主题详情和回复占 600 次/小时配额。
  首次补齐数百个主题可能跨多轮 `partial` run，这是预期行为。
- 连续 10 个主题抓取失败会中止本轮剩余扫描（run 本已 `partial`）：限流时每个失败
  主题都要走满客户端重试退避，继续扫描只会让限流窗口更久不恢复。剩余主题在后续
  轮次继续收敛。
- 余额页只提供主题链接，不提供回复 ID，因此投币关系只能记录到主题级。
- 余额页缺少流水表（维护页、风控页）时无法区分“没有流水”，会打印警告并把本次 run
  标记为 `partial`，而不是当作完整空结果。
- 被删除的主题会保留感谢记录，但详情抓取会持续失败并保持 `partial`；本期不做删除检测。

## 示例

```shell
eto v2ex -o output/v2ex
eto --db-only v2ex
eto --db-only v2ex --tipped
eto --db-only v2ex --tipped --force
```

[返回命令索引](./README.md)
