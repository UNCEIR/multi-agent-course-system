---
name: ppt-generation
description: 根据课程内容或主题，自动生成 PPT 课件（期末PPT课设/小组汇报/课堂展示等类型），多 agent 协作。当用户需要生成 PPT、课件、汇报材料时使用。 何时不用：简单问答或短文写作请用 writing 或直接对话；PPT 生成是多 agent 重任务，别当通用问答用。
allowed_tools: [web_search]
---

## Description
PPT 微课件自动生成系统（多 agent 协作）：提示词 → 课件结构 → DSL → PPTX 渲染，支持期末 PPT 课设/小组汇报类型。

## Trigger
用户需要生成 PPT/课件/汇报材料时激活。触发关键词：PPT/课件/汇报/演示文稿。

## Architecture（按序加载）
1. Rules（先读边界，再行动）：
   - [Load Shared Rules: fallback](../_shared/rules/fallback.md)
   - [Load Rules: scope](./rules/scope.md)
2. Commands（执行流程）：
   - [Load Command: plan-outline](./commands/plan-outline.md)
3. Scripts（占位）：
   - [Load Script: phase3-placeholder](./scripts/phase3-placeholder.md)

> Phase 3 实装：本 skill 当前为目录骨架，能力待 `ppt_generate` 系统落地后填充。
