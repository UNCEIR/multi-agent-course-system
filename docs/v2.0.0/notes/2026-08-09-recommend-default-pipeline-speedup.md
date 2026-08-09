# 推荐统一入口默认改并行 Pipeline（真实降耗：206s → 60s）

## 背景与问题

- 前轮 Plan A/B 声称"优化"，实测 `/recommend/stream` 仍 169-206s（rounds 14→7 但总耗时没降）。
- 根因（日志实证）：浪费不在轮次，而在 **4 个串行 LLM 调用**：
  - `student_profile` 10-56s、`course_rerank` 13-59s、`course_feasibility` 9-36s、`recommendation_reason` 20s（且常超时失败）。
  - ReAct 模式全程串行，`rerank(59s)` 与 `feasibility(36s)` 本可并行却累加为 95s。

## 总体架构方案

- `stream_recommend_unified` 增加 `mode` 参数：
  - **默认 `pipeline`**：走并行 Pipeline（`student_profile∥course_recall`、`rerank∥feasibility` 用 `asyncio.gather`），外部 LLM 调用少、延迟低。
  - **`mode="react"`**：保留 ReAct（多轮决策 LLM，慢），失败兜底 Pipeline。
- `recommend_courses` 工具同样默认 `mode="pipeline"`，react 可选。

## 细节实现

- `python/agent/recommend/supervisor.py`：`stream_recommend_unified(request, *, mode="pipeline")`，pipeline 直接代理 `stream_recommend`；react 分支保留原 ReAct→Pipeline 兜底逻辑。
- `python/tools/recommend/recommend_courses.py`：`RecommendCoursesInput` 加 `mode` 字段，`recommend_courses` / `stream_recommend_courses` 透传 mode。
- 主 agent 工具白名单（13 个已实装工具）不变；`recommend_courses` 默认走 pipeline。

## 测试与验证

- 更新 `test_stream_recommend_unified_react_fallback_pipeline`（显式 `mode="react"`）、`test_recommend_courses_delegates_to_v1_supervisor`（断言默认 mode=pipeline）。
- 回归：`python -m pytest tests/ -m "not slow" -q` → **131 passed, 4 deselected**。
- 端测（`curl_recommend_payload.json`，`/api/v1/recommend/stream`）：
  - 优化前（ReAct）：`total_latency_ms=205957.6`（205.9s），group=react。
  - 优化后（Pipeline 并行）：**`total_latency_ms=60318.9`（60.3s，降 71%）**，group=pipeline，6 门课/6 理由，done 收尾。

## 经验与后续

- **轮次优化是假优化**：LLM 单次调用 10-60s 才是主耗时，并行（`asyncio.gather`）才是真优化。
- Pipeline 已并行 `rerank∥feasibility`、`student_profile∥course_recall`，这是 3 倍加速的关键。
- ReAct 保留为可选模式（演示/异常场景），但默认不再走它。
- 后续可继续：主 agent `/chat` 意图识别后路由到 `recommend_courses`（pipeline）而非 7 原子工具逐个调；重排/理由结果短期缓存。

## 补充：ReAct B 组并行修复（2026-08-09）

用户指出"部分工具可以并行"——A 组（extract_profile∥search_courses）已并行，但 **B 组（rerank_courses∥check_feasibility）这个最大收益点没并行**（rerank 59s + feasibility 36s 串行 = 95s）。

修复：
- `react_tools.py` 新增 `execute_rerank_on_snapshot` / `execute_feasibility_on_snapshot`：在 courses 快照上执行、不写共享 state.courses，返回结果由主循环合并（对齐 Pipeline Phase2 语义：ranked 排序 → 仅保留 available → 记录 warnings/priority_advice）。
- `supervisor.py` 流式 + 同步 ReAct 循环加 B 组并行分支：本轮 tool_calls 同时含 rerank+feasibility 时 `asyncio.gather`，按原序回填 ToolMessage。
- 决策 prompt 补充"rerank_courses 与 check_feasibility 可同一轮并行"。

**发现并修复一个隐藏 bug**：同步版 `_react_recommend` 的 A/B 组并行逻辑此前**缩进在 `if not tool_calls:` 的 `break` 之后，是死代码**（同步路径从未并行）。修复缩进后同步版 B 组命中（单测验证 `react_b_group_parallel candidate_count=2`，courses 正常）。

测试：新增 `test_react_rerank_feasibility_parallel`；回归 `132 passed, 4 deselected`。

## 补充：主 agent 完整编排提速（2026-08-09）

用户指出 `/api/v1/chat` 走主 agent 完整编排仍 222s。根因（日志实证）：主 agent 读 SKILL.md 后**自己逐个调用 7 个原子工具**（非一键工具），每步一次决策 LLM + 工具 LLM 串行，`recommendation_reason` 单次达 83s。

修复：
- `skills/recommend-courses/SKILL.md`：allowed_tools 收回为 `[recommend_courses]`，主流程引导直接调一键工具（`mode=pipeline` 内部并行），原子工具降为"高级可选"。
- `agent/main/prompt.py`：推荐部分改为"直接调 recommend_courses 一键工具，不要手动分步调原子工具"。
- `agent/runtime.py`：主 agent 白名单移除 7 个原子工具（只留 recommend_courses + 系统/知识库工具），从根上避免主 agent 逐个串行调。

端测对比（`curl_recommend_payload.json` → `/api/v1/chat`）：
- 优化前：222.7s，5 门课
- 优化后：152.8s（-31%），7 门课 + 时间冲突过滤/满员预警/抢课策略

说明：152s 中一键工具内部 pipeline 约 60s，其余为主 agent 决策 LLM 多轮 + 最终呈现 LLM 的开销（SKILL 驱动本质成本）。直接 `/recommend/stream`（pipeline）仍是最快路径（60s）。
