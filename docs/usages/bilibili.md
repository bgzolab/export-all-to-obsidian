# bilibili

导出 Bilibili 收藏夹。

## 用法

```shell
eto [全局参数] bilibili -f FID -o OUTPUT [--force]
```

## 参数

| 参数 | 必需 | 说明 |
| --- | --- | --- |
| `-f`, `--fid` | 是 | 收藏夹 ID |
| `-o`, `--output` | 是 | 输出目录，不存在时会自动创建 |
| `--force` | 否 | 覆盖已存在的文件并继续导出 |

## 凭证

通过 `COOKIES` 或 `--cookies-file` 提供 `bilibili.com` 的 Cookie。导出前会做一次凭证验活。

## 输出

每个收藏视频写成一个 Markdown 文件，文件名格式为 `<bvid>-<title>.md`。文件带 front matter，正文包含 Bilibili 播放器 iframe。

```text
OUTPUT/
└── <bvid>-<title>.md
```

已失效的视频仍会导出，并在正文顶部提示可尝试的缓存站点。

## 增量

默认遇到已存在文件时，当前导出流程提前结束，本次同步标记为 `partial`。传入 `--force` 后会覆盖已有文件并继续导出。

## 示例

```shell
eto --index-file output/index/export-index.md \
  bilibili -f your-fav-id -o output/bilibili
```

强制重新导出：

```shell
eto bilibili -f your-fav-id -o output/bilibili --force
```

[返回命令索引](./README.md)
