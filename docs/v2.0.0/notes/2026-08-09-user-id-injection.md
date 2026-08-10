# user_id 全链路穿透（chat → 工具）与 JSON 端测

## 背景与问题

- chat 场景的 `ChatRequest.user_id` 此前只进日志，没透传给主 agent 工具；`recommend_courses`/`query_knowledge` 靠 LLM 从对话猜 user_id，不可靠，且 `recommend_courses` 无法个性化。
- 后续功能定制化需要按学生身份做个性化/鉴权，需要一套统一的 user_id 注入基座。

## 总体架构方案

- **ContextVar 统一注入基座**：`agent/main/context.py` 用 `ContextVar` 存当前请求 user_id，工具统一 `get_current_user_id()` 读取。
- **`/chat` 与 `/chat/stream` 用 `user_context(req.user_id)` 包裹 agent 调用**（同一 event loop 内 100% 可靠），并把 `user_id` 写入 `config["configurable"]`。
- **工具纯注入**：`query_knowledge`、`recommend_courses` 的 Input schema 移除 `user_id` 字段，改为读取 ContextVar；不依赖 LLM 填参，不把 user_id 暴露给 LLM 猜测。
- 直连端点 `/api/v1/recommend/stream` 仍显式收 `RecommendationRequest.user_id`（不经 chat，两套并存）。

## 细节实现

- 新增 `python/agent/main/context.py`：`_current_user_id` ContextVar + `get_current_user_id()` / `is_authenticated()` / `set_current_user_id()` / `user_context()` 上下文管理器。
- `python/api/chat.py`：同步 chat 与 chat_stream 都加 `user_id` 到 configurable 并用 `user_context(req.user_id)` 包裹调用。
- `python/tools/knowledge/query_knowledge.py`：删 `user_id` 参数，改 `get_current_user_id()`；检索分区 `[public]` + 本人分区。
- `python/tools/recommend/recommend_courses.py`：删 `user_id` 参数，`RecommendationRequest(user_id=get_current_user_id(), ...)`。
- `agent/main/prompt.py`、`skills/knowledge-query/SKILL.md`、`AGENTS.md` 补充"user_id 系统注入"说明。

## 测试与验证

- 新增 `tests/test_user_context.py`（ContextVar set/reset/嵌套/匿名）。
- 更新 `test_query_knowledge.py`（用 `user_context` 包裹，断言注入分区）、`test_phase1_local_capabilities.py`（recommend 注入 user_id）、`test_api_e2e.py`（chat/chat_stream 断言 config 携带 user_id）。
- 回归：`python -m pytest tests/ -m "not slow" -q` → **122 passed, 4 deselected**。
- Docker 重建 + JSON 端测（入参 = `scripts/curl_recommend_payload.json`）：
  - `POST /api/v1/recommend/stream`：200，ReAct 模式（group=react）完成，142.7s，6 门课、3 条理由，`done` 收尾，无 fallback。
  - `POST /api/v1/chat`：200，202.9s，主 agent 经 `recommend_courses` 工具完成个性化推荐并返回课程/考核/容量分析。

## 经验与后续

- **ContextVar + 端点包裹是最可靠穿透方式**；deepagents `AgentMiddleware.abefore_model` 不接收 config，`Runtime` 也无 config 属性，middleware 注入方案不可靠，最终放弃。
- `astream_events` 的 `on_chat_model_stream` 在 chat/stream 上未透出 text 事件（deepagents 图以 `stream_mode="updates"` 聚合），chat/stream 目前只稳定产出 `done`；token 级透出待后续用 `astream(stream_mode="messages")` 处理，不阻塞 user_id 注入目标。**（2026-08-10 已修复**：`MAIN_AGENT_SPEC` 加 `streaming=True`，factory 透传后 `astream_events` 能产出 `on_chat_model_stream`，chat/stream 恢复 text 事件，不再空回复。见 `specs.py`/`factory.py`。）
- 后续所有需要用户身份的工具/插件统一走 `get_current_user_id()`。
