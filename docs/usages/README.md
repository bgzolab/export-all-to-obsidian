# 命令用法

本目录按子命令整理 `eto` 的用法。全局参数必须写在子命令之前：

```shell
eto [全局参数] <命令> [命令参数]
```

安装和加载 `.env` 的步骤见仓库根目录的 [README](../../README.md#quick-start)。

## 全局参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--index-file PATH` | 无 | 索引 Markdown 输出路径；不传时把索引直接打印到终端 |
| `--prefix TEXT` | `~` | 导出文件名和索引链接的统一前缀；`--prefix ""` 可关闭前缀 |
| `--cookies-file PATH` | 环境变量 `COOKIES` | Netscape 格式 `cookies.txt` 的路径 |
| `--db PATH` | `data/eto.db` | SQLite 数据库路径 |
| `--db-only` | 关闭 | 只抓取 API 并写入 raw/投影表，不生成 Markdown 和索引 |

`--cookies-file` 优先于环境变量 `COOKIES`。`--index-file`、`--prefix`、`--cookies-file`、`--db` 和 `--db-only` 都只能放在子命令前面。`--index-file` 与 `--db-only` 互斥。

```shell
eto --prefix "" github -t config/template/github.md -o output/github
eto --cookies-file ./cookies.txt zhihu -c your-collection-id -o output/zhihu
eto --index-file output/index/export-index.md --db ./data/eto.db weibo -u your-user-id -o output/weibo
eto --db-only bangumi -s 2 -c 3
```

## 环境变量

| 变量 | 适用命令 | 说明 |
| --- | --- | --- |
| `CNBLOG_ACCESS_TOKEN` | `cnblog` | 博客园访问令牌 |
| `BGM_ACCESS_TOKEN` | `bangumi` | Bangumi 访问令牌 |
| `V2EX_ACCESS_TOKEN` | `v2ex` | V2EX 访问令牌，同时还需要 `v2ex.com` 的 Cookie |
| `GITHUB_TOKEN` | `github` | GitHub 访问令牌 |
| `TWITTER_CSRF_TOKEN` | `twitter` | 可选；未设置时从 Cookie 的 `ct0` 推导 |
| `TWITTER_USER_ID` | `twitter` | 可选；未设置时从 Cookie 的 `twid` 推导 |
| `COOKIES` | `qireader`、`v2ex`、`zhihu`、`weibo`、`bilibili`、`twitter` | Netscape 格式 `cookies.txt` 的路径，不是 Cookie 内容本身 |
| `TELEGRAM_BOT_TOKEN` | 所有会验活导出的命令 | 可选；凭证失效提醒 |
| `TELEGRAM_CHAT_ID` | 所有会验活导出的命令 | 可选；也接受别名 `TELEGRAM_BOT_CHAT_ID` |

`cookies.txt` 至少需要包含对应平台的域名。各命令需要的域名见各自的说明页。

## 命令索引

| 命令 | 导出内容 | 必需凭证 | 支持 `--force` |
| --- | --- | --- | --- |
| [`cnblog`](./cnblog.md) | 博客园收藏 | `CNBLOG_ACCESS_TOKEN` | 是 |
| [`bangumi`](./bangumi.md) | Bangumi 收藏 | `BGM_ACCESS_TOKEN` | 是 |
| [`qireader`](./qireader.md) | 稍后读列表 | `COOKIES` | 是 |
| [`github`](./github.md) | GitHub stars | `GITHUB_TOKEN` | 是 |
| [`v2ex`](./v2ex.md) | V2EX 收藏主题 | `V2EX_ACCESS_TOKEN` + `COOKIES` | 是 |
| [`zhihu`](./zhihu.md) | 知乎收藏夹 | `COOKIES` | 是 |
| [`weibo`](./weibo.md) | 微博点赞 | `COOKIES` | 是 |
| [`bilibili`](./bilibili.md) | Bilibili 收藏夹 | `COOKIES` | 是 |
| [`twitter`](./twitter.md) | Twitter 点赞 | `COOKIES` | 是 |
| [`import-markdown`](./import-markdown.md) | 把已有 Markdown 导入数据库 | 无 | 否 |
| [`db rebuild`](./db.md) | 从 raw 响应重建平台投影表 | 无 | 否 |

## 公用行为

### 凭证验活

除 `github` 和 `import-markdown` 外，每个导出命令在开始前都会做一次轻量凭证探针：

- 确认凭证失效时，跳过本次导出。
- 配置了 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID` 时，发送 Telegram 提醒。
- 因网络或服务异常无法确认时，打印提示后继续导出。

### 增量与 `--force`

默认情况下，导出器把「目标文件已存在」视为本地增量信号：

- 命中已存在文件时，当前导出流程提前结束，本次同步记录标记为 `partial`。
- 支持 `--force` 的命令会覆盖已有文件并继续遍历。
- 不支持 `--force` 的命令（`cnblog`、`qireader`、`v2ex`、`zhihu`）遇到同名文件就会停止；需要重新导出时，请先移走已有文件或换一个输出目录。

### 输出文件

每个条目写成一个 Markdown 文件，默认前缀为 `~`，例如 `~BV1xxxxxx.md`。输出目录不存在时会自动创建。

大多数命令会自动写入 YAML front matter；`bangumi` 和 `github` 的内容由模板决定。

### 索引文件

不传 `--index-file` 时，索引打印到终端。传入后，索引写入 Markdown 文件，并按模块分组：

```markdown
## zhihu

- [[~zhihu-entry-1|First saved item]]
- [[~zhihu-entry-2|Second saved item]]

## bilibili

- [[~BV1xxxxxx|One saved video]]
```

同一模块重复导出时，新条目追加到该模块的 `##` 分节下，已有顺序不变。

### Raw 数据库

每次 API 响应和 `import-markdown` 导入的文件都会追加到 SQLite 数据库。默认路径是当前目录下的 `data/eto.db`，可用 `--db` 修改。

```shell
eto --db ./data/eto.db zhihu -c your-collection-id -o output/zhihu
```

数据库只增不改。Cookie、Authorization、X-CSRF-Token、X-API-Key 等凭证头会被脱敏，但 URL 和响应正文仍可能包含敏感数据，请把数据库当作凭证文件保管，不要提交到版本库。

### `--db-only` 与投影层

`--db-only` 仍然请求 API、写入 `sync_run` / `sync_response`，但：

- 不要求 `-o` / `-t`，不写 Markdown，不写索引，不创建输出目录。
- 不豁免凭证：各平台的 token / cookie 仍然必需。
- 不因目标文件已存在而提前结束；`--max-pages` 等显式抓取范围参数仍然生效。
- 默认启用增量剪枝：列表页照常抓取，但已存在的详情/辅助请求（如 README、长文、
  正文、角色、主题详情）会跳过；传 `--force` 可关闭剪枝并完整抓取。
- 所有平台在整页条目都已知时停止后续分页（乐观假设列表稳定、新数据在前），
  本次 run 标记为 `partial`。
- 抓取结束后在同一 `sync_run` 内重建该平台的投影表。
- 传输错误和非 200 响应在重建时跳过并计数；200 响应解析失败或违反约束仍会整体回滚。
- 投影失败时本次 run 标记为 `partial`，命令非零退出；raw 已保存，可稍后执行
  `eto db rebuild <platform>`。

```shell
eto --db-only github
eto --db-only v2ex
eto --db-only twitter --max-pages 10
```

投影表按平台划分，不是跨平台统一模型。日常查询/导出可以只读投影表；raw 层保留给
全量重建、补列和灾难恢复。`--force` / `--prefix` 在 `--db-only` 下无意义，会被忽略。
