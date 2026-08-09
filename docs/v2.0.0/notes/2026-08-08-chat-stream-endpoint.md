# Chat SSE 端点补齐（POST /api/v1/chat/stream）

## 背景与问题

- 上一轮收敛推荐接口时确认了「recommend_courses 流式适配 + chat SSE」方案，但只落地了 `recommend_courses` 工具内部流式聚合（消费 `stream_recommend_unified`），chat SSE 端点未实施。
- `POST /api/v1/chat` 仍是同步 JSON 返回，前端主对话框无法看到流式打字效果，与 AGENTS.md「前端 API 一律流式」契约不符。

## 总体架构方案

- 新增 `POST /api/v1/chat/stream` SSE 端点，用 deepagents 主 agent（LangChain Runnable）的 `astream_events` 推送流式事件。
- 保留同步 `POST /api/v1/chat` 兼容后端调用。
- 事件协议：`text`（token 增量）、`tool`（工具 start/end）、`done`（reply + messages_count）、`error`（结构化 code/message）。

## 细节实现

- `python/api/chat.py`：
  - `chat_stream` 端点返回 `StreamingResponse(media_type="text/event-stream")`。
  - `async for event in agent.astream_events(..., version="v1")` 过滤：
    - `on_chat_model_stream` → 提取 `chunk.content`（处理 str/list 两种形态）→ 累积并 yield `text`。
    - `on_tool_start` / `on_tool_end` → yield `tool`（tool 名 + status）。
    - 结束后 yield `done`（reply = 拼接的 token）。
    - 异常捕获后 yield `error`（不静默断连）。
- 复用 `ChatRequest`，`session_id` 继续用于 thread_id 恢复；`run_name=LLMTaskName.CHAT_ENDPOINT`。

## 测试与验证

- `TestChatStreamEndpoint`（`tests/test_api_e2e.py`）：
  - mock agent `astream_events` 产出 tool/text/tool 事件，断言 `tool → text → done` 顺序、reply 内容、session_id。
  - mock 抛异常，断言终事件为 `error`。
- `python -m pytest tests/ -m "not slow" -q`：**116 passed, 4 deselected**。

## 经验与后续

- `astream_events` 的 `on_chat_model_stream` 事件需兼容 `chunk.content` 为 str 或 tool-call dict 列表两种形态。
- mock 时 `astream_events` 应为 async generator（含 `yield`），否则出现 coroutine never awaited 警告。
- 前端主对话框接 `/api/v1/chat/stream`；后续如需工具内部阶段进度透出（如推荐阶段），可扩展 `tool` 事件的 payload。
