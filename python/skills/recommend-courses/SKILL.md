---
name: recommend-courses
description: 根据学生自然语言选课需求，完成公选课个性化推荐（召回→硬约束过滤→重排→可行性检查→推荐理由）。当用户表达选课偏好、课程推荐需求时使用。
allowed_tools: [recommend_courses]
---

## 推荐课程流程

### 1. 识别触发场景

用户需求中出现以下关键词时调用本技能：

- 选课：想选、推荐、哪些课、选修、公选课
- 偏好：兴趣、不想考试、作业少、校区、时间冲突
- 组合：推荐 + 理由 + 可行性

### 2. 执行步骤

1. **调 `recommend_courses` tool**，传入：
   - `query`：学生的自然语言选课需求（原样传入）
   - `user_id`：用户 ID
   - `num_items`：推荐课程数量（默认 10）
2. **tool 内部自动执行**（`recommend_courses` 内部编排，无需手动分步调用）：
   - `extract_profile` → 提取学生画像 + 硬约束
   - `search_courses` → 宽召回（无画像）/ 精召回（有画像）
   - `filter_hard_constraints` → 确定性过滤（校区/类别/考试等）
   - `semantic_filter_courses` → LLM 语义初筛（候选 > 40 时）
   - `rerank_courses` → 画像偏好 + Milvus 语义融合重排
   - `check_feasibility` → 容量/风险检查
   - `generate_reasons` → 每门课推荐理由
   > 注：以上 7 个子工具是 `recommend_courses` tool 的内部编排流程，待 Phase 1 Step 3 实装后生效。当前 `recommend_courses` 为 stub 状态。
3. **向用户呈现结果**：
   - 推荐课程列表（课程名 + 推荐理由）
   - 若有 `warnings`（如候选不足、风险提示），一并说明
   - 如果召回太少（<5 门），提示用户放宽约束

### 3. 注意事项

- **filter_hard_constraints 不可跳过**：硬约束是确定性过滤，违反约束的课程绝不推荐
- **数值引用文件**：课程容量、人数等数值来自 MySQL 事实数据，不要凭记忆编造
- **失败兜底**：tool 失败时提示用户稍后重试，不返回空推荐