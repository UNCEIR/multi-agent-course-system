# 面试追问题库更新复盘（2026-06-01）

## 本次解决的问题

面试追问题库 `docs/interview-question-bank.md` 原有 18 题（Q1-Q18），覆盖了项目真实性、Multi-Agent 设计、数据召回、LLM 幻觉控制、硬约束、流式推荐和验证。但缺少 ReAct 双模式编排、LLM 语义初筛与评分公式、语义缓存优化、可行性 LLM 化等近期迭代的面试准备内容。

## 具体改动

### 更新已有题目（3 题）

- **Q3（Multi-Agent 必要性）**：补充"规则保下限、LLM 提上限"核心论述，引用 5/25 架构审视结论，说明纯 LLM 和纯规则各自的局限。
- **Q4（Supervisor 模式好处）**：补充与 ReAct 模式的对比，说明 Pipeline 和 ReAct 并存的原因及 A/B 路由机制。
- **Q5（Phase 1 并行）**：在边界中补充 wide + refined 双路召回如何缓解并行收益下降的问题。

### 新增题目（10 题，Q19-Q28）

| 章节 | 题目 | 核心考点 |
|---|---|---|
| 8. ReAct 编排与双模式 | Q19 Pipeline vs ReAct 适用场景 | 双模式并存设计 |
| | Q20 硬约束工具锁死机制 | ReactState.hard_filtered 强制补调 |
| 9. LLM 语义初筛与评分 | Q21 语义初筛失败退化 | 空列表不中断链路 |
| | Q22 为什么不全程 LLM | 成本与确定性权衡 |
| | Q23 _compute_score 公式 | 乘法放大器设计 |
| 10. 语义缓存与 Embedding 优化 | Q24 语义缓存误命中根因 | 1024 维句式区分度 |
| | Q25 阈值 0.95 选择 | 经验值边界 |
| | Q26 embedding 3→1 次优化 | query_embedding 参数透传 |
| 11. 可行性与前端 | Q27 priority_advice LLM 与规则 | 静默回退风险 |
| | Q28 类别模糊匹配修复 | category_rules 别名映射 |

### 自测清单补充

新增 3 项自测：Pipeline vs ReAct 区别、语义缓存误命中修复、评分职责分离变化。

## 验证

- ReadLints 检查编辑后的文件无 linter 错误。
- 所有证据字段均与源代码交叉验证：`_compute_score` 公式权重、`max_rounds = 10`、`ReactState.hard_filtered`、`course_recall_cache_semantic_threshold = 0.95`、`category_rules` 映射内容等均与代码一致。
- 未修改任何业务代码，仅编辑文档。

## 经验

- 面试题库的证据字段必须与代码交叉验证，不能凭记忆写。本次逐一 grep 了 `_compute_score`、`ReactState`、`_llm_semantic_filter`、`category_rules` 等关键实现，确保证据准确。
- 新增章节编号需要同步调整反向自测的章节号（原 `## 8. 反向自测` → `## 12. 反向自测`）。
