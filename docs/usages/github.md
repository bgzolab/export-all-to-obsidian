# github

导出当前认证用户的 GitHub stars。

## 用法

```shell
eto [全局参数] github -t TEMPLATE -o OUTPUT [--force]
```

## 参数

| 参数 | 必需 | 说明 |
| --- | --- | --- |
| `-t`, `--template` | 是 | 模板文件路径，可使用仓库自带的 `config/template/github.md` |
| `-o`, `--output` | 是 | 输出目录，不存在时会自动创建 |
| `--force` | 否 | 覆盖已存在的文件并继续导出 |

## 凭证

需要环境变量 `GITHUB_TOKEN`。该命令不执行凭证验活，也不会发送 Telegram 提醒；缺少令牌时会直接报错退出。

## 模板

模板由 `-t` 指定，没有内置默认路径。仓库自带示例：`config/template/github.md`。

模板使用 `{{变量}}` 替换，支持以下变量：

| 变量 | 内容 |
| --- | --- |
| `{{authors}}` | 仓库所有者 |
| `{{name}}` | 仓库名 |
| `{{owner_login}}` | 所有者登录名 |
| `{{full_name}}` | `owner/repo` |
| `{{description}}` | 仓库描述 |
| `{{url}}` | 仓库 URL |
| `{{readme}}` | 仓库 README 原文，缺失时为空 |
| `{{language}}` | 主语言 |
| `{{topics}}` | 主题列表，逗号分隔 |
| `{{stargazers_count}}` | star 数 |
| `{{forks_count}}` | fork 数 |
| `{{open_issues_count}}` | 打开 issue 数 |
| `{{fork}}` | 是否为 fork |
| `{{archived}}` | 是否已归档 |
| `{{private}}` | 是否私有 |
| `{{homepage}}` | 主页 |
| `{{license}}` | 许可证 |
| `{{created_time}}` | 仓库创建时间 |
| `{{updated_at}}` | 仓库更新时间 |
| `{{pushed_at}}` | 最近推送时间 |
| `{{starred_at}}` | star 时间 |
| `{{export_time}}` | 导出时间 |
| `{{repo_filename}}` | 导出文件名，含 `--prefix` |
| `{{prefix}}` | 当前文件名前缀 |

## 输出

每个 star 仓库写成一个 Markdown 文件，文件名格式为 `<prefix><owner>-<repo>.md`。不额外写入 front matter，模板决定文件内容。

```text
OUTPUT/
└── ~<owner>-<repo>.md
```

`--prefix` 同时影响文件名、`{{prefix}}` 和 `{{repo_filename}}`。使用 `--prefix ""` 可以关闭默认的 `~` 前缀。

## 增量

默认遇到已存在文件时，当前导出流程提前结束，本次同步标记为 `partial`。传入 `--force` 后会覆盖已有文件并继续导出。

## 示例

```shell
eto --index-file output/index/export-index.md \
  github -t config/template/github.md -o output/github
```

关闭文件名前缀：

```shell
eto --prefix "" github -t config/template/github.md -o output/github
```

强制重新导出：

```shell
eto github -t config/template/github.md -o output/github --force
```

[返回命令索引](./README.md)
