# Raw Response Layer Design

- Issue: [#16](https://github.com/bgzolab/export-all-to-obsidian/issues/16)
- Status: Implemented
- Date: 2026-11-07

## 1. 目标

所有 API 响应和已有 Markdown 文件原样存入 SQLite，只增不改。以后做规范化、恢复或统计，都从 raw 重放。

本层只负责保存，不建跨平台规范表，不做删除检测、统计、搜索和 bot。

## 2. 两张表

`sync_run` 是一次任务；`sync_response` 是任务下的每条响应或文件。子表通过 `run_id` 关联父表。

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

CREATE INDEX idx_sync_response_run ON sync_response(run_id);
CREATE INDEX idx_sync_response_lookup ON sync_response(endpoint, fetched_at);
CREATE INDEX idx_sync_response_sha256 ON sync_response(sha256);
```

非直观字段：

- `sync_run.status`：`running` / `success` / `partial` / `failed`。导出因文件已存在提前结束时标 `partial`。
- `sync_run.command`：`shlex.join(sys.argv)`，一行纯文本，方便复现。
- `sync_response.request`：请求 JSON，包含 method、url、headers、body、页码和游标。Markdown 导入存 `path` 和 `size`。
- `sync_response.body`：`response.content` 原始字节，zlib 压缩。异常时为 NULL。
- `sync_response.sha256`：未压缩 body 的哈希，用于校验和 Markdown 导入去重。
- `status_code`：HTTP 状态码；Markdown 导入为 NULL。

## 3. 写入规则

- 在 HTTP 边界采集，先记录，再解析，再判断状态码。
- 非 2xx、空响应和传输异常也记录。传输异常写 `body=NULL`、`error=...` 后继续抛异常。
- 不保存响应头、content-type 和原始大小；需要时从 body 算。
- 重复请求不去重，每次观察一行。
- `endpoint` 用稳定语义键：`<platform>.<resource>.<action>`，如 `github.stars.list`、`zhihu.collection.page`、`import.markdown`。一旦写入不要改名。
- 时间统一 UTC ISO 8601。
- 请求头只脱敏 `Cookie` 和 `Authorization`（大小写不敏感，值替换为 `[REDACTED]`）。URL、query、body 和其他 header 原样保存。
- 凭证探测不记录。
- 数据库按凭证文件保护：文件 0600，父目录 0700，不提交 git，不公开备份。URL/body 中仍可能含敏感信息。

## 4. 数据来源

API：

- 所有内容请求走 `export_runtime.http`，在活动 `sync_run` 内写入。
- 当前平台：GitHub、知乎、Bilibili、微博、V2EX、Bangumi、Qireader、CNBlog、Twitter。

Markdown：

- `platform='local'`、`operation='import.markdown'`、`endpoint='import.markdown'`。
- 不解析 front matter，先保存文件原始字节。
- 同路径同 `sha256` 跳过；文件变化新增一行。

未来的手工/机器人写入也走 `sync_run` + `sync_response`，用 `operation` 标明来源。

## 5. 重放

- 按 `endpoint` 选择解析器。
- 按 `fetched_at, id` 顺序回放，必须幂等。
- 投影表以后再加；手工修改要事件化或单独存 override，否则会被重放覆盖。

## 6. 数据库

- `--db` 是顶层选项，默认 `data/eto.db`（相对当前目录）。
- WAL、foreign_keys、busy_timeout、synchronous=NORMAL。
- 迁移用编号 SQL + `PRAGMA user_version`，不引入 ORM 或 Alembic。
- 备份使用 SQLite 备份或 `VACUUM INTO`，不要只复制 WAL 模式下的主文件。

## 7. 暂缓

跨平台规范表、删除检测、内容寻址去重、统计、搜索、Telegram bot、多账号。
