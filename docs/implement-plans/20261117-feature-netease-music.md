---
goal: 新增 eto --db-only netease，抓取自建歌单、歌曲、歌单歌曲关联和最近播放历史，排行只保留 raw 响应
created: 2026-11-17
modified: 2026-11-17
status: Planned
design: docs/design/netease-music.md
---

# 网易云音乐歌单与听歌历史入库实施计划

## 目标

实现网易云音乐自建歌单、歌曲、歌单歌曲关联和最近播放历史的数据库入库；排行只写 raw 层；命令只支持 `--db-only`。

## 约束与前提

- **CON-001**：上游没有完整听歌历史；`netease_play_record` 只能从首次同步开始累积最近播放窗口。
- **CON-002**：v1 只落库，不生成 Markdown、不写索引；命令必须与 `--db-only` 一起使用。
- **CON-003**：只抓 creator 为自己的歌单，包含“我喜欢的音乐”，排除订阅歌单。
- **CON-004**：排行不建投影表；周榜/总榜只写 raw。
- **CON-005**：新增 `pycryptodome` 运行时依赖；uid 默认从账号接口自动识别，`--uid` 仅作覆盖。
- **GUD-001**：复用 `export_runtime.http`、`db.raw`、`db.projections._upsert`；固定 endpoint 名和回放顺序；投影表使用 `STRICT`。
- **GUD-002**：中文文档、无 emoji、单文件小于 1000 行；新增非平凡逻辑必须有测试。

## 实施步骤

### 阶段 1：依赖、加密、客户端与凭证

完成标准：weapi 加密有已知向量测试；客户端能正确发出 6 类请求；凭证探针能识别未登录。

| Task     | Status  | Description | Verification Steps | Date |
| -------- | ------- | ----------- | ------------------ | ---- |
| TASK-001 | Completed | 在 `pyproject.toml` 增加 `pycryptodome` 并更新 `poetry.lock`；新增 `src/netease/__init__.py`、`src/netease/weapi.py`，实现 `aes_cbc_base64`、`rsa_encrypt`、`weapi_encrypt(payload, secret=None)`。 | `poetry lock`；`PYTHONPATH=src pytest tests/test_netease_weapi.py -q`；`ruff check src/netease tests/test_netease_weapi.py`；`ruff format --check src/netease tests/test_netease_weapi.py`。 | 2026-11-18 |

#### TASK-001 执行记录
- **状态**: 已完成（2026-11-18）
- **变更摘要**: 引入 `pycryptodome` 并实现 weapi 双层 AES + RSA 加密。
- **逻辑变更**:
  - **新增**: `src/netease/__init__.py`、`src/netease/weapi.py`（`aes_cbc_base64`、`rsa_encrypt`、`generate_secret`、`weapi_encrypt`）、`tests/test_netease_weapi.py`。
  - **修改**: `pyproject.toml` 增加 `pycryptodome (>=3.23.0,<5.0.0)`，`poetry.lock` 由 `poetry lock` 重新生成。
- **相关代码**: `netease.weapi.weapi_encrypt` 是客户端唯一的加密入口；RSA 仅做模幂，未引入 RSA 库。
- **验证结果**: `poetry lock` 成功；`tests/test_netease_weapi.py` 6 项通过；ruff check/format 通过。
| TASK-002 | Completed | 扩展 `export_runtime.http` 的可选 `request_meta`，写入 `sync_response.request.meta`；新增 `src/netease/api_endpoints.py`、`src/netease/client.py`，实现账号、歌单列表、歌单详情、歌曲详情、最近播放、周榜/总榜请求；账号请求不写 raw，其余走 `http.post`。 | `PYTHONPATH=src pytest tests/test_http_recorder.py tests/test_netease.py -q`；测试断言 endpoint、`data` 表单、`request_meta` 和账号不落 raw。 | 2026-11-18 |

