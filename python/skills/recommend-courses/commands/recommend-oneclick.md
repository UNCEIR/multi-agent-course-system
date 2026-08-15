# Command: recommend-oneclick（一键推荐，最快路径）

## Goal
对用户选课需求做端到端个性化推荐，延迟最低。

## Steps
1. 用用户原话构造 `query`（不转述、不丢弃约束条件）。
2. 调用 `recommend_courses` 工具：
   - `query`：选课需求原话
   - `num_items`：默认 6
   - `mode`：`pipeline`（并行编排）
3. 工具内部自动完成：画像 → 召回 → 硬约束 → 语义初筛 → 重排 → 可行性 → 推荐理由。
4. 不要手动分步调用原子工具（会显著变慢），除非需要精细控制。

## 参数契约
见 `../scripts/pipeline-sequence.md`。
