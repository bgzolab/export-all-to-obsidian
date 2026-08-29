---
title: 项目架构
created: 2026-04-30T20:58:38
modified: 2026-05-12T00:00:00
description: 当前 export-to-obsidian 项目的实际结构、入口、模块边界与数据流摘要。
tags:
  - ai-notes
---

这是一个单仓库 Python CLI 工具，用来把多个平台的已保存内容导出为
Obsidian 友好的 Markdown 文件。

## 架构概览

- 薄 CLI 入口：src/export_to_obsidian.py -> src/app/cli.py
- 模块按平台拆分：bangumi、bilibili、cnblog、github、qireader、twitter、v2ex、weibo、zhihu
- 各平台导出编排位于各自 exporter.py
- 导出运行时对象位于 export_runtime
- 通用能力放在 utils、entity
- 输出目标是本地文件系统，不依赖数据库
- 文档与长期上下文放在 docs/memories

## 关键目录

- src: 业务代码
- src/export_to_obsidian.py: 兼容入口，只暴露 eto 和历史导出符号
- src/app/cli.py: click group、子命令与参数装配
- src/app/context.py: 根上下文初始化与 IndexWriter 获取
- src/export_runtime/index_writer.py: 导出索引累计与落盘
- src/export_runtime/exporter_support.py: 导出路径、增量剪枝、Markdown 写入、索引追加等轻量共用 helper
- src/<platform>/exporter.py: 各平台导出编排
- src/<platform>: 各平台客户端、拉取逻辑、内容转换逻辑
- src/utils: 文件写入、Markdown 转换、模板渲染等通用能力
- config/bangumi_template.md: Bangumi 导出模板
- tests: 当前测试集，覆盖 bangumi、cnblog、qireader、utils
- docs/implementation-plans: 功能计划与执行记录
- docs/memories: 提供给后续对话的稳定上下文
- output: 导出结果样例

## 运行时数据流

1. 用户执行 eto 顶层命令。
2. click 解析顶层参数与子命令。
3. app.context 创建 IndexWriter，并把 --index-file 配置注入根上下文。
4. app.cli 将 IndexWriter 显式注入对应平台 exporter。
5. 每条数据转换为 WebPage 或 Video 前言加 Markdown 内容。
6. export_runtime.exporter_support 处理通用输出路径、增量剪枝、Markdown 写入与索引追加。
7. utils.file_utils 将内容写入 output 目录。
8. IndexWriter 将本轮导出条目打印到终端或写入一个 Markdown 索引文件。

## 已实现命令边界

- cnblog: 导出博客园收藏
- bangumi: 导出 Bangumi 收藏，可按 subject_type 或 collection_type 过滤
- qireader: 导出稍后读列表
- twitter: 导出当前用户点赞 Tweet（X 网页 GraphQL Likes 接口，Cookie 鉴权）
- v2ex: 导出收藏主题
- zhihu: 导出收藏夹内容
- weibo: 导出点赞微博
- bilibili: 导出收藏夹视频
- github: 导出当前认证用户的 starred repositories

## 输出模型

- 统一输出 Markdown 文件
- 文件名前缀由顶层 `--prefix` 统一控制，默认值为 `~`
- front matter 由 utils.template 与 utils.md_utils 生成
- Bangumi 使用模板文件
- Bilibili 输出 iframe 嵌入块和基础说明
- GitHub 使用模板文件并注入 README 内容

## 当前约束

- 没有数据库，没有任务队列，没有服务端进程
- 主要是同步分页抓取，失败处理以跳过或提前结束为主
- 多个模块用“检测到已存在文件即结束同步”做增量剪枝
- 所有模块通过顶层 `--prefix` 共享统一文件名前缀配置
- 已抽出轻量 exporter helper，但尚未引入 BaseExporter 一类更高层抽象
- bangumi.bangumi 目前保留为历史兼容导入层

