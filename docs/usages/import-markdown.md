# import-markdown

把已有 Markdown 文件原样导入 raw 数据库。

## 用法

```shell
eto [全局参数] import-markdown PATH
```

## 参数

| 参数 | 必需 | 说明 |
| --- | --- | --- |
| `PATH` | 是 | 要导入的目录；必须存在且是目录 |

## 行为

- 递归扫描 `PATH` 下所有 `*.md` 文件。
- 文件内容原样写入 SQLite 数据库，不修改原文件。
- 同一导入目录下，相对路径和文件内容的 SHA-256 都相同时视为已导入并跳过。
- 完成后打印导入数量、跳过数量和失败数量。

## 数据库

使用全局 `--db` 指定数据库，默认 `data/eto.db`。

```shell
eto --db ./data/eto.db import-markdown ./output
```

`--index-file`、`--prefix` 和 `--cookies-file` 对该命令没有作用。

## 示例

```shell
eto --db ./data/eto.db import-markdown ./output
```

输出示例：

```text
导入完成: 12 个，跳过 3 个，失败 0 个
```

该命令不执行凭证验活，也不会发送 Telegram 提醒。

[返回命令索引](./README.md)
