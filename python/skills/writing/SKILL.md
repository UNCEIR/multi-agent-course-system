---
name: writing
description: 辅助学生完成论文写作、报告撰写、方案设计等写作任务（多体裁/多风格，对话式协作）。当用户需要写作、论文、报告、读后感时使用。
allowed_tools: [writing_assistant]
---

## Description
对话式写作助手：多体裁（学术论文/读书报告/实习报告/课程设计/演讲稿/新闻稿/散文）成稿 + 迭代修改。

## Trigger
用户需要写作/论文/报告/读后感/演讲稿时激活。触发关键词：写/写一篇/帮我写/论文/报告/读后感/综述。

## Architecture（按序加载）
1. Rules（先读边界，再行动）：
   - [Load Shared Rules: facts](../_shared/rules/facts.md)
   - [Load Rules: no-fabrication](./rules/no-fabrication.md)
2. Commands（执行流程）：
   - [Load Command: request-confirm](./commands/request-confirm.md)
   - [Load Command: generate-iterate](./commands/generate-iterate.md)
3. Scripts（调用示例，按需引用）：
   - [Load Script: writing-example](./scripts/writing-example.md)
