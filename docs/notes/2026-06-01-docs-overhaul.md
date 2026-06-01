# 2026-06-01 面试文档全量优化

## 背景与问题

- 本轮要解决的问题：`docs/` 下 8 个面试/架构文档写于 5/20 左右，之后项目经历了 4 轮重大迭代（5/23 召回-重排评分分离、5/25 LLM 参与度审视、5/26 P0-P1-A 五步改造、5/28 类别模糊匹配修复），但文档从未同步更新。
- 触发原因：准备面试实习，需要项目文档能准确反映当前架构和代码状态，能应对 AI Agent / 后端工程 / 推荐系统三个方向的拷打。
- 影响范围：`docs/` 下全部 8 个 `.md` 文件 + `INDEX.md`，不动 `docs/notes/`。

## 总体架构方案

- 保留 8 个文件的分工不变（INDEX / interview-guide / star-stories / question-bank / resume-template / architecture / code-walkthrough / supervisor-main-orchestration）
- 核心叙事从"电商迁移到公选课"升级为"规则保下限、LLM 提上限 + Pipeline/ReAct 双模式编排"
- 淡化电商背景（一句话带过），三个面试方向按岗位可切换侧重

## 细节实现

### 更新的关键文件

| 文件 | 更新类型 | 主要变化 |
|---|---|---|
| `architecture.md` | 完整重写 | mermaid 图补 A/B+Phase 1.75+ReAct；新增双模式编排和评分职责分离章节；Agent 矩阵更新 FeasibilityAgent LLM 化；Redis 补语义缓存修复；降级表+限制+追问点各新增 4 条 |
| `code-walkthrough.md` | 大幅更新 | 新增 ReAct 工具编排和流式 Token 解析两节；Supervisor 补 _react_recommend 和 _llm_semantic_filter；召回补 embedding 3→1 次和 search 返回格式；重排补 _compute_score；可行性补 _llm_priority_advice；测试更新为 39 passed；总计 20 节 |
| `supervisor-main-orchestration.md` | 增量更新 | 新增 §13.5 Phase 1.75；更新 §11.1 召回打分（移除 profile）；更新 §14.2 重排公式；新增 §15.5 LLM 抢课建议；新增 §23 ReAct 编排分支 |
| `interview-star-stories.md` | 完整重写 | 从 5 个故事替换为 8 个，按面试价值排序；删除"电商迁移"故事，新增 ReAct 双模式、评分分离、语义缓存修复、LLM 语义初筛、embedding 优化等 |
| `interview-question-bank.md` | 增量更新 | 更新 Q3/Q4/Q5；新增 Q19-Q28 共 10 题，覆盖 ReAct/语义缓存/评分/embedding/priority_advice/类别匹配 |
| `resume-template.md` | 完整重写 | 三个方向 bullet 全部重写；60s 和 3min 口播模板全面更新；边界补充 ReAct/语义缓存/embedding 优化 |
| `interview-guide.md` | 完整重写 | 主叙事升级为 Pipeline+ReAct 双模式；新增"按岗位切换侧重"章节；淡化电商背景 |
| `INDEX.md` | 增量更新 | 主线表补充 supervisor-main-orchestration.md；统一口径更新；阅读路径补充 |

### 核心逻辑

- 所有文档内容与 `python/` 代码交叉验证，代码路径和方法名与源码一致
- STAR 故事遵循 interview-star-packaging 技能规范：先讲为什么再讲做了什么，每个 R 主动暴露一个遗憾
- 不编造未验证指标，未知数据标"待补充"

## Debug 结论

- 根因：文档在 5/20 集中重构后未跟随 5/23-5/28 的代码迭代更新
- 排查过程：对比 `docs/notes/` 26 篇日记与 8 个文档的内容差异，识别出 4 轮迭代的缺失内容
- 解决方式：并行启动 7 个子代理 + 1 个直接编辑，按依赖顺序更新

## 测试与验证

- 已执行：每个文件更新后 ReadLints 检查，均无 Markdown 错误
- 已执行：代码路径与 `python/` 源码交叉验证（子代理内完成）
- 未执行：未运行 pytest 或 Docker（本轮只改文档）
- 未执行：未做文档间 Markdown 链接解析（当前文档主要用代码样式路径引用）

## 经验与后续

- 本轮经验：文档与代码应同步更新，每次重大代码迭代后应检查面试文档是否需要同步
- 本轮经验：并行子代理可以大幅加速文档更新（7 个子代理并行 ~10 分钟完成 8 个文件）
- 后续建议：可以考虑在 `tasks/lessons.md` 中加一条"每次 P0/P1 级改动后检查 docs/ 是否同步"
- 后续建议：ReAct 模式 A/B 注册后应同步更新 resume-template 和 interview-guide 中的"不要写"清单
