---
name: recommend-courses
description: 根据学生自然语言选课需求，完成公选课个性化推荐（召回→硬约束过滤→重排→可行性检查→推荐理由）。当用户表达选课偏好、课程推荐需求时使用。
allowed_tools: [recommend_courses]
---

## Description
公选课个性化推荐：画像提取 → 召回 → 硬约束过滤 → 语义初筛 → 重排 → 可行性 → 推荐理由。支持一键（pipeline，最快）与原子工具（精细控制）两条路径。

## Trigger
用户表达选课偏好、课程推荐需求（如"推荐几门不用考试的课""有没有作业少的公选课"）时激活。

## Architecture（按序加载）
1. Rules（先读边界，再行动）：
   - [Load Shared Rules: identity](../_shared/rules/identity.md)
   - [Load Shared Rules: facts](../_shared/rules/facts.md)
   - [Load Rules: boundaries](./rules/boundaries.md)
2. Commands（按用户需求选路径）：
   - [Load Command: recommend-oneclick](./commands/recommend-oneclick.md)
   - [Load Command: present-results](./commands/present-results.md)
   - [Load Command: atomic-control](./commands/atomic-control.md)
3. Scripts（编排序列示例，按需引用）：
   - [Load Script: pipeline-sequence](./scripts/pipeline-sequence.md)
