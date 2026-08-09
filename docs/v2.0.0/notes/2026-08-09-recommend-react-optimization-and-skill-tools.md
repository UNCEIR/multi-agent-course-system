# ReAct 延迟优化（Plan A）+ SKILL 驱动原子工具（Plan B）

## 背景与问题

- 推荐接口单请求 142-248s：`rounds=10-14`，14 轮 = 14 次决策 LLM + 8 次子 Agent LLM + 3 次 embedding，全部串行累加。
- 根因（实证）：空转轮（决策不调工具也白耗一轮）、无单次 LLM 超时、重复工具调用、轮次上限过高。
- Plan B 目标：v1 的 7 个 ReAct 工具提升为独立 `@tool`，SKILL.md 承载完整流程，主 agent 读 SKILL 后自行编排。

## 冲突检验（subagent）

- 两计划文件交集为零（A 改 supervisor/react_tools/base_agent；B 新增 atomic_tools + 改注册/SKILL/context/course_recall）。
- 4 个设计张力已解决：embedding 缓存用 dict+Lock（ContextVar 在 asyncio.gather 下跨任务失效）；recommend_courses 保持 ReAct-first；prompt 双面对齐；semantic_filter/流式理由补超时。

## Plan A 实现

- `supervisor.py` 两处 ReAct 循环（流式 + 同步）：
  - 空转即终止（无 tool_calls 且非 FINISH → break）
  - `max_rounds` 20→10
  - A 组并行（extract_profile ∥ search_courses）：`asyncio.gather` 执行、按 tool_calls 原始顺序回填 ToolMessage（**修复 OpenAI "tool 消息须跟在 tool_calls 后" 400 错误**——最初实现回填顺序错位导致端测失败）
  - 决策 prompt 收紧（每工具只调一次、不重复、可并行提示）
- `base_agent.py`：`asyncio.wait_for(_execute, timeout=self.timeout)` 超时兜底；`settings.agent_timeout_*` 校准（profile 15/recall 10/rerank 15/reason 20/feasibility 20）。
- `react_tools.py`：ReactState 去重（已完成工具跳过）。

## Plan B 实现

- 新增 `tools/recommend/atomic_tools.py`：7 个 @tool（extract_profile/search_courses/filter_hard_constraints/semantic_filter_courses/rerank_courses/check_feasibility/generate_reasons）。
  - 状态传递：profile 用 JSON、courses 用 course_id 列表，工具内 `_hydrate_courses` 从 MySQL 还原（避免 150 门课进上下文）。
  - user_id 从 `get_current_user_id()` 注入。
  - `semantic_filter_courses` 补 `asyncio.wait_for(timeout=15)`（supervisor._llm_semantic_filter 不在 BaseAgent 覆盖内）。
- 注册：`tools/recommend/__init__.py` + `tools/__init__.py` + `runtime.py` register_many（工具总数 12→19）。
- **主 agent 工具白名单**：只暴露 13 个已实装工具，排除 Phase 2/3/4 stub（避免 LLM 误调 code_interpreter 等）。
- `skills/recommend-courses/SKILL.md` 重写：allowed_tools 放开 7 原子工具 + 完整操作手册（步骤/每工具一次/硬约束不跳过/失败回退 recommend_courses）。
- `prompt.py`：推荐部分改为"读 SKILL 按步骤调用 7 原子工具"。
- `context.py` + `course_recall_agent.py`：embedding dict+Lock 请求级缓存（同 user+query 只 embed 一次，容量 100 上限）。

## 测试与验证

- 新增：`test_recommend_atomic_tools.py`（7 工具契约、user_id 注入、rerank→feasibility 链、semantic_filter、embedding 缓存隔离、SKILL allowed_tools 一致）、`test_base_agent.py` 超时兜底、`test_stream_recommend.py` 空转即终止。
- 回归：`python -m pytest tests/ -m "not slow" -q` → **131 passed, 4 deselected**。
- 端测（`curl_recommend_payload.json`）：
  - Plan A 后 `/recommend/stream`：rounds 14→7，`group=react` 无 fallback，6 门课/6 理由。
  - Plan B 后 `/recommend/stream`：仍 `group=react` 正常；主 agent `tool_count=13`（stub 已排除）。
  - `/chat` SKILL 驱动：日志确认主 agent 依次调 course_recall（wide/refined）/course_rerank/course_feasibility，`query_embedding_cached` 命中（缓存生效），`agent.failed recommendation_reason` 为空串 error（asyncio.TimeoutError 兜底触发）。耗时 >300s（SKILL 驱动 = 主 agent 多轮决策 LLM + 工具 LLM 串行，为编排本质成本）。

## 经验与后续

- **ToolMessage 必须按 tool_calls 原始顺序回填**：并行执行可，但消息历史顺序不能乱，否则违反 OpenAI 消息约束。
- **ContextVar 在 asyncio.gather 下跨任务失效**：child task 上下文独立，共享缓存用 dict+Lock。
- **SKILL 驱动主 agent 天然比固定 Pipeline 慢**：编排权交给 LLM = 多轮决策；后续可考虑主 agent 只在意图识别后路由到 `recommend_courses` 一键工具（内部 Pipeline 最快路径），7 原子工具作为可选的精细编排路径。
- **stub 工具不应暴露给主 agent**：已用 allowlist 白名单过滤，后续新工具实装后加入白名单。
- 后续：LLM 单次调用本身慢（student_profile 55s 等）是外部服务延迟，可考虑并行/缓存/更换模型。
