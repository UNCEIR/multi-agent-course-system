# Command: atomic-control（高级：原子工具精细控制）

## Goal
需要逐步控制推荐流程时的备选路径（默认不用）。

## Steps（严格按序，每工具一次）
1. `extract_profile`：学生画像
2. `search_courses`（wide → refined）：召回
3. `filter_hard_constraints`：确定性硬约束过滤（**不可跳过**）
4. `semantic_filter_courses`：语义初筛
5. `rerank_courses`：重排
6. `check_feasibility`：可行性（容量/冲突）
7. `generate_reasons`：推荐理由

## 注意
- 默认优先一键工具；原子路径仅当用户需要分步干预时使用。