#### TASK-002 执行记录
- **状态**: 已完成（2026-11-18）
- **变更摘要**: raw request 支持 `meta`，网易云客户端可发出账号与 6 类数据请求。
- **逻辑变更**:
  - **新增**: `src/netease/api_endpoints.py`（路径、endpoint 名、排行 type 映射）、`src/netease/client.py`（Cookie/Session、7 个方法、`NeteaseClientError`）、`tests/test_netease.py`。
  - **修改**: `src/export_runtime/http.py` 增加可选 `request_meta`，仅在传入时写入 `request.meta`，不改变已有平台的 request JSON；`tests/test_http_recorder.py` 覆盖 meta。
  - **修正**: weapi RSA 只应反转一次；TASK-001 的 `weapi_encrypt` 曾重复反转导致上游返回空 200，已修正并更新已知向量。
- **相关代码**: `NeteaseClient.get_account` 直接用 `session.post`，不落 raw；其余方法经 `export_runtime.http.post`。
- **验证结果**: `tests/test_http_recorder.py` + `tests/test_netease.py` 22 项通过；ruff check/format 通过；用仓库根目录 `cookies.txt` 实测账号、歌单、详情、歌曲、最近播放、周榜/总榜均返回 200。
| TASK-003 | Completed | 在 `src/app/credential_guard.py` 增加 `probe_netease_credentials`：账号 200 空对象判 invalid，301/401/403 判 invalid，非 JSON/非对象/请求异常判 unknown。 | `PYTHONPATH=src pytest tests/test_credential_guard.py -q`；覆盖 valid / empty / 301 / 401 / 非 JSON / 网络异常。 | 2026-11-18 |

#### TASK-003 执行记录
- **状态**: 已完成（2026-11-18）
- **变更摘要**: 新增网易云凭证探针，按账号接口判断登录态。
- **逻辑变更**:
  - **新增**: `probe_netease_credentials` 与 `_netease_identity`。
  - **修改**: `tests/test_credential_guard.py` 覆盖 account/profile 两种 uid、空账号、业务/HTTP 301/401/403、业务错误、非 JSON、网络异常、缺域 Cookie、配置缺失。
- **相关代码**: 探针只调用 `NeteaseClient.get_account`；`MUSIC_A_T`/`MUSIC_R_T` 等 Cookie 不作为判断依据。
- **验证结果**: `tests/test_credential_guard.py` 66 项通过；ruff check/format 通过。

### 阶段 2：抓取流程与 CLI

完成标准：`eto --db-only netease` 能把 6 类响应写入 raw；不改投影；失败路径标记 partial。

| Task     | Status  | Description | Verification Steps | Date |
| -------- | ------- | ----------- | ------------------ | ---- |
| TASK-004 | Completed | 新增 `src/netease/exporter.py`：歌单列表分页（limit=1000，最多 20 页）、只保留 creator 为自己的歌单、按 `trackCount` / `trackUpdateTime` / `detailResponseId` 剪枝、`--force` 绕过、歌曲详情每批 500、历史 100 条、周榜/总榜各 1000 条；按资源粒度标记 partial。 | `PYTHONPATH=src pytest tests/test_netease.py -q`；用 fake 客户端断言调用顺序、分批、剪枝、429/HTTP/code 错误的 partial 行为。 | 2026-11-18 |

#### TASK-004 执行记录
- **状态**: 已完成（2026-11-18）
- **变更摘要**: 新增网易云抓取编排，覆盖歌单分页、详情剪枝、歌曲分批、历史与排行。
- **逻辑变更**:
  - **新增**: `src/netease/exporter.py`（`sync`、分页/剪枝/批量/partial/429 停止）与对应 fake 客户端测试。
  - **修改**: 无。
  - **说明**: 剪枝状态通过 `_playlist_states()` 懒加载 `db.projections.netease.playlist_state`，投影模块在 TASK-008 落地；`--force` 时不查询投影。
