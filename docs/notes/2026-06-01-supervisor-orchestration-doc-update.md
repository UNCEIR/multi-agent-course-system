# 2026-06-01 supervisor-main-orchestration.md 增量更新

## 解决了什么问题

文档 `docs/supervisor-main-orchestration.md` 在 5/23-5/28 迭代后有多处描述与代码不一致，需要增量更新以反映真实代码状态。

## 改动内容

1. **新增 §13.5 Phase 1.75 LLM 语义初筛**：记录 `_llm_semantic_filter` 触发条件（profile 存在 + 候选 >40）、摘要拼接方式、LLM 参数、失败回退策略。
2. **更新 §11.1 召回初始分公式**：`_score_candidates()` 已移除 profile 匹配逻辑（domain/category/campus/workload/exam/grade_friendly），仅保留 query term 和 popularity 加分；补充 Milvus COSINE 距离初始化公式。
3. **更新 §14.2 规则排序公式**：替换为 `_compute_score(course, profile)` 的完整规则表，包含 `final = profile_score * (1.0 + milvus_sim * 0.5)` 公式和 LLM 重排前预过滤说明。
4. **新增 §15.5 LLM 个性化抢课建议**：记录 `_llm_priority_advice` 的 12 门阈值、LLM 参数、返回结构 `PriorityAdvice(advice, priority)`、规则 fallback、静默失败行为和数据流路径。
5. **更新 §19 流式事件序列**：补充 Phase 1.75 不产生独立事件的说明。
6. **新增 §23 ReAct 编排分支**：记录触发条件、`_react_recommend()` 执行流程、7 工具表、硬约束不可跳过的锁死机制、ReAct vs Pipeline 的正常/异常路径差异和 token 增量。

## 测试

- ReadLints 检查无 linter 错误
- Grep 验证所有章节标题结构正确（§1-§23 + §13.5）

## 经验

- 增量更新大型 Markdown 文档时，用精确的上下文 anchor 做 StrReplace 比重写整段更安全
- 文档中的打分逻辑需要与代码严格对齐，两阶段评分职责分离（召回负责广度、重排负责精度）是设计决定，文档要明确标注
