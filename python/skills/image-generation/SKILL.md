---
name: image-generation
description: 根据提示词生成图片（即梦 4.0，经自建 MCP server 两段式异步任务），产物转存后返回链接。当用户需要生成图片、配图、插画时使用。
allowed_tools: [image_generate, image_generate_get]
---

## Description
AI 图片生成（两段式链式调用）：提交任务（image_generate → task_id）→ 轮询查询（image_generate_get → done）→ 产物转存 MinIO/本地 → 返回持久化链接。

## Trigger
用户需要生成图片/配图/插画/海报时激活。触发关键词：生成图片/画一张/配图/插画/AI 绘图。

## Architecture（按序加载）
1. Rules（先读边界，再行动）：
   - [Load Shared Rules: fallback](../_shared/rules/fallback.md)
   - [Load Rules: no-fake](./rules/no-fake.md)
2. Commands（两段式流程）：
   - [Load Command: generate-deliver](./commands/generate-deliver.md)
   - [Load Command: poll-result](./commands/poll-result.md)
3. Scripts（调用契约，按需引用）：
   - [Load Script: two-phase-example](./scripts/two-phase-example.md)