- **相关代码**: `sync` 先校验账号 uid，再按“歌单列表 → 详情/歌曲 → 最近播放 → 周榜/总榜”顺序抓取；HTTP 429 抛 `_RateLimited` 终止本轮。
- **验证结果**: `tests/test_netease.py` 25 项通过；ruff check/format 通过。
| TASK-005 | Completed | 在 `src/app/cli.py` 增加 `netease` 子命令：非 `--db-only` 报 `UsageError`；`--uid` / `-u` 可选；`--force`；通过 `run_with_credential_guard` 和 `run_action('netease', 'sync', None, ...)` 执行。 | `PYTHONPATH=src pytest tests/test_cli_db.py tests/test_netease.py -q`；`CliRunner` 断言非 db-only 退出码、uid 传参、force 传参、run 行 platform/operation。 | 2026-11-18 |

#### TASK-005 执行记录
- **状态**: 已完成（2026-11-18）
- **变更摘要**: 新增 `eto --db-only netease` 子命令并接入凭证探针与 sync_run。
- **逻辑变更**:
  - **新增**: `netease` click 子命令（`--uid/-u`、`--force`）。
  - **修改**: `src/app/cli.py` 导入 `probe_netease_credentials` 与 `netease.exporter.sync`；`tests/test_cli_db.py` 增加非 db-only 拒绝、uid/force 透传、run 行断言。
- **相关代码**: `run_action('netease', 'sync', None, ...)`；v1 无 Markdown/索引输出。
- **验证结果**: `tests/test_cli_db.py` + `tests/test_netease.py` 94 项通过；ruff check/format 通过。
| TASK-006 | Completed | 补齐 exporter 与 CLI 测试：账号 uid 自动识别、`--uid` 不一致拒绝、空账号报错、单个歌单失败后继续、历史/排行失败不影响其他数据。 | `PYTHONPATH=src pytest tests/test_netease.py tests/test_cli_db.py -q`；断言失败路径 `sync_run.status='partial'` 或命令非零退出。 | 2026-11-18 |

#### TASK-006 执行记录
- **状态**: 已完成（2026-11-18）
- **变更摘要**: 补齐账号校验失败、uid 不一致、空账号与 partial 传播的 exporter/CLI 测试。
- **逻辑变更**:
  - **新增**: `profile.userId` 回退、uid 不一致不发起数据请求、空账号报错、账号 HTTP/业务错误测试；CLI 层 uid 不一致/空账号 `failed`、资源失败 `partial` 测试。
  - **修改**: `tests/test_netease.py` 的 fake 客户端支持账号异常；`tests/test_cli_db.py` 增加三条 CLI 失败路径。
- **相关代码**: `netease.exporter.sync`、`app.cli.netease`、`app.context.run_action`。
- **验证结果**: `tests/test_netease.py` + `tests/test_cli_db.py` 102 项通过；ruff check/format 通过。

### 阶段 3：迁移与投影

完成标准：4 张投影表可重建；自建歌单过滤、成员替换、占位歌曲、历史去重、幂等全部有测试。

| Task     | Status  | Description | Verification Steps | Date |
| -------- | ------- | ----------- | ------------------ | ---- |
| TASK-007 | Completed | 新增 `src/db/migrations/004_netease.sql`：4 张 `STRICT` 表和 4 个索引；更新 `tests/test_db_schema.py` 的 `user_version` 到 4；更新 `tests/test_projection_schema.py` 的表、索引、平台时间列集合。 | `PYTHONPATH=src pytest tests/test_db_schema.py tests/test_projection_schema.py -q`；断言 4 张表、4 个索引、JSON/STRICT/外键约束。 | 2026-11-18 |

#### TASK-007 执行记录
- **状态**: 已完成（2026-11-18）
- **变更摘要**: 新增网易云 4 张投影表与 4 个索引，迁移版本升到 4。
- **逻辑变更**:
  - **新增**: `src/db/migrations/004_netease.sql`；`test_projection_schema.py` 增加 JSON、关系外键与历史表不引用歌曲库的约束测试。
  - **修改**: 两个 schema 测试的 `user_version` 断言 3 → 4；投影表/索引/平台时间列集合纳入网易云。
