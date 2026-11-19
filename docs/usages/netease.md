# netease

把当前登录账号的网易云自建歌单、歌曲、歌单成员和最近播放写入数据库。该命令只支持
`--db-only`，不生成 Markdown 和索引。

## 用法

```shell
eto [全局参数] --db-only netease [--uid UID] [--force]
```

## 参数

| 参数 | 必需 | 说明 |
| --- | --- | --- |
| `--uid`, `-u` | 否 | 用户 ID；默认从账号接口自动识别 |
| `--force` | 否 | 忽略歌单详情剪枝，重新抓取全部自建歌单 |

`--db-only` 是全局参数，必须写在 `netease` 前面。非 db-only 调用会报
`netease requires --db-only` 并退出 2。

## 凭证

需要 `music.163.com` 域的 `MUSIC_U` Cookie。Cookie 来自 Netscape 格式的
`cookies.txt`：

- 默认读取环境变量 `COOKIES` 指向的文件；
- 可用全局 `--cookies-file` 覆盖。

命令先用账号接口验活。账号接口返回 200 但 `account` / `profile` 为空时，说明
`MUSIC_U` 未登录或已失效，本次不会抓取任何数据。

```shell
eto --cookies-file ./cookies.txt --db-only netease
```

`--uid` 只做覆盖和校验。显式传入的 uid 与当前登录账号不一致时，命令直接报错，
避免把别人账号的公开歌单写进自己的库。

## 抓取范围

1. 账号接口识别 uid（不写入 raw）。
2. 用户歌单列表，每页 1000 条，最多 20 页；只保留 `creator` 为自己的歌单，
   包含“我喜欢的音乐”，排除订阅歌单。
3. 每个歌单详情：读取完整 `trackIds`；所有待抓歌单的歌曲 id 去重后，按 500 个一批
   请求歌曲详情。
4. 最近播放，上游返回最近约 300 条（`limit` 参数未生效）。
5. 周榜和总榜，各请求 1000 条（上游实际返回前 100 条）；只写入 raw 层，不建投影表。

歌单详情默认剪枝：上次详情的 `track_count`、`track_update_time` 与本次列表一致，
已有 `detail_response_id`，且所有成员歌曲都已补全元数据时，跳过详情和歌曲请求。
`--force` 绕过该判断。

## 数据表

| 表 | 内容 |
| --- | --- |
| `netease_playlist` | 自建歌单元数据 |
| `netease_song` | 歌曲元数据；歌单成员中缺失的歌曲先写占位行 |
| `netease_playlist_song` | 歌单与歌曲的多对多关系及 `position` |
| `netease_play_record` | 最近播放日志，按 `(song_id, play_time)` 去重 |

`netease_play_record` 只保存歌曲快照，不引用 `netease_song`；历史/排行不会污染歌曲库。

raw endpoint：

- `netease.playlists.page`
- `netease.playlist.detail`
- `netease.songs.detail`
- `netease.play.recent`
- `netease.play.rank.week`
- `netease.play.rank.all`

## 增量与限制

- 上游没有完整听歌历史，只有滚动窗口；`netease_play_record` 从首次同步开始累积，
  两次运行之间被窗口挤出的记录无法补回。
- 不做删除检测：取消收藏、删除歌单、从歌单移除歌曲后，旧投影行会保留。
- 歌单详情剪枝只看歌单更新时间，且要求上次的歌曲批次已全部入库；歌曲元数据单独变化时
  用 `--force` 刷新。
- 成功批次未返回的歌曲（下架）记为不可用，不再阻塞剪枝；歌曲重新上架后需要 `--force`
  才会重试元数据。
- 404/429/5xx 或业务 `code != 200` 会把本次 run 标记为 `partial`；HTTP 429 会停止
  本轮后续请求，下一次运行继续补。
- 排行不投影，查询需要先用 Python 解压 raw body：

```python
import json

from db.connection import connect
from db.raw import latest_response

connection = connect('data/eto.db')
response = latest_response(connection, 'netease.play.rank.week')
payload = json.loads(response['body'])
for row in (payload.get('weekData') or [])[:10]:
    song = row.get('song') or {}
    print(row.get('playCount'), song.get('name'))
```

## 示例

```shell
eto --cookies-file ./cookies.txt --db-only netease
eto --cookies-file ./cookies.txt --db-only netease --force
eto --db data/eto.db db rebuild netease
```

## 相关

- 设计：[docs/design/netease-music.md](../design/netease-music.md)
- 投影层：[docs/design/projection-layer.md](../design/projection-layer.md)
- 数据库维护：[db.md](./db.md)

[返回命令索引](./README.md)
