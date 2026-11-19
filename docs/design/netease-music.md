---
status: 已实现
created: 2026-11-17
modified: 2026-11-18
tags: [feature, data]
---

# 网易云音乐歌单与听歌历史入库设计

- Issue: [#8](https://github.com/bgzolab/export-all-to-obsidian/issues/8)
- Status: 已实现
- Date: 2026-11-17
- Implemented: 2026-11-18
- Related: [projection-layer.md](projection-layer.md)、[raw-response-layer.md](raw-response-layer.md)、[incremental-pruning.md](incremental-pruning.md)

## 背景与目标

Issue #8 给出的是 `https://music.163.com/#/user/songs/rank?id=xxx`，也就是“听歌排行”页面。用户真正想要的是更接近“听歌历史”的数据，同时希望把网易云歌单落库，并明确要求听歌排行、听歌历史不能污染歌曲库。

网易云没有公开的完整听歌历史接口。当前可获得的只有：

- 最近播放：按时间倒序的滚动窗口，默认 100 条，带 `playTime`（毫秒），没有 offset/游标。
- 听歌排行：按周/全部时间聚合的 Top 列表，单次最多约 1000 条，只有 `playCount` / `score`，没有逐次播放时间。

因此本设计把“历史”定义为：**从首次同步开始，持续累积最近播放记录**；不承诺回填更早的历史。排行响应只写入 raw 层，不建投影表。

目标：

- 新增 `eto --db-only netease`，抓取当前登录账号的自建歌单（含“我喜欢的音乐”）并落库。
- 歌曲库拆成 `netease_song`、`netease_playlist`、`netease_playlist_song` 三张投影表。
- 最近播放写入独立的 `netease_play_record`，保存歌曲快照，不写 `netease_song`，不设外键。
- 周榜/总榜写入 raw（`netease.play.rank.week` / `netease.play.rank.all`），未来用 Python 从 raw 读取。
- 所有响应仍写入 `sync_run` / `sync_response`，支持 `eto db rebuild netease` 幂等重建。

非目标：

- 不做完整历史回填；上游不存在该接口。
- 不建排行投影表；不导出排行 Markdown。
- 不导出任何 Markdown / 索引；v1 只落库。
- 不抓取收藏的歌单（订阅歌单），只抓 `creator` 为自己的歌单。
- 不做删除检测、多账号、歌词/评论、歌单编辑历史。
- 不使用官方开放平台 API（个人开发者不可用）。

## 范围

- 包含：
  - `eto --db-only netease [--uid UID] [--force]`。
  - 网易云 weapi 客户端与 `pycryptodome` 加密依赖。
  - 自建歌单列表、歌单详情、歌曲详情分批抓取。
  - 最近播放抓取与历史投影表。
  - 周榜/总榜抓取与 raw 记录。
  - 迁移 `005_netease.sql`、投影解析器、凭证探针、CLI、测试与文档。
- 不包含：
  - Markdown、索引、`--output-only`。
  - 排行投影表。
  - 订阅/收藏歌单。
  - 完整历史回填、删除检测、多账号。
  - 官方开放平台、登录流程、验证码/扫码登录。

## 调研结论

### 接口

| 数据 | 上游路径 | 加密 | 分页/上限 | 关键字段 |
| --- | --- | --- | --- | --- |
| 账号 | `POST /weapi/w/nuser/account/get` | weapi | 无 | `account`、`profile`；匿名时为空对象 |
| 用户歌单 | `POST /weapi/user/playlist` | weapi | `limit` / `offset` / `more` | `playlist[]`、`more` |
| 歌单详情 | `POST /weapi/v6/playlist/detail` | weapi | 无 | `playlist.trackIds` 完整；`playlist.tracks` 只带少量完整对象 |
| 歌曲详情 | `POST /weapi/v3/song/detail` | weapi | `c` 为 JSON 数组，单批最多 1000 | `songs[]` |
| 最近播放 | `POST /weapi/play-record/song/list` | weapi | `limit` 默认 100；无 offset/游标 | `data.total`、`data.list[]`；每条含 `playTime`（毫秒）、`data` 歌曲、`resourceType`、`banned`、`multiTerminalInfo` |
| 听歌排行 | `POST /weapi/v1/play/record` | weapi | `type=0/1`、`limit` 最多约 1000、`offset`、`total` | `allData` / `weekData`、`allDataSize` / `weekDataSize`；每行 `{playCount, score, song}` |

实测补充：

- 2026-11-17 用仓库根目录 `cookies.txt` 做只读探测，公开歌单、歌单详情、歌曲详情接口均可用，weapi 加密路径正确。
- 一个 `trackCount=1273` 的大型歌单，`playlist.trackIds` 返回 1273 条，`playlist.tracks` 只返回 6 条完整歌曲对象。因此歌曲详情必须用 `trackIds` 再调 `/weapi/v3/song/detail` 分批补全。
- 当前 `cookies.txt` 中的 `MUSIC_U` 未通过登录态校验：账号接口返回空的 `account` / `profile`，最近播放返回 `total=0`。实现后的端到端验证需要重新登录 `music.163.com` 并导出 Cookie。

### 鉴权

- 需要 `music.163.com` 域的 `MUSIC_U` Cookie；`__csrf` 对只读接口不是必需，存在时原样带进 weapi payload。
- weapi 使用两轮 AES-128-CBC（固定 key `0CoJUm6Qyw8W8jud` + 固定 IV `0102030405060708`，第二轮的 key 为随机 16 字节），再用固定公钥做 RSA；Python 侧用 `pycryptodome` 只处理 AES，RSA 用 `pow` 完成。
- Cookie 文件只按 `music.163.com` 匹配，不把 `.163.com` 的无关 Cookie 一起发送。

### 历史可得性

- `/play-record/song/list` 是滚动窗口，不是完整事件日志；平台可能只保留每首歌的最近记录，重复播放不一定每次都有独立行。
- 没有 offset/游标，不能翻页；要形成本地历史，只能从第一次同步开始持续运行 `eto --db-only netease`。
- 两次运行之间的播放记录可能被窗口挤出；这是上游限制，不是实现缺陷。
- 排行只有聚合计数，不能反推逐次播放时间。

## 方案设计

### CLI 与运行模式

`netease` 是 DB-only 平台，必须与全局 `--db-only` 一起使用；普通导出模式直接报 `UsageError`，避免静默不写 Markdown。

```shell
eto --db-only netease
eto --db-only netease --uid 123456
eto --db-only netease --force
```

- `--uid` / `-u` 可选：默认调用账号接口，从 `account.id` 或 `profile.userId` 自动识别。
- 显式传入的 `--uid` 必须与当前登录账号一致；不一致时拒绝执行，避免把别人的公开歌单当成自己的数据。
- `--force`：忽略“歌单未变更”剪枝，重新抓取所有自建歌单的详情和歌曲。
- 没有 `-o` / `-t`；`--index-file` 与 `--db-only` 的全局互斥规则不变。
- `sync_run.operation='sync'`，`scope=None`；单账号假设，uid 通过 raw request 的 `meta.uid` 记录。

### 抓取流程

```text
account = client.get_account()
uid = --uid or account.account.id or account.profile.userId
if uid 为空: 报错并结束
if --uid 与 uid 不一致: 报错并结束

playlists = []
offset = 0
while pages < MAX_PLAYLIST_PAGES:
    page = client.list_playlists(uid, limit=1000, offset=offset)
    playlists += page.playlist or []
    if not page.more: break
    if page.playlist 为空: break
    offset += 1000

own = [p for p in playlists if creator_id(p) == uid]
for p in own:
    if not force and unchanged(p): 跳过
    detail = client.get_playlist_detail(p.id)
    for batch in chunks(detail.playlist.trackIds, 500):
        client.get_song_details(batch)

client.get_recent_plays(limit=100)
client.get_play_rank(uid, 'week', limit=1000)
client.get_play_rank(uid, 'all', limit=1000)
```

说明：

- `creator_id(p)` 取 `p.creator.userId`，缺失时回退到 `p.userId`；只保留等于当前 uid 的歌单。“我喜欢的音乐”是 `specialType=5`、creator 为自己的歌单，因此包含在内。
- 歌单列表每页 1000 条；`MAX_PLAYLIST_PAGES=20` 是防御性上限，超过时打印提示并标记 `partial`。
- 歌曲详情每批 500 个 id，低于上游单批 1000 的上限，减少单次响应体积。
- 历史固定请求 100 条；排行固定请求 1000 条，`type=0` 为全部时间，`type=1` 为最近一周。
- 所有数据请求都走 `export_runtime.http`，endpoint 固定为：
  - `netease.playlists.page`
  - `netease.playlist.detail`
  - `netease.songs.detail`
  - `netease.play.recent`
  - `netease.play.rank.week`
  - `netease.play.rank.all`

### 只投影自建歌单

`/weapi/user/playlist` 的响应同时包含自建歌单和订阅歌单；投影层只应保留自建歌单。为不依赖额外的账号表，客户端在 raw request 的 `meta` 中记录本次请求的 uid：

```json
{
  "method": "POST",
  "url": "https://music.163.com/weapi/user/playlist",
  "headers": {"Cookie": "[REDACTED]"},
  "body": {"params": "...", "encSecKey": "..."},
  "meta": {"uid": 123456}
}
```

投影解析 `netease.playlists.page` 时，按 `meta.uid` 过滤 `creator_id` 不等于 uid 的条目。实际 HTTP 请求仍只发送加密表单，`meta` 只进入 raw 层，不改变上游请求。

`export_runtime.http` 为此增加可选的 `request_meta` 参数；不传时 request JSON 结构与现在完全一致，兼容已有平台。

### 数据模型

新增迁移 `005_netease.sql`，创建 4 张 `STRICT` 表：

```sql
CREATE TABLE netease_playlist (
    playlist_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    cover_img_url TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    creator_id INTEGER NOT NULL DEFAULT 0,
    creator_json TEXT CHECK (json_valid(creator_json)),
    track_count INTEGER NOT NULL DEFAULT 0,
    play_count INTEGER NOT NULL DEFAULT 0,
    subscribed_count INTEGER NOT NULL DEFAULT 0,
    create_time INTEGER NOT NULL DEFAULT 0,
    update_time INTEGER NOT NULL DEFAULT 0,
    track_update_time INTEGER NOT NULL DEFAULT 0,
    special_type INTEGER NOT NULL DEFAULT 0,
    subscribed INTEGER NOT NULL DEFAULT 0 CHECK (subscribed IN (0, 1)),
    privacy INTEGER NOT NULL DEFAULT 0,
    ordered INTEGER NOT NULL DEFAULT 0 CHECK (ordered IN (0, 1)),
    tags_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(tags_json)),
    detail_response_id INTEGER REFERENCES sync_response(id),
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
) STRICT;

CREATE INDEX idx_netease_playlist_creator
    ON netease_playlist(creator_id);

CREATE INDEX idx_netease_playlist_special_type
    ON netease_playlist(special_type);

CREATE TABLE netease_song (
    song_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    artists_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(artists_json)),
    album_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(album_json)),
    duration INTEGER NOT NULL DEFAULT 0,
    publish_time INTEGER NOT NULL DEFAULT 0,
    fee INTEGER NOT NULL DEFAULT 0,
    mv INTEGER NOT NULL DEFAULT 0,
    alias_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(alias_json)),
    trans_names_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(trans_names_json)),
    pop INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 0,
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE netease_playlist_song (
    playlist_id INTEGER NOT NULL REFERENCES netease_playlist(playlist_id),
    song_id INTEGER NOT NULL REFERENCES netease_song(song_id),
    position INTEGER NOT NULL DEFAULT 0,
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL,
    PRIMARY KEY (playlist_id, song_id)
) STRICT;

CREATE INDEX idx_netease_playlist_song_song
    ON netease_playlist_song(song_id);

-- 历史是独立日志：只存歌曲快照，不引用 netease_song，避免污染歌曲库。
CREATE TABLE netease_play_record (
    song_id INTEGER NOT NULL,
    play_time INTEGER NOT NULL,
    resource_type TEXT NOT NULL DEFAULT 'SONG',
    banned INTEGER NOT NULL DEFAULT 0 CHECK (banned IN (0, 1)),
    device_json TEXT CHECK (json_valid(device_json)),
    song_json TEXT NOT NULL CHECK (json_valid(song_json)),
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL,
    PRIMARY KEY (song_id, play_time)
) STRICT;

CREATE INDEX idx_netease_play_record_play_time
    ON netease_play_record(play_time);
```

字段约定：

- `netease_playlist.response_id` 指向歌单列表响应；`detail_response_id` 指向成功抓到 `trackIds` 的详情响应，只用于剪枝，不覆盖主溯源列。
- 平台时间按原类型保留：歌单 `create_time` / `update_time` / `track_update_time`，歌曲 `publish_time`，历史 `play_time`，全部是毫秒 epoch 的 `INTEGER`。
- `netease_playlist` 只保存自建歌单；`creator_id` 来自 `creator.userId`，缺失时回退到 `userId`。
- `netease_playlist_song.position` 是 `trackIds` 中的 0-based 顺序；同一歌单里重复的 song id 只保留第一次出现的位置。
- `netease_song` 的 `artists_json`、`album_json`、`alias_json`、`trans_names_json` 来自 `ar/al/alia/tns`；旧式报文回退到 `artists/album/alias/transNames`。
- `netease_play_record` 不设 `song_id -> netease_song` 外键；`song_json` 保存完整歌曲快照，保证历史不依赖歌曲库是否仍有该行。
- 排行不建表。`netease.play.rank.week` / `netease.play.rank.all` 的响应只留在 raw 层。

### 投影与重建

`src/db/projections/netease.py` 实现 `rebuild(connection)`。

删除顺序：

1. `netease_play_record`
2. `netease_playlist_song`
3. `netease_song`
4. `netease_playlist`

回放顺序：

1. `netease.playlists.page`：upsert `netease_playlist`；按 `request.meta.uid` 过滤非自建歌单。
2. `netease.playlist.detail`：按 `playlist.id` 替换 `netease_playlist_song` 成员；为 `trackIds` 中缺失的歌曲插入占位行；更新 `detail_response_id`。
3. `netease.songs.detail`：upsert `netease_song` 完整字段。
4. `netease.play.recent`：upsert `netease_play_record`，按 `(song_id, play_time)` 去重。

成员替换规则：

- 每条详情响应先 `DELETE FROM netease_playlist_song WHERE playlist_id = ?`，再按 `trackIds` 顺序插入。最后一条详情响应决定成员列表。
- `trackIds` 缺失或不是列表时跳过该响应并计数，不删除旧成员，避免坏响应把歌单清空。
- `trackIds` 是空列表时删除旧成员并不插入，表示空歌单。
- 详情响应对应的 `netease_playlist` 行不存在时，`aux_missed++` 并跳过；正常情况下列表响应已先回放。

占位歌曲：

- 成员插入前，对每个 `song_id` 执行 `INSERT ... ON CONFLICT(song_id) DO NOTHING`，写入 `name=''` 等默认值。
- 这样 `netease_playlist_song` 的外键始终成立；后续 `netease.songs.detail` 用正常 upsert 补全字段。
- 占位插入不能覆盖已有的完整歌曲行，因此必须使用 `DO NOTHING`，不能复用普通 upsert。

历史：

- `netease.play.recent` 的 `data.list[]` 逐条 upsert 到 `netease_play_record`。
- 只接受 `resourceType == 'SONG'` 或缺失 `resourceType` 的记录；其他类型跳过并计数。
- `data` 不是对象、`data.id` 缺失、`playTime` 不是正整数时跳过该条并计数。
- 同一 `(song_id, play_time)` 在多轮响应中重复出现时只保留一行；`response_id` 可更新为较新的观察响应。
- 历史表只增不删；`rebuild` 会先清空再回放全部 raw，因此同一份 raw 连续重建两次结果一致。

失败处理：

- `netease.playlists.page` 是主实体响应。`code != 200` 时：
  - `301` / `401` / `403` 视为登录失效，抛 `ProjectionError`，整体回滚，避免用登录失败响应清空投影。
  - 其他 code 记为业务无数据，跳过并计数。
  - `playlist` 键缺失或不是列表/nil 时抛 `ProjectionError`；`playlist: null` 是合法空页。
- `netease.playlist.detail`、`netease.songs.detail`、`netease.play.recent` 是辅助/日志响应：
  - 200 非 JSON、缺少业务字段、顶层类型错误时跳过并计数，不阻塞整个平台。
  - 单条无效记录跳过并计数，不静默丢弃。
- 所有跳过都要在 `RebuildResult` 里体现；命令输出沿用现有 summary。

### 增量与剪枝

- 歌单列表每次完整抓取，不用本地投影做页级停止。
- 歌单详情按 `track_count`、`track_update_time`、`detail_response_id` 判断是否未变更：
  - 三者都存在且与当前列表一致，并且所有成员歌曲都已投影出 `netease.songs.detail`
    元数据（没有占位行）时跳过详情和歌曲请求。
  - `--force` 跳过该判断。
  - 新歌单、track 数变化、更新时间变化、上次详情失败（`detail_response_id IS NULL`）、
    歌曲批次失败留下占位行，都会重新抓取。
- 历史每次抓取固定 100 条；没有本地游标，重复记录由主键去重。
- 排行每次抓取周榜和总榜各一次；不投影。
- 不做删除检测：取消收藏、删除歌单、从歌单移除歌曲后，旧投影行保留到未来的删除策略实现。
- `--force` 不改变历史/排行的抓取范围，只影响歌单详情剪枝。

### 凭证与错误处理

凭证探针 `probe_netease_credentials`：

- 调用账号接口，不写入 raw。
- 200 且 `account` / `profile` 至少一个包含 `id` 或 `userId`：`valid`。
- 200 但 `account` / `profile` 为空：`invalid`，提示 `MUSIC_U 未登录或已失效，请重新导出 cookies.txt`。
- 301 / 401 / 403：`invalid`。
- 非 200、非 JSON、非对象、请求异常：`unknown`。
- `MUSIC_U` 缺失：`get_cookie_header` 抛 `ValueError`，按现有规则判为 `invalid`；`cookies.txt` 不存在/不可读则 `CookiesConfigError` 转 `ClickException`。

运行期错误：

| 情况 | 行为 |
| --- | --- |
| 账号 200 空对象 | 报错并结束，不抓任何数据 |
| `--uid` 与账号不一致 | `ClickException`，不抓任何数据 |
| 歌单列表 HTTP/JSON/code 错误 | 标记 `partial`，停止歌单抓取，继续历史/排行 |
| 单个歌单详情失败 | 标记 `partial`，打印歌单 id，继续下一个歌单 |
| 单批歌曲详情失败 | 标记 `partial`，打印批次，继续下一批 |
| 历史请求失败 | 标记 `partial`，继续排行 |
| 排行请求失败 | 标记 `partial`，不阻塞其他数据 |
| HTTP 429 | 标记 `partial`，停止本轮后续请求，下一轮再补 |
| 5xx / 传输异常 | 标记 `partial`，按资源粒度决定继续或停止 |
| 200 + `code != 200` | 标记 `partial`，打印 code/message；301 额外提示 Cookie 失效 |

`sync_run.status`：

- `success`：所有计划请求都成功（允许空数据）。
- `partial`：任一请求失败、页数上限截断、历史/排行失败。
- `failed`：账号校验失败或未捕获异常。

### 依赖与文件布局

新增运行时依赖 `pycryptodome`，只用于 AES-128-CBC；RSA 用 Python 整数幂完成。

```text
src/netease/
    __init__.py
    api_endpoints.py      # 上游路径与常量
    weapi.py              # weapi 加密
    client.py             # Cookie、Session、账号/歌单/歌曲/历史/排行请求
    exporter.py           # 抓取编排、剪枝、partial 标记
src/db/migrations/005_netease.sql
src/db/projections/netease.py
docs/usages/netease.md
```

## 关键决策

- **DEC-001**：建 4 张投影表：歌单、歌曲、歌单歌曲关联、历史；排行不建表。理由：用户要求历史/排行不污染歌曲库；历史需要可查询，排行可以以后从 raw 回放。
- **DEC-002**：`netease` 必须与 `--db-only` 一起使用。理由：v1 不生成 Markdown，普通导出模式静默无输出会误导用户。
- **DEC-003**：只抓 creator 为自己的歌单，包含“我喜欢的音乐”，排除订阅歌单。理由：用户明确选择“仅自己创建”，同时红心歌曲是歌曲库的重要组成部分。
- **DEC-004**：uid 默认从账号接口自动识别，`--uid` 仅作覆盖；不一致时拒绝。理由：减少手工参数，同时避免导出别人账号的公开数据。
- **DEC-005**：weapi 用 `pycryptodome`，不手写 AES，也不引入本地 Node 服务。理由：AES 是唯一需要的加密原语，`pycryptodome` 体积小、实现成熟；自建 Node 服务会增加运行时常驻进程和 Cookie 暴露面。
- **DEC-006**：歌单元数据来自歌单列表响应，详情响应只负责成员和 `detail_response_id`。理由：列表字段完整，详情字段较少；混用两套 upsert 会把列表字段覆盖成默认值。
- **DEC-007**：成员按 `trackIds` 建，歌曲详情按 500 一批补全；不使用 `playlist.tracks`。理由：实测 1273 首歌单只返回 6 个完整对象，`tracks` 不足以建库。
- **DEC-008**：成员插入前先插占位歌曲，占位用 `DO NOTHING`。理由：既保证外键成立，又不会用空字段覆盖已有的完整歌曲行。
- **DEC-009**：每条详情响应替换整个歌单成员。理由：歌单顺序和成员会变化，逐条 upsert 无法删除已移除的歌曲。
- **DEC-010**：历史是“从首次同步开始累积”的滚动窗口。理由：上游没有完整历史接口；这是唯一诚实的数据边界。
- **DEC-011**：排行只写 raw，查询用 `db.raw.iter_responses`。理由：用户不需要排行投影；raw 已保存每次响应，未来可以按需回放。
- **DEC-012**：歌单列表请求在 raw request 的 `meta.uid` 记录 uid，投影按它过滤自建歌单。理由：`user/playlist` 同时返回订阅歌单，响应本身没有当前账号 uid；`meta` 比动态 endpoint 或额外账号表更直接。
- **DEC-013**：凭证探针必须走账号接口，不能靠历史接口判断登录态。理由：未登录时历史接口也返回 200 + 空列表，会静默丢数据。
- **DEC-014**：歌单列表的 301/401/403 在重建时视为致命错误，不用登录失败响应清空投影。理由：投影重建先删表再回放，静默跳过会丢掉全部歌单。

## 备选方案

- **ALT-001**：建 5 张表，排行也建快照表。未采用：用户明确不需要排行投影；raw 已保留每次排行响应。
- **ALT-002**：只建歌曲表 + 关联表，歌单元数据留在 raw。未采用：无法直接列出歌单、按歌单查询或导出歌单标题。
- **ALT-003**：把历史/排行写进 `netease_song`，加来源标记。未采用：会让歌曲库被历史/排行污染，且无法表达逐次播放时间。
- **ALT-004**：本地跑一个 `NeteaseCloudMusicApi` Node 服务。未采用：多一个常驻进程、Cookie 暴露面和部署成本；Python 直连 weapi 足够。
- **ALT-005**：纯 Python 实现 AES，避免新增依赖。未采用：手写 AES 代码和测试量更大，维护风险高于引入成熟库。
- **ALT-006**：使用 `cryptography` 而不是 `pycryptodome`。未采用：为一个 AES-CBC 调用引入更重的依赖；`pycryptodome` 更贴合现有 NetEase 实现习惯。
- **ALT-007**：v1 同时生成 Obsidian Markdown。未采用：用户明确要求先落库；历史的按日/按次分组和增量文件名需要单独设计。
- **ALT-008**：走网易云官方开放平台。未采用：个人开发者场景官方明确不支持读取听歌记录。
- **ALT-009**：用 `sync_run.scope` 传 uid，不扩展 `request_meta`。未采用：scope 在 run 开始时固定，自动识别 uid 时无法回填；`request_meta` 对加密 API 的其他语义参数也通用。
- **ALT-010**：保留订阅歌单元数据，只在查询时过滤。未采用：用户选择“仅自己创建”，投影层不应保留订阅歌单行。

## 风险与限制

- **RISK-001**：没有完整听歌历史；最近播放是滚动窗口，必须在窗口挤出前反复运行。两次运行之间可能丢记录。
- **RISK-002**：`MUSIC_U` 会过期；账号接口在匿名时仍返回 200 空对象，历史接口返回 200 空列表。探针必须拦住，否则会静默空跑。
- **RISK-003**：weapi 算法或密钥常量可能随客户端改版变化；失效时需要更新 `weapi.py` 和测试向量。
- **RISK-004**：大歌单会产生多次歌曲详情请求；上游限流数值未公开，429 时只能停止本轮，下一轮再补。
- **RISK-005**：`trackIds` 对超大歌单可能被上游截断；`trackCount` 与成员数不一致时只能提示，无法自动补齐。
- **RISK-006**：最近播放可能对同一首歌只保留最近一次，不能当作完整播放事件日志。
- **RISK-007**：不做删除检测；取消收藏、删除歌单、移除歌曲后的旧行会保留。
- **RISK-008**：`pycryptodome` 是新增运行时依赖，需要更新 `poetry.lock`。
- **RISK-009**：排行只在 raw 层，`sync_response.body` 是 zlib 压缩的；SQL 客户端不能直接 `json_extract`，必须用 Python 解压。
- **RISK-010**：历史 raw 持续增长，`db rebuild netease` 的回放时间会随运行次数增加。
- **RISK-011**：详情剪枝依赖 `track_update_time` 和 `track_count`；歌曲元数据变化但歌单未更新时不会刷新，需要 `--force`。
- **RISK-012**：`__csrf` 缺失时只读接口仍可用，但上游未来可能收紧；届时需要先访问首页获取 Cookie。
- **RISK-013**：`request_meta` 是 raw request JSON 的新增字段；旧消费方需要忽略未知键。当前没有依赖固定键集合的代码。
- **RISK-014**：`COOKIES` 环境变量可能仍指向旧的 cookies 文件；端到端验证时用
  `--cookies-file cookies.txt` 显式指定刚导出的文件。

## 验证方式

- **TEST-001**：weapi 加密对固定 payload + 固定 secret 生成已知 `params` / `encSecKey`；并用 AES 解密两层验证明文 round-trip。
- **TEST-002**：客户端对账号、歌单列表、歌单详情、歌曲详情、最近播放、周榜/总榜发出正确的 endpoint、加密表单和 `request_meta`；账号请求不写 raw，数据请求写 raw。
- **TEST-003**：迁移后 `user_version=5`，存在 4 张网易云投影表和 4 个索引；JSON / STRICT / 外键约束生效。
- **TEST-004**：投影只保留 `meta.uid` 对应的自建歌单；歌曲按详情 upsert；成员按详情替换；缺失歌曲生成占位；历史按 `(song_id, play_time)` 去重。
- **TEST-005**：同一份 raw 连续重建两次，除 `db_created_at` / `db_updated_at` 外逐列相等。
- **TEST-006**：歌单列表 301 在重建时回滚；辅助响应坏 JSON 跳过并计数；历史单条缺 `playTime` 跳过并计数。
- **TEST-007**：CLI 在非 `--db-only` 下报 `UsageError`；`--uid` 不一致报错；`--force` 跳过详情剪枝。
- **TEST-008**：`PYTHONPATH=src pytest tests -q`、`ruff check src tests`、`ruff format --check src tests` 全部通过。
- **TEST-009**：用有效 `MUSIC_U` 手工执行 `eto --db-only netease`，检查 4 张表、raw 中的排行响应，再执行两次 `eto db rebuild netease` 验证幂等。