- **相关代码**: `netease_playlist`、`netease_song`、`netease_playlist_song`、`netease_play_record`。
- **验证结果**: `tests/test_db_schema.py` + `tests/test_projection_schema.py` 19 项通过；ruff check/format 通过。
| TASK-008 | Completed | 新增 `src/db/projections/netease.py`：按固定顺序回放 4 类响应；歌单列表按 `request.meta.uid` 过滤；详情替换成员并插占位歌曲；歌曲详情 upsert；历史按 `(song_id, play_time)` upsert；实现 `playlist_state` 供导出器剪枝；在 `src/db/projections/__init__.py` 注册 `netease`。 | `PYTHONPATH=src pytest tests/test_projection_netease.py -q`；覆盖只保留自建歌单、成员替换、空歌单、占位、历史去重、301 回滚、坏辅助响应跳过、两次重建幂等。 | 2026-11-18 |

#### TASK-008 执行记录
- **状态**: 已完成（2026-11-18）
- **变更摘要**: 新增网易云投影解析器并注册平台，支持剪枝状态查询。
- **逻辑变更**:
  - **新增**: `src/db/projections/netease.py`（4 类响应回放、自建歌单过滤、成员替换、占位歌曲、历史去重、`playlist_state`）、`tests/test_projection_netease.py`。
  - **修改**: `src/db/projections/__init__.py` 注册 `netease`。
  - **边界**: 详情 `trackIds` 缺失/非法时在删除成员前拒绝，保留旧成员；空列表才清空成员。
- **相关代码**: `rebuild`、`_upsert_playlists`、`_replace_members`、`_upsert_songs`、`_upsert_recent`、`playlist_state`。
- **验证结果**: `tests/test_projection_netease.py` 13 项通过；相关投影/ schema 测试 38 项通过；ruff check/format 通过。
| TASK-009 | Pending | 补 `db rebuild netease` 测试与 raw endpoint 测试：`SUPPORTED_PLATFORMS` 包含 `netease`；`rebuild_platform` 调用新解析器；6 个 endpoint 通过 `http.post` 记录。 | `PYTHONPATH=src pytest tests/test_cli_db.py tests/test_raw_platforms.py tests/test_projection_base.py -q`；断言重建命令、endpoint 名称和 raw 行。 | |

### 阶段 4：文档与最终验证

完成标准：文档与实现一致；全量测试、ruff 通过；有有效 Cookie 时完成手工端到端验证。

| Task     | Status  | Description | Verification Steps | Date |
| -------- | ------- | ----------- | ------------------ | ---- |
| TASK-010 | Pending | 更新 `docs/design/projection-layer.md`：增加网易云 4 张表、回放/删除顺序、1-3 张表预算的例外说明；新增 `docs/usages/netease.md`；更新 `docs/usages/README.md`、`docs/usages/db.md`、`README.md`、`AGENTS.md`。 | 人工核对文档中的表名、endpoint、命令和 raw 排行查询示例；`grep -R "netease" docs README.md AGENTS.md` 无遗漏。 | |
| TASK-011 | Pending | 全量验证：运行测试、lint、format；用有效 `MUSIC_U` 手工执行 `eto --db-only netease`，检查 4 张表和 raw 排行；连续执行两次 `eto db rebuild netease` 验证幂等。 | `PYTHONPATH=src pytest tests -q`；`ruff check src tests`；`ruff format --check src tests`；手工命令见 `docs/usages/netease.md`。 | |

## 涉及文件

