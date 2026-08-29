---
title: 技术栈与规范
created: 2026-04-30T20:58:38
modified: 2026-08-29T00:00:00
description: 当前技术栈与开发命令。与 AGENTS.md 重合处优先以 AGENTS.md 为准。
tags:
  - ai-notes
---

技术栈、开发命令、代码约定、CLI 契约与测试现状均已收敛到仓库根目录的 `AGENTS.md`。本文件仅记录 AGENTS.md 之外的补充约定。

## 补充约定

- 源码目录固定为 `src`，测试目录固定为 `tests`。
- 推荐优先保持最小改动，不做无关重构。
- 当前 CLI 已明确使用 click，后续命令改造默认沿用 click。
- Markdown 记忆文档均带 YAML front matter。