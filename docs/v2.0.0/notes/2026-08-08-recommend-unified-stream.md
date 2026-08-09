# 推荐接口收敛：统一流式入口（默认 ReAct → 兜底 Pipeline）

## 背景与问题

- v1 遗留 5 个推荐端点（同步 `/api/v1/recommend`、`/recommend/stream`、`/recommend/react`、`/recommend/react/stream`、`/recommend/graph`）职责重叠、同步/流式混用，前端体验不一致。
- AGENTS.md 要求前端 API 一律流式；v1 supervisor 的 `stream_recommend`（Pipeline）与 `react_stream_recommend`（ReAct）是分开的两条流式路径，没有"默认 ReAct、失败兜底 Pipeline"的合一版本。

## 总体架构方案

- **收敛入口**：只保留 `POST /api/v1/recommend/stream` 一个流式端点，删除其余 4 个。
- **编排策略**：默认走 ReAct 流式，流式中任一阶段失败自动切换到 Pipeline 流式继续输出，`done.experiment_group=pipeline_fallback` 标注降级。
- **同源工具**：`recommend_courses` 工具内部消费同一 `stream_recommend_unified` generator，与前端入口同源，保证 deepagents 调用与 API 结果一致。
- v1 `SupervisorOrchestrator` 保留为能力层；后续新智能体编排统一用 deepagents/LangGraph。

## 细节实现

- `python/agent/recommend/supervisor.py` 新增 `stream_recommend_unified(request)`：
  1. 先 `async for event in react_stream_recommend(request)`；遇 `error` 事件记录失败原因并 break。
  2. 失败则发 `react_fallback` 阶段事件，再 `async for event in stream_recommend(request)`。
  3. Pipeline 分支的 `done` 事件改写 `experiment_group=pipeline_fallback` 并附 `react_fallback` 详情。
- `python/api/recommend.py`：仅保留 `POST /api/v1/recommend/stream`，调用 `stream_recommend_unified`；`_sse_wrapper` 在 `done` 收 Agent 指标、`error` 记业务事件。
- `python/agent/runtime.py`：移除 `rec_graph` 单例与 `build_recommendation_graph()` 调用（graph 端点已删）。
- `python/tools/recommend/recommend_courses.py`：新增内部 generator `stream_recommend_courses`，`recommend_courses`（@tool）消费它聚合返回 JSON 字符串，错误事件转异常。
- 文档同步：`CLAUDE.md`/`README.md`/`docs/architecture.md` API 表、`tools/README.md`、`recommend_courses.md`。

## 测试与验证

- 新增 `test_stream_recommend_unified_react_fallback_pipeline`：mock ReAct 失败，断言事件序列含 `react_fallback`、终 `done` 且 `experiment_group=pipeline_fallback`。
- 新增 `TestRecommendStreamEndpoint`（`test_api_e2e.py`）：消费 `/api/v1/recommend/stream` 流，断言事件顺序与终 `done`；错误场景走结构化 `error` 事件。
- 更新 `test_recommend_courses_delegates_to_v1_supervisor` 为 mock `stream_recommend_unified`。
- `python -m pytest tests/ -m "not slow" -q`：**114 passed, 4 deselected**。

## 经验与后续

- deepagents/StructuredTool 工具契约是"单值返回"，工具内无法向主 agent 的 SSE 流注入中间事件；前端流式体验必须由端点级 SSE 承载，工具内部只能做同源聚合。
- 后续新智能体编排统一使用 deepagents/LangGraph，v1 supervisor 仅作为原子能力层保留。