- **FILE-001**：`pyproject.toml`、`poetry.lock` — 新增 `pycryptodome`。
- **FILE-002**：`src/netease/__init__.py`、`src/netease/weapi.py` — weapi 加密。
- **FILE-003**：`src/netease/api_endpoints.py` — 上游路径和常量。
- **FILE-004**：`src/netease/client.py` — Cookie、Session、6 类请求、账号探针复用。
- **FILE-005**：`src/netease/exporter.py` — 抓取编排、剪枝、partial。
- **FILE-006**：`src/export_runtime/http.py` — `request_meta`。
- **FILE-007**：`src/app/credential_guard.py` — `probe_netease_credentials`。
- **FILE-008**：`src/app/cli.py` — `netease` 子命令。
- **FILE-009**：`src/db/migrations/004_netease.sql` — 4 张表。
- **FILE-010**：`src/db/projections/netease.py` — 投影解析器。
- **FILE-011**：`src/db/projections/__init__.py` — 注册平台。
- **FILE-012**：`tests/test_netease_weapi.py`、`tests/test_netease.py`、`tests/test_projection_netease.py`、`tests/test_http_recorder.py`、`tests/test_credential_guard.py`、`tests/test_db_schema.py`、`tests/test_projection_schema.py`、`tests/test_projection_base.py`、`tests/test_cli_db.py`、`tests/test_raw_platforms.py` — 测试。
- **FILE-013**：`docs/design/projection-layer.md`、`docs/usages/netease.md`、`docs/usages/README.md`、`docs/usages/db.md`、`README.md`、`AGENTS.md` — 文档。

## 测试与验证

- **TEST-001**：`PYTHONPATH=src pytest tests/test_netease_weapi.py -q`；固定 payload + 固定 secret 的已知向量；AES 两层解密 round-trip。
- **TEST-002**：`PYTHONPATH=src pytest tests/test_http_recorder.py tests/test_netease.py -q`；`request_meta` 记录、账号不落 raw、6 个 endpoint 正确。
- **TEST-003**：`PYTHONPATH=src pytest tests/test_db_schema.py tests/test_projection_schema.py -q`；`user_version=4`、4 张表、4 个索引、STRICT/JSON/外键。
- **TEST-004**：`PYTHONPATH=src pytest tests/test_projection_netease.py -q`；自建歌单过滤、成员替换、占位、历史去重、301 回滚、坏响应跳过、幂等。
- **TEST-005**：`PYTHONPATH=src pytest tests/test_cli_db.py tests/test_projection_base.py tests/test_raw_platforms.py -q`；`db rebuild netease` 与平台注册。
- **TEST-006**：`PYTHONPATH=src pytest tests -q`；全量回归。
- **TEST-007**：`ruff check src tests`、`ruff format --check src tests`。
- **TEST-008**：有效 `MUSIC_U` 下手工执行：
  ```shell
  eto --db-only netease
  eto --db-only netease --force
  eto db rebuild netease
  eto db rebuild netease
  ```
  检查 `netease_playlist`、`netease_song`、`netease_playlist_song`、`netease_play_record` 和 raw 中的 `netease.play.rank.week` / `netease.play.rank.all`。

## 风险与遗留

- **RISK-001**：完整历史不可得；测试只能验证“从首次同步开始累积”，不能验证历史回填。
- **RISK-002**：当前本地 `cookies.txt` 的 `MUSIC_U` 未登录；TASK-011 的端到端验证需要先重新导出 Cookie。
- **RISK-003**：weapi 常量或上游路径变化会导致请求失败，需要维护 `weapi.py` / `api_endpoints.py`。
- **RISK-004**：大歌单会触发多次歌曲详情请求；429 时本轮停止，下一轮补。
- **RISK-005**：排行只在 raw 层，查询需要 Python 解压 `sync_response.body`；后续可以按需增加只读查询命令。
- **RISK-006**：不做删除检测；旧歌单、旧成员、旧历史行会保留。
- **RISK-007**：`request_meta` 改变 raw request JSON 的结构，旧消费方必须忽略未知键。
- **RISK-008**：`pycryptodome` 需要随包安装；如果目标环境无法安装，需要退回 `cryptography` 或纯 Python AES。
