---
name: recommend-courses
description: 根据学生自然语言选课需求，完成公选课个性化推荐（召回→硬约束过滤→重排→可行性检查→推荐理由）。当用户表达选课偏好、课程推荐需求时使用。
allowed_tools: [recommend_courses]
---

## 推荐课程流程

### 0. 前置

- 当前用户 `user_id` 已由系统自动注入，**不要**向用户索要学号或猜测 user_id。
- 课程事实数据（容量、人数、考核方式）必须来自工具返回结果，不要凭记忆编造。

### 1. 一键推荐（推荐路径，最快）

**直接调用 `recommend_courses` 工具**，传入：

```json
{"query": "<学生选课需求原话>", "num_items": 6, "mode": "pipeline"}
```

- `mode=pipeline`：内部走并行编排（画像∥召回、重排∥可行性并行），延迟最低
- 工具内部自动完成：画像提取 → 召回 → 硬约束过滤 → 语义初筛 → 重排 → 可行性 → 推荐理由
- **不要**手动分步调用各原子工具（会显著变慢），除非需要精细控制

### 2. 呈现结果

- 向用户展示课程列表（课程名 + 推荐理由）
- 若有 `warnings`（候选不足、容量紧张、时间冲突），一并说明
- 若召回太少（<5 门），提示用户放宽约束

## 高级：原子工具（可选，精细控制）

如确实需要逐步控制，可依次调用以下工具（每工具一次，不要重复）：
`extract_profile` → `search_courses`(wide/refined) → `filter_hard_constraints` → `semantic_filter_courses` → `rerank_courses` → `check_feasibility` → `generate_reasons`

但**默认优先使用 `recommend_courses` 一键工具**（并行、快）。

## 注意事项

- **优先 `recommend_courses` 一键工具**（pipeline 模式并行最快）
- **filter_hard_constraints 不可跳过**：硬约束是确定性过滤，违反约束的课程绝不推荐
- **失败兜底**：工具失败时提示用户稍后重试，不返回空推荐
- **数值引用文件**：课程容量、人数等数值来自 MySQL 事实数据，不要凭记忆编造
