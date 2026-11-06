# Raw Response Layer Design

- Issue: [#16](https://github.com/bgzolab/export-all-to-obsidian/issues/16)
- Status: Draft (raw layer only)
- Date: 2026-11-07
- Plan: [`../implementation-plans/issue-16-raw-layer.md`](../implementation-plans/issue-16-raw-layer.md)

## 1. 目标

只做一件事：每次 API 请求、每个已有 Markdown 文件，都原样存进 SQLite。

两张表：

- `sync_run`：一次任务。
- `sync_response`：这次任务下的每条响应或文件。

数据只增不改。以后要规范化、恢复、统计，都从这里重放。

## 2. 边界

做：

- 保存 API 响应和 Markdown 文件。
- 记录任务、响应、状态和错误。
- 提供一个 `--db` 参数。
- 请求头只脱 Cookie 和 Authorization，其余原样保存。

不做：

- 不建 `item` / `collection` / `membership` 等规范表。
- 不做删除检测、统计、搜索、Telegram bot。
- 不改现有 Markdown 导出行为。
- 不引入 ORM 或新依赖。

## 3. 两张表

### 3.1 父子关系

`sync_run` 是一次任务，`sync_response` 是任务明细，一对多：

```text
sync_run 1 ─── n sync_response
              sync_response.run_id -> sync_run.id
```

命名共享 `sync` 前缀，子表带 `run_id`，不需要猜父子关系。

### 3.2 `sync_run`

一次任务一行。API 同步、Markdown 导入都算一次任务。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK | 自增主键 |
| `platform` | TEXT | `github` / `zhihu` / `local` |
| `operation` | TEXT | 任务类型，如 `stars` / `collection` / `import.markdown` |
| `scope` | TEXT | 任务范围，如用户名、收藏夹 id、导入目录 |
| `command` | TEXT | 触发本次任务的命令，一行纯文本，可直接复制执行 |
| `started_at` | TEXT | 开始时间，UTC ISO 8601 |
| `finished_at` | TEXT | 结束时间，未结束时为 NULL |
| `status` | TEXT | `running` / `success` / `partial` / `failed` |
| `error` | TEXT | 任务级错误摘要 |

`partial` 用于“跑了一部分”：限流、异常、`--max-pages`、导出提前结束都算。只有完整跑完才是 `success`。

### 3.3 `sync_response`

一条响应或一个文件一行。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK | 自增主键 |
| `run_id` | INTEGER FK | 指向 `sync_run.id` |
| `endpoint` | TEXT | 稳定接口名，如 `github.stars.list` |
| `request` | TEXT | 请求 JSON：method / url / headers / body；页码、游标也在这里 |
| `status_code` | INTEGER | HTTP 状态码；导入文件为 NULL |
| `fetched_at` | TEXT | 拿到响应的时间，UTC ISO 8601 |
| `body` | BLOB | zlib 压缩后的原始字节；异常时可为 NULL |
| `sha256` | TEXT | 未压缩 body 的 sha256；无 body 时为 NULL |
| `error` | TEXT | 传输层异常信息 |

### 3.4 DDL

```sql
CREATE TABLE sync_run (
    id INTEGER PRIMARY KEY,
    platform TEXT NOT NULL,
    operation TEXT NOT NULL,
    scope TEXT,
    command TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    error TEXT
);

CREATE TABLE sync_response (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES sync_run(id),
    endpoint TEXT NOT NULL,
    request TEXT,
    status_code INTEGER,
    fetched_at TEXT NOT NULL,
    body BLOB,
    sha256 TEXT,
    error TEXT
);

CREATE INDEX idx_sync_response_run
    ON sync_response(run_id);

CREATE INDEX idx_sync_response_lookup
    ON sync_response(endpoint, fetched_at);

CREATE INDEX idx_sync_response_sha256
    ON sync_response(sha256);
```

### 3.5 为什么字段这么少

分页参数、游标、请求头都放进 `request` JSON，不再单独建列。响应头、content-type、原始大小暂不保存，需要时从 `body` 算。`body` 统一 zlib；`status=success` 表示完整，`partial` 表示没跑完。规范表等有真实数据后再设计。

## 4. 字段约定

- `request` 是 JSON 文本。API 请求存 method、url、headers、body；分页参数和游标也放里面。导入文件存 `path` 和 `size`。
- `body` 存 `response.content` 的原始字节，zlib 压缩。不要存 `response.text`，不要重新 `json.dumps`。
- `sha256` 是未压缩 body 的哈希，用于校验和 Markdown 导入去重。
- 时间统一 UTC ISO 8601。
- `endpoint` 是 replay 的分发键，一旦写入不要改名；新语义加新 endpoint。
- `command` 存 `shlex.join(sys.argv)` 生成的一行文本，不用 JSON。没有真实命令行时（测试、库调用）为 NULL。
- 重复请求不去重。每次请求一行，便于追溯。
- 请求头只脱敏 `Cookie`、`Authorization`，大小写不敏感，值替换为 `[REDACTED]`。URL、query、body 和其余 header 原样保存，方便以后重试。
- 数据库仍按凭证文件对待：文件权限 0600，父目录 0700，不提交 git，不放到公开备份。

脱敏范围刻意只做 header，不引入字段规则；URL 和 body 里如果出现 token，不做处理。

## 5. 采集规则

- 在 HTTP 边界采集，不在 exporter 里采集。
- 写 `request` 前，只把 `Cookie`、`Authorization` 的值替换为 `[REDACTED]`；其余原样。
- 先记录，再解析，再判断状态码。
- 非 2xx 也记录 body。
- 传输异常记录一行 `body=NULL`、`error=...`，然后继续抛异常。
- 解析失败不重复记录，body 已经在库里。
- 凭证探测（`credential_guard`）不记录，它不是内容数据。
- 不保存响应头，避免额外字段和额外决策。

## 6. 数据来源

### 6.1 API

统一走一个 HTTP 采集器，调用方传入 `run_id`、`endpoint`、`request`。第一版只接 GitHub 试点，验证任务生命周期和分页记录。

### 6.2 已有 Markdown

- `platform='local'`
- `operation='import.markdown'`
- `endpoint='import.markdown'`
- `scope` 为导入目录
- `request` 为 `{"path": "...", "size": ...}`
- `body` 为文件原始字节
- `status_code=NULL`

不解析 front matter。先保住字节，映射以后再做。

同一路径、同一 `sha256` 已有记录时跳过；文件变化则新增一行。

### 6.3 未来的手工/机器人写入

同样走 `sync_run` + `sync_response`，`operation` 标明来源即可。不直接写未来的规范表。

## 7. endpoint 示例

统一用 `<platform>.<resource>.<action>`：

| endpoint | 说明 |
|---|---|
| `github.stars.list` | GitHub stars 分页 |
| `github.repo.readme` | 仓库 README |
| `zhihu.collection.page` | 知乎收藏夹分页 |
| `bilibili.favlist.page` | Bilibili 收藏夹分页 |
| `weibo.likes.page` | 微博点赞分页 |
| `v2ex.topic.detail` | V2EX 主题详情 |
| `bangumi.subject.detail` | Bangumi 条目详情 |
| `twitter.likes.page` | Twitter 点赞分页 |
| `import.markdown` | 旧 Markdown 文件 |

页码和游标不建列，放 `request`。

## 8. replay

- 按 `endpoint` 选解析器。
- 按 `fetched_at, id` 顺序回放。
- 回放必须幂等。
- 投影表以后再加，现在不设计。
- 手工修改如果进入投影，必须事件化或单独存 override，否则重放会覆盖。

## 9. SQLite 与 CLI

连接参数：

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = NORMAL;
```

- `--db <path>` 是顶层选项，必须放在子命令前。
- 未指定时使用 `~/.eto/eto.db`。
- 数据库文件 0600，父目录 0700（Windows 跳过 chmod）。
- 迁移用编号 SQL 文件 + `PRAGMA user_version`，不引入 Alembic。
- 每页请求结束后提交一次事务。

## 10. 验证

- body 压缩/解压后与原始字节一致，`sha256` 正确。
- 非 2xx、传输异常都能落库。
- `sync_run` 状态流转正确。
- `Cookie` / `Authorization` header 被替换为 `[REDACTED]`，其余 header 保留。
- Markdown 导入同路径同 hash 跳过，文件变化新增。
- 试点平台现有导出测试仍然通过。
- 数据库文件权限为 0600，且不在 git 工作区。

## 11. 暂缓

- 跨平台规范表。
- 删除检测。
- 内容寻址去重。
- 响应头、content-type、body 大小等额外元数据。
- 统计、搜索、Telegram bot。
- 多账号。

## 12. 风险

- **数据库仍可能含凭证**：只脱了 Cookie/Authorization header；URL、query、body 或 `command` 里仍可能有敏感信息。必须 0600、gitignore、不要公开备份。
- **存储增长**：所有 body 都保留。先靠 zlib 压缩，需要时再加去重。
- **endpoint 改名**：会让 replay 找不到解析器。新增而不是重命名。
- **WAL 备份**：不要只复制主文件，使用 SQLite 备份或 `VACUUM INTO`。
