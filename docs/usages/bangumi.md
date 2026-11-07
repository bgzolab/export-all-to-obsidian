# bangumi

导出 Bangumi 收藏。

## 用法

```shell
eto [全局参数] bangumi -t TEMPLATE -s SUBJECT_TYPE -o OUTPUT [-c COLLECTION_TYPE] [--force]
```

## 参数

| 参数 | 必需 | 说明 |
| --- | --- | --- |
| `-t`, `--template` | 是 | 模板文件路径，可使用仓库自带的 `config/template/bangumi.md` |
| `-s`, `--subject_type` | 是 | 主题类型，见下表 |
| `-o`, `--output` | 是 | 输出目录，不存在时会自动创建 |
| `-c`, `--collection_type` | 否 | 收藏类型；不传时导出全部 5 种收藏类型 |
| `--force` | 否 | 覆盖已存在的文件并继续导出 |

`-s` 取值：

| 值 | 类型 |
| --- | --- |
| `1` | 书籍 |
| `2` | 动画 |
| `3` | 音乐 |
| `4` | 游戏 |
| `6` | 三次元 |

`-c` 取值：

| 值 | 状态 |
| --- | --- |
| `1` | 想看 |
| `2` | 看过 |
| `3` | 在看 |
| `4` | 搁置 |
| `5` | 抛弃 |

## 凭证

需要环境变量 `BGM_ACCESS_TOKEN`。导出前会做一次凭证验活。

## 模板

模板由 `-t` 指定，没有内置默认路径。仓库自带示例：`config/template/bangumi.md`。

模板使用简单的字符串替换，支持以下占位符：

| 占位符 | 内容 |
| --- | --- |
| `{{aliases}}` | 别名列表 |
| `{{bangumi}}` | 条目 ID |
| `{{rating}}` | 评分 |
| `{{cover}}` | 封面 URL |
| `{{created}}` | 创建时间 |
| `{{modified}}` | 导出时间 |
| `{{tags}}` | 标签列表 |
| `{{title}}` | 标题 |
| `{{website}}` | 官方网站列表 |
| `{{summary}}` | 简介 |
| `{{characters}}` | 角色信息表格 |

列表字段会以 Python 列表字符串的形式替换，例如 `['bangumi/done', 'bangumi/anime']`。

## 输出

输出目录按条目的实际类型分子目录：

```text
OUTPUT/
├── book/
├── anime/
├── music/
├── game/
└── real/
```

文件名格式为 `<subject_id>-<title>.md`，例如 `OUTPUT/anime/123456-某部动画.md`。

## 增量

默认遇到已存在文件时，当前收藏类型的导出提前结束，本次同步标记为 `partial`。

传入 `--force` 后会覆盖已有文件并继续导出。不传 `-c` 时，各收藏类型依次导出；某个类型提前结束不会阻止后续类型继续。

## 示例

只导出一个收藏类型：

```shell
eto --index-file output/index/export-index.md \
  bangumi -t config/template/bangumi.md -s 2 -c 3 -o output/bangumi
```

导出某个主题类型下的全部收藏类型：

```shell
eto --index-file output/index/export-index.md \
  bangumi -t config/template/bangumi.md -s 1 -o output/bangumi
```

强制重新导出：

```shell
eto bangumi -t config/template/bangumi.md -s 2 -o output/bangumi --force
```

[返回命令索引](./README.md)
