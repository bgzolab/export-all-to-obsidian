---
title: 项目设计
created: 2026-04-30T20:58:38
modified: 2026-08-29T00:00:00
description: 当前设计动机与已知设计现实。命令契约、环境变量、增量行为见 AGENTS.md。
tags:
  - ai-notes
---

CLI 契约、环境变量、增量行为与输出约定均已收敛到仓库根目录的 `AGENTS.md`，此处只保留设计动机与遗留问题。

## 设计动机

- 用简单 CLI 统一导出多平台收藏、点赞、稍后读、视频收藏到本地。
- 输出直接可被 Obsidian 使用；定期重复执行做增量同步，并生成合并索引。

## 已知设计现实

- 项目不是通用插件系统，新增平台仍需在 `src/app/cli.py` 手动注册 click 子命令，并显式注入 IndexWriter。
- 增量剪枝依赖“目标文件已存在”，而非远端游标持久化。
- 测试覆盖尚不完整，zhihu、weibo、bilibili 暂无独立测试文件。
- 文档分层：README（简单英文，面向用户）＋ docs/memories 与 AGENTS.md（中文内部记忆，面向后续对话）。