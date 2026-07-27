# Supervisor 与 LangGraph 编排器对比

## 背景与问题

- 本轮要解决的问题：`/api/v1/recommend` 走 `SupervisorOrchestrator`，`/api/v1/recommend/graph` 走 LangGraph `StateGraph`，用户想搞清楚两者业务结果「等价」的前提下，编排器到底差在哪、为什么生产用前者、效果对比、代码层面如何体现。
- 触发原因或用户诉求：上一轮已盘点接口用途，这一轮要求把「等价」拆细。
- 影响范围：仅做只读分析，对比 `python/orchestrator/supervisor.py` 与 `python/orchestrator/graph.py`。

## 总体架构方案

- 涉及模块：
  - `python/orchestrator/supervisor.py`（`SupervisorOrchestrator`）
  - `python/orchestrator/graph.py`（`build_recommendation_graph` + LangGraph `StateGraph`）
  - 共用 5 个 Agent：`StudentProfileAgent` / `CourseRecallAgent` / `CourseRerankAgent` / `CourseFeasibilityAgent` / `RecommendationReasonAgent`
- 数据流：两者都包含「画像 + 召回 并行 → 重排 + 可行性 并行 → 推荐理由 串行」三段；区别在编排载体和中间能否再精修。
- 关键设计取舍：Supervisor 内嵌「画像驱动的二次召回」，是当前生产真链路；LangGraph 仅作为同样三段的**展示版编排**，方便后续接入条件分支、断点、可视化追踪。

## 细节实现

### 编排器结构对比

| 维度 | `SupervisorOrchestrator` | LangGraph `build_recommendation_graph` |
|------|---------------------------|-----------------------------------------|
| 编排方式 | 纯 Python `async/await` + `asyncio.gather` 直接写流程 | 显式声明节点和边的有向图（DAG） |
| Agent 注入 | 构造函数支持依赖注入，单测可替换（`test_supervisor_pipeline.py` 直接 stub） | 模块级单例（`graph.py` 顶层 `student_profile_agent = StudentProfileAgent()` …） |
| 状态载体 | 函数局部变量：`profile_result`、`raw_courses`、`final_courses` 等 | `PipelineState`（TypedDict），全程在节点间传递 |
| 中间精修 | 画像成功后**追加一次结构化召回**并 `_merge_courses` | **没有这一步**，画像不会影响召回二次执行 |
| 阶段日志 | 4 处 `structlog`：`start / phase1_complete / refined_recall_complete / phase2_complete / phase3_complete / complete`，带 `request_id` | 仅 `init_node` 设置 `request_id`，无阶段日志 |
| 异常路径 | 依赖各 Agent `BaseAgent._fallback` 兜底；最外层无 try/except | 同左，但状态字段缺失时多用 `state.get(..., default)` 容错 |
| 实验上下文 | `experiment.assign` 后**写入返回结果** `experiment_group` | `init_node` 写入 `state["experiment_group"]`，但**返回时被丢弃**（`/recommend/graph` 响应里没拼回去） |
| Agent 结果回填 | `RecommendationResponse.agent_results` 完整 5 项 | 接口层只 `model_dump()` final_courses，丢弃 `agent_results` 详情 |
| 链路类型 | 当前生产链路 | 演示性链路 |

### 关键代码体现

1. Supervisor 的「画像精修召回」差异点（LangGraph 没有）：

```117:135:python/orchestrator/supervisor.py
        if student_profile:
            refined_result = await self.course_recall_agent.run(
                student_profile=student_profile,
                prompt=prompt,
                context=request.context,
                num_items=request.num_items * 2,
            )
            raw_courses = self._merge_courses(
                raw_courses,
                getattr(refined_result, "courses", []),
            )
            recall_result.data["refined_candidate_count"] = len(raw_courses)
            logger.info(
                "course_supervisor.refined_recall_complete",
                request_id=request_id,
                refined_count=len(getattr(refined_result, "courses", [])),
                merged_candidate_count=len(raw_courses),
            )
```

2. LangGraph 仅一次召回，画像即使成功也不会再补：

```81:100:python/orchestrator/graph.py
async def course_recall_node(state: PipelineState) -> PipelineState:
    result = await course_recall_agent.run(
        student_profile=state.get("student_profile"),
        prompt=state.get("prompt", ""),
        context=state.get("context", {}),
        num_items=state.get("num_items", 10) * 2,
    )
    state["raw_courses"] = getattr(result, "courses", [])
    state["agent_results"]["course_recall"] = result
    return state


async def parallel_phase1(state: PipelineState) -> PipelineState:
    profile_state, recall_state = await asyncio.gather(
        student_profile_node(dict(state)),
        course_recall_node(dict(state)),
    )
    state.update(profile_state)
    state.update(recall_state)
    return state
```

3. LangGraph 的边声明（DAG 形态明确）：

