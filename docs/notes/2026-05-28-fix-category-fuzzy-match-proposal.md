# 2026-05-28 类别模糊匹配 Bug OpenSpec 提案

## 背景与问题

- 本轮要解决的问题：HardConstraintFilter 类别模糊匹配无法识别「理工类」「文科类」等口语表达，导致合规课程被误过滤。
- 触发原因或用户诉求：用户在 explore 后执行 `/opsx-propose`，要求先阐述 bug 再给出修复方案。
- 影响范围：硬约束过滤、prompt 硬约束提取、MySQL 结构化 refined recall；推荐结果可能为空或严重偏少。

## 总体架构方案

- 涉及模块：`hard_constraint_filter.py`、`student_profile_agent.py`、`course_repository.py`；新增 `services/category_normalization.py`。
- 数据流：

```
用户 prompt「理工类」
  → StudentProfileAgent 提取/归一化 → categories=["自然科学与工程技术类"]
  → CourseRecallAgent MySQL IN（归一化后命中）
  → HardConstraintFilter（归一化 + 子串 fuzzy 兜底）
```

- 关键设计取舍：别名表集中维护 + 保留现有 `_fuzzy_text_match` 子串逻辑，兼容已有「自然科学类」用例。

## 细节实现

- 修改或分析的关键文件（提案阶段，尚未改代码）：
  - `python/orchestrator/hard_constraint_filter.py:201` `_fuzzy_text_match`
  - `python/agents/student_profile_agent.py:190` `category_rules`
  - `python/repositories/course_repository.py` `fetch_courses` categories IN
- 核心逻辑：数据集仅两类 canonical；`"理工"` 不是 `"自然科学与工程技术"` 的子串，纯子串匹配必然失败。
- OpenSpec 变更目录：`openspec/changes/fix-category-fuzzy-match/`（proposal、design、specs、tasks 已齐）。

## Debug 结论

- 根因：用户/LLM 口语标签与 DB canonical 分类命名体系不一致；匹配层只有子串、无别名映射。
- 排查过程：阅读 AGENTS.md、hard_constraint_filter、student_profile_agent、course.csv 分类枚举、现有测试 `test_hard_constraint_filter_accepts_fuzzy_category_match`（仅覆盖「自然科学类」）。
- 解决方式（待 implement）：共享 `normalize_category()` + 扩展 prompt 关键词 + recall 入口归一化。

## 测试与验证

- 已执行：`openspec status --change fix-category-fuzzy-match`（4/4 artifacts complete）。
- 结果：提案制品完成，代码未改动。
- 未执行：`pytest`（实现阶段按 tasks.md 4.1/4.2 执行）。

## 经验与后续

- 本轮经验：子串 fuzzy 适合 partial 名称（自然科学↔自然科学与工程技术），不适合简称（理工↔全称）；别名表应单点维护。
- 后续建议：运行 `/opsx:apply` 或 `/opsx-apply` 按 tasks.md 实现并补测试。
