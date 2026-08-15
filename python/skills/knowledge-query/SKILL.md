---
name: knowledge-query
description: 基于知识库（学生手册、学校规章、个人成绩单）回答学生关于大学校园生活、规章制度和个人学业的问题。当用户查询学校制度、管理规定、个人学业成绩时使用。
allowed_tools: [query_knowledge]
---

## Description
知识库问答：学生手册（public 分区）+ 个人成绩单（user 分区）检索 → 引用来源作答。

## Trigger
用户查询学校制度/管理规定/校园生活/个人学业成绩时激活。触发关键词：制度/手册/转专业/奖学金/宿舍/学分/毕业条件/某科成绩/修过哪些课。

## Architecture（按序加载）
1. Rules（先读边界，再行动）：
   - [Load Shared Rules: identity](../_shared/rules/identity.md)
   - [Load Shared Rules: grounding](../_shared/rules/grounding.md)
   - [Load Rules: knowledge-boundary](./rules/knowledge-boundary.md)
2. Commands（执行流程）：
   - [Load Command: answer-from-kb](./commands/answer-from-kb.md)
3. Scripts（调用示例，按需引用）：
   - [Load Script: query-example](./scripts/query-example.md)
