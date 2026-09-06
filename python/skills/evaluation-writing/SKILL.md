---
name: evaluation-writing
description: 根据学生成绩数据（知识库成绩单，user 分区隔离）生成个性化学业评价（雷达图评价体系 + 评语），教师端生成后同步学生端。当需要生成评语、教师寄语、学业评价时使用。 何时不用：仅查成绩数值时请用 knowledge-query（query_transcript）；评语生成是教师端专属，学生端不触发。
allowed_tools: [get_academic_snapshot, design_dimensions, compute_radar_values, generate_comment]
---

## Description
教师端学业评价生成：以知识库成绩单为数据基准 → 五层反幻觉管线（快照→维度提案→雷达数值→评语核验→兜底）→ 落库同步学生端。

## Trigger
教师为指定学生生成评语/寄语/学业评价时激活。

## Architecture（按序加载）
1. Rules（先读边界，再行动）：
   - [Load Shared Rules: identity](../_shared/rules/identity.md)
   - [Load Shared Rules: facts](../_shared/rules/facts.md)
   - [Load Shared Rules: fallback](../_shared/rules/fallback.md)
   - [Load Rules: anti-hallucination](./rules/anti-hallucination.md)
2. Commands（按流程执行）：
   - [Load Command: five-layer-pipeline](./commands/five-layer-pipeline.md)
   - [Load Command: comment-types](./commands/comment-types.md)
3. Scripts（编排序列示例，按需引用）：
   - [Load Script: pipeline-sequence](./scripts/pipeline-sequence.md)
