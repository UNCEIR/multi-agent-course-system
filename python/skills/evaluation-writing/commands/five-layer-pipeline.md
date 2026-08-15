# Command: five-layer-pipeline（五层反幻觉管线）

## Steps（端点直管，按层顺序执行）
1. 层① `get_academic_snapshot`：确定性直查成绩单结构化数据（课程/学分/成绩 + 派生统计）。
2. 层② `design_dimensions`：LLM 提案 5 个评价维度（Pydantic 硬校验 → 默认维度集降级）。
3. 层③ `compute_radar_values`：代码按 metric 枚举计算雷达数值（0-100 归一）。
4. 层④ `generate_comment`：LLM 生成评语 → 数值引用核验硬闸 → 规则化评语兜底。
5. 层⑤ 落库：`evaluation_records`（append 历史，status=generated|fallback）→ 学生端可读。

## 事件流（SSE）
`stage / radar / comment_token* / done / error`
