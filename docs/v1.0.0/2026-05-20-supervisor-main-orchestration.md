# 流式推荐接口编排说明复盘

## 背景与问题

- 本轮要解决的问题：把 `docs/supervisor-main-orchestration.md` 从“同步/流式共用主链路说明”纠偏为“流式推荐接口编排说明”，避免 Phase 3 混入老同步接口的一次性输出原理。
- 触发原因或用户诉求：用户指出主要想看流式接口的一系列编排，Phase 3 没必要同时交代原接口输出原理，要求只重构已有两个文档，不新建其他文件。
- 影响范围：仅修改 `docs/supervisor-main-orchestration.md` 和本 note；不新建文件，不修改业务代码，不提交 git commit。

## 总体架构方案

- 涉及模块：`python/main.py`、`python/orchestrator/supervisor.py`、`python/orchestrator/hard_constraint_filter.py`、`python/agents/` 下 5 个 Agent、`python/services/stream_token_markup_parser.py`、`python/orchestrator/graph.py`。
- 数据流或调用链：HTTP 请求从 `/api/v1/recommend/stream` 进入 FastAPI，`_recommend_stream_response()` 创建 `StreamingResponse`，`_sse_wrapper()` 消费 `SupervisorOrchestrator.stream_recommend()` 产生的事件，并输出 `text/event-stream`。
- 关键设计取舍：文档把同步接口降为边界对照，把重点放在流式链路的阶段事件、Phase 3 token 流、marker parser、`done` 聚合和错误事件上。

## 细节实现

- 修改或分析的关键文件：重构 `docs/supervisor-main-orchestration.md` 与本 note；本轮没有新增第三个文件。
- 核心逻辑：
  - 流式入口：`/api/v1/recommend/stream` 调用 `supervisor.stream_recommend(request)`，由 `_sse_wrapper()` 转成 SSE 帧。
  - Phase 1：画像与宽召回并行，先推送 `phase:start`，完成后推送 `phase1_complete`。
  - 画像后二次召回：画像成功时使用结构化字段补召回并按 `course_id` 去重合并。
  - Phase 1.5：`HardConstraintFilter` 在重排前确定性过滤硬约束，触发时推送 `phase15_complete`。
  - Phase 2：重排与可行性检查并行，完成后推送 `phase2_complete`。
  - Phase 3：只解释流式理由生成；使用 `[COURSE:course_id:course_name]` marker 与 `StreamTokenMarkupParser` 生成 `course_start`、`text`、`course_end`，并在最后 `done` 聚合结构化结果。
- 兼容性与风险控制：文档明确同步接口 `/api/v1/recommend` 不是本篇重点，LangGraph 只在 `/api/v1/recommend/graph` 作为展示接口；不把未执行的业务测试或未验证指标写成事实。

## Debug 结论

- 根因：上一版文档把“Supervisor 主链路总览”和“流式接口编排”写在一起，导致 Phase 3 同时解释同步 `run()` 和流式 `astream_reasons()`，不符合用户当前只看流式接口的阅读目标。
- 排查过程：先读取 `tasks/todo.md`，再复核 `docs/supervisor-main-orchestration.md`、本 note、`python/main.py` 流式入口、`SupervisorOrchestrator.stream_recommend()`、`RecommendationReasonAgent.astream_reasons()` 与 `StreamTokenMarkupParser`。
- 解决方式：把主文档标题、入口、Phase 3、事件序列、`done` 聚合、STAR 口播和自测清单统一改成流式视角；同步接口只保留一句边界说明。

## 测试与验证

- 已执行：待本轮编辑完成后检查两份文档的 Markdown 诊断。
- 结果：`docs/supervisor-main-orchestration.md` 和本 note 未发现 Markdown linter 问题；主文档已复查并移除展开版中残留的“同步接口返回 JSON 理由”表述。
- 未执行及原因：不运行业务测试；本轮只重构 Markdown 文档，没有改动 Python 业务代码。

## 经验与后续

- 本轮经验：当用户关注流式接口时，文档应围绕“事件什么时候发、Phase 3 为什么才开始 token、Parser 如何归属课程、`done` 如何收口”展开；同步接口只能做边界对照，不能喧宾夺主。
- 后续建议：如果后续继续优化文档，可以单独补一张流式时序图，展示 `start -> phase1_complete -> phase15_complete -> phase2_complete -> phase3_start -> course/text -> done`。

## 用户反馈后的二次重构

- 本轮追加问题：用户指出主文档仍然偏概念和话术，不需要 STAR、LangChain、同步老接口边界，而是要流式链路的全部工程细节，例如打分机制、数据转换、召回依据等。
- 处理方式：重写 `docs/supervisor-main-orchestration.md`，删除面试包装、框架边界、自测清单和老接口说明，改成流式接口工程细节文档。
- 重点补充：
  - 请求字段如何转换成 prompt。
  - 画像字段如何分为软偏好和硬约束。
  - Redis cache key、structured signature、语义缓存桶和余弦相似度复用逻辑。
  - MySQL 结构化召回依据、短 query 限制和初始排序。
  - Milvus chunk 向量召回如何从 `chunk_id` 映射回 `course_id`。
  - 候选合并、召回初始分 `_score_candidates()` 的具体加分项。
  - 二次画像召回与宽召回的区别。
  - Phase 1.5 硬过滤规则、稀疏 warning。
  - Phase 2 规则重排分、领域多样性、可行性 warning 和最终课程交集。
  - Phase 3 marker 协议、Parser 状态机、token 收集、超时与 `done` 事件。
- 验证结果：`ReadLints` 检查主文档无 Markdown 诊断；搜索确认主文档无 `STAR`、`LangChain`、`LangGraph`、`面试`、`报菜名`、`自测`、`老接口` 等残留表述。
- 未执行：未运行业务测试，因为本轮只重构 Markdown 文档，没有修改 Python 代码。
