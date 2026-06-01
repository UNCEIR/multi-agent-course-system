# 2026-06-01 architecture.md 面试文档重写

## 本次解决的问题

`docs/architecture.md` 作为面试架构讲解主文档，内容滞后于 5/23-5/28 四轮迭代后的代码状态。具体缺失：

1. Phase 1.75 LLM 语义初筛在 mermaid 图和编排流程中完全缺失
2. ReAct 双模式编排未体现，A/B 实验分流逻辑未说明
3. CourseFeasibilityAgent 描述仍是"纯规则逻辑，不依赖 LLM"，与实际的 LLM priority_advice 不符
4. 召回和重排的评分职责分离（5/23 重大改动）未记录
5. Redis 语义缓存误命中修复（阈值 0.9→0.95）未记录
6. 降级表缺少语义初筛失败、FeasibilityAgent LLM 静默回退、ReAct 硬约束强制补调等条目
7. 已知限制中缺少 ReAct group 未注册、treatment_llm config 未传入、LangGraph 版本功能差异等

## 方案

完整重写 `docs/architecture.md`，从业务问题出发，覆盖 AI Agent / 后端工程 / 推荐系统三个面试方向。

### 总体架构变更

- mermaid 图新增 A/B 分组节点，Pipeline 和 ReAct 分两个 subgraph
- Pipeline 子图包含 Phase 1→1.5→1.75→2→3 完整流程
- ReAct 子图展示 7 个工具 + 10 轮限制 + 硬约束锁死
- FeasibilityAgent 标注 LLM priority_advice 输出

### 新增章节

- **双模式编排**（第 5 章）：Pipeline vs ReAct 对比表、7 个工具矩阵、硬约束强制补调机制
- **评分职责分离**（第 7 章）：召回 `_score_candidates` 和重排 `_compute_score` 的具体打分规则和公式
- **语义缓存误命中修复**：嵌入 Redis 章节，说明问题、修复和效果

### 更新内容

- Agent 职责矩阵：CourseFeasibilityAgent 更新为 LLM + 规则双路径、CourseRerankAgent 补充 _compute_score
- 降级表：新增 4 个风险点
- 已知限制：新增 4 条
- 可追问点：新增 4 个高价值面试问题

## 测试

- ReadLints 检查 `docs/architecture.md`：无 linter 错误
- 逐项对照代码验证：
  - `supervisor.py` 确认 Phase 1.75 触发条件（候选>40 且有画像）
  - `ab_test.py` 确认只注册了 control/treatment_llm，无 react group
  - `course_rerank_agent.py:165` 确认 `_compute_score` 公式
  - `course_recall_agent.py:404` 确认 `_score_candidates` 只用关键词匹配+热度
  - `settings.py:41` 确认 `course_recall_cache_semantic_threshold=0.95`
  - `course_recall_cache_repository.py:77` 确认 prompt 始终纳入 payload
  - `react_tools.py` 确认 7 个工具定义
  - `course_feasibility_agent.py:47` 确认 LLM 调用存在

## 经验

1. 面试文档和代码的同步是持续问题——每次迭代改了代码后应该同步检查文档
2. 重写时需要逐个验证代码状态，不能只靠 AGENTS.md 的描述，因为 AGENTS.md 本身也可能滞后
3. mermaid 图的 subgraph 嵌套对可读性影响很大，需要在复杂度和信息量之间平衡
