---
title: 项目架构
created: 2026-04-30T20:58:38
modified: 2026-08-29T00:00:00
description: 当前 export-to-obsidian 的实际结构与运行时数据流。基础约定见 AGENTS.md。
tags:
  - ai-notes
---

基础约定（目录、技术栈、开发命令）见仓库根目录的 `AGENTS.md`，此处只补充更细的架构信息。

## 运行时数据流

1. 用户执行 `eto` 顶层命令。
2. click 解析顶层参数与子命令。
3. `app.context` 创建 IndexWriter，并把 `--index-file` 配置注入根上下文。
4. `app.cli` 将 IndexWriter 显式注入对应平台 exporter。
5. Cookie 统一由 `app.cookies` 从 Netscape 格式 `cookies.txt`（`COOKIES` 环境变量或 `--cookies-file` 指定路径）按域名提取。
6. 每条数据转换为 WebPage 或 Video 前言加 Markdown 内容。
7. `export_runtime.exporter_support` 处理通用输出路径、增量剪枝、Markdown 写入与索引追加。
8. `utils.file_utils` 将内容写入 output 目录。
9. IndexWriter 将本轮导出条目打印到终端或写入一个 Markdown 索引文件。

## 关键模块职责

- `src/app/context.py`: 根上下文初始化与 IndexWriter 获取。
- `src/app/cookies.py`: 统一从 Netscape cookies.txt 按域名提取 Cookie 请求头。
- `src/export_runtime/index_writer.py`: 导出索引累计与落盘。
- `src/export_runtime/exporter_support.py`: 输出路径、增量剪枝、Markdown 写入、索引追加等轻量共用 helper。
- `src/<platform>/exporter.py`: 各平台导出编排。
- `src/utils`: 文件写入、Markdown 转换、模板渲染等通用能力。

## 输出模型

- 统一输出 Markdown 文件，文件名前缀由顶层 `--prefix` 控制（默认 `~`）。
- front matter 由 `utils.template` 与 `utils.md_utils` 生成。
- Bangumi 使用模板文件；Bilibili 输出 iframe 嵌入块；GitHub 使用模板并注入 README。

## 当前约束

- 已抽出轻量 exporter helper，但尚未引入 BaseExporter 一类更高层抽象。
- `bangumi.bangumi` 目前保留为历史兼容导入层。