```160:176:python/orchestrator/graph.py
def build_recommendation_graph() -> StateGraph:
    graph = StateGraph(PipelineState)
    graph.add_node("init", init_node)
    graph.add_node("parallel_phase1", parallel_phase1)
    graph.add_node("parallel_phase2", parallel_phase2)
    graph.add_node("filter", filter_node)
    graph.add_node("recommendation_reason", recommendation_reason_node)
    graph.add_node("aggregate", aggregate_node)

    graph.set_entry_point("init")
    graph.add_edge("init", "parallel_phase1")
    graph.add_edge("parallel_phase1", "parallel_phase2")
    graph.add_edge("parallel_phase2", "filter")
    graph.add_edge("filter", "recommendation_reason")
    graph.add_edge("recommendation_reason", "aggregate")
    graph.add_edge("aggregate", END)
    return graph.compile()
```

4. Supervisor 的依赖注入（更好测试）：

```38:73:python/orchestrator/supervisor.py
    def __init__(
        self,
        ab_engine: ABTestEngine | None = None,
        student_profile_agent: StudentProfileAgent | None = None,
        course_recall_agent: CourseRecallAgent | None = None,
        course_rerank_agent: CourseRerankAgent | None = None,
        course_feasibility_agent: CourseFeasibilityAgent | None = None,
        recommendation_reason_agent: RecommendationReasonAgent | None = None,
    ):
        ...
        self.student_profile_agent = student_profile_agent
        ...
        self.ab_engine = ab_engine or ABTestEngine()
```

5. LangGraph 出口（在 `main.py` 里拼装响应）裁掉了 `agent_results` 等观察字段：

```125:146:python/main.py
@app.post("/api/v1/recommend/graph")
async def recommend_via_graph(request: RecommendationRequest):
    """使用LangGraph状态图进行公选课推荐 (展示LangGraph能力)"""
    if not rec_graph:
        return {"error": "Graph not initialized"}
    state = {
        "user_id": request.user_id,
        "scene": request.scene,
        "num_items": request.num_items,
        "prompt": request.prompt or request.query or request.context.get("query", ""),
        "context": request.context,
    }
    result = await rec_graph.ainvoke(state)
    return {
        "request_id": result.get("request_id"),
        "user_id": result.get("user_id"),
        "courses": [course.model_dump() for course in result.get("final_courses", [])],
        "recommendation_reasons": result.get("recommendation_reasons", []),
        "selection_warnings": result.get("selection_warnings", []),
        "experiment_group": result.get("experiment_group", "control"),
        "total_latency_ms": round(result.get("total_latency_ms", 0), 1),
    }
```

## Debug 结论

- 「等价」是指**步骤数量、节点角色和并行结构相同**：都是 5 个 Agent、两轮并行、一次串行理由。
- 实际**不完全等价**的点：
  1. Supervisor 多一次「画像驱动的精修召回」（`_merge_courses` 合并候选），LangGraph 没有。
  2. Supervisor 输出 `agent_results` 全量观察数据；LangGraph 在 `main.py` 出口只挑了几个字段。
  3. Supervisor 6 处阶段级 `structlog.info`，LangGraph 节点内零阶段日志。
  4. Supervisor 通过构造函数注入 5 个 Agent，便于在测试中 stub；LangGraph 是模块级单例，难以替换。
- 为什么生产用 Supervisor：
  - 精修召回带来更高召回质量；
  - 完整 `agent_results` 直接服务前端「Agent 轨迹」可视化和 `MetricsCollector` 采集；
  - 阶段日志便于线上排障；
  - 依赖注入让 `test_supervisor_pipeline.py` 能完整覆盖编排。

## 测试与验证

- 已执行：
  - 阅读 `supervisor.py` 与 `graph.py` 全部代码并交叉对比节点结构、状态字段、日志、响应。
  - 阅读 `main.py:117-146` 的两个 endpoint，确认 `/recommend/graph` 出参精简差异。
- 结果：
  - 两条链路在「业务结果」层面**接近等价**，但 Supervisor 有「精修召回 + 观测信息更全 + 可测试」三点明显优势。
  - LangGraph 链路当前定位是「演示 LangGraph 编排能力」，未承担生产流量。
- 未执行及原因：
  - 未做实际接口对比压测（如响应耗时、`agent_results` 内容差异）。本轮按用户需求只做代码层面对比，未触发外部依赖。

## 经验与后续

- 本轮经验：
  - 「编排器等价」要按「节点 / 边 / 状态 / 观测 / 注入」五个维度去拆，不能只看节点数量。
  - LangGraph 的真正价值是「条件边 + 断点 + 可视化」，目前还没用上；如果未来要加「画像失败则跳过精修」「重排失败则切回规则排序」这类条件分支，迁回 LangGraph 反而比手写 if 更清晰。
- 后续建议：
  - 在 LangGraph 链路补上 Supervisor 的「画像精修召回」节点（可写成条件边：`student_profile is not None` 时进入 `refined_recall_node`），让两条链路真正等价。
  - `recommend_via_graph` 出参补回 `agent_results`，否则它对前端 Agent 轨迹页面无价值。
  - 模块级 Agent 单例改为依赖注入或工厂函数，便于和 Supervisor 共用同一组实例（目前两边各 `new` 一份，初始化成本和资源占用都翻倍）。
