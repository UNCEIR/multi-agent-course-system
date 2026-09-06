---
name: report-generation
description: 根据批量学科成绩 Excel（一科一文件），生成逐学生期末成绩报告单（PDF/HTML 下载链接 + LLM 综合评价）。当教师需要生成成绩单、期末报告、班级成绩汇总时使用。 何时不用：个人成绩查询请用 knowledge-query（query_transcript）；成绩单生成是教师端批量任务，勿当个人查询用。
allowed_tools: [inspect_score_excels, render_report_batch]
---

## Description
教师端批量成绩单生成：多科 Excel → 确定性解析合并 → 年级分类选模板 → 逐学生填表（LLM+Jinja2 降级）→ PDF/HTML 渲染 → token 下载链接 + 失败重试。

## Trigger
用户提供学科成绩 Excel（一科一文件）并要求生成成绩单/期末报告时激活。

## Architecture（按序加载）
1. Rules（先读边界，再行动）：
   - [Load Shared Rules: identity](../_shared/rules/identity.md)
   - [Load Shared Rules: facts](../_shared/rules/facts.md)
   - [Load Shared Rules: fallback](../_shared/rules/fallback.md)
   - [Load Rules: integrity](./rules/integrity.md)
2. Commands（按流程执行）：
   - [Load Command: inspect-classify](./commands/inspect-classify.md)
   - [Load Command: render-batch](./commands/render-batch.md)
   - [Load Command: retry-failed](./commands/retry-failed.md)
3. Scripts（编排序列示例，按需引用）：
   - [Load Script: batch-sequence](./scripts/batch-sequence.md)
