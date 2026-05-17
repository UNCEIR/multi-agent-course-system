# Streaming SSE 实现设计笔记

> 日期: 2026-05-17
> 触发: `ECOM_LLM_STREAMING=true`，API 端点支持 SSE 流式输出，前端卡片式逐课展示推荐理由

---

## 背景

系统目前为请求-响应模式：`POST /api/v1/recommend` → Supervisor 三阶段编排 → 完整 `RecommendationResponse` JSON 返回。
需要增加 SSE 流式端点，推送阶段进度事件和词级推荐理由文本，便于前端做演示性互动。

---

## 28 个设计决策

### #1: 要 stream 的内容范围
- **进度事件**（B）：SSE 按 pipeline 阶段推送进度（Phase 1/2/3 完成状态）
- **Token 流式**（C）：推荐理由逐 token 推送给前端打字效果
- **两者都实现**

### #2: 推荐理由输出的格式选择
- **C 方案**：LLM 改 prompt 输出自然语言纯文本（非 JSON），前端逐字符渲染

### #3: 自然语言输出的内容结构
- **A 方案**：整段自然语言混排，各课程推荐连续书写，像 ChatGPT 打字效果

### #4: SSE Event 类型
- 全部都要：`phase`、`text`、`done`、`error`（后扩展 `course_start`、`course_end`）

### #5: Supervisor 层新增 streaming 方法
- **B 方案**：Supervisor 新增 `stream_recommend()` async generator 方法，内部编排后 yield 结构化事件，endpoint 负责 SSE 序列化。

### #6: Agent 新增 streaming 方法的签名
- **A 方案**：`astream_reasons()` 返回 `AsyncGenerator[dict, None]`，agent 内部调 parser 并透传结构化 chunk。不返回 `AgentResult`（延迟统计等由 supervisor 在外部 wrap）。

### #7: Supervisor yield 的单元
- **B 方案**：yield 结构化 event 对象 `{"event": "phase", "data": {...}}`，endpoint 层负责 `sse_format()` 序列化。可测试、可追踪、协议无关。

### #8: SSE 事件时序
- **a)** 每个 phase 汇总一个 `phase` 事件（不分 sub-agent 细粒度）
- **b)** `text` 事件带 `course_id`，前端做卡片对齐
- **c)** 任何阶段出错发 `error` 事件后中断流

### #9: text 事件的 course_id 来源
- **A 方案**：LLM prompt 约定按 marker token `[COURSE:id:name]` 标注每门课推荐起点，parser 拦截后标记后续 token

### #10: Marker 检测逻辑归属层
- **C 方案**：独立 `StreamTokenMarkupParser` 工具类 → 消费 `AsyncGenerator[str]`，产出 `AsyncGenerator[dict]`。Agent 保纯净，Supervisor 只编排，Parser 独立可测。

### #11: Marker 格式核心规范
- 总起段不需要 marker
- 每门课程推荐以 `COURSE:ID:NAME` 开头（后续改为 `[COURSE:id:name]` 包裹）
- 大小写不区分
- 使用 `course_id:course_name` 双重映射，方便 LLM 自然引用

### #12: Marker 需要 `[]` 包裹
- 格式定为 `[COURSE:CS101:电影鉴赏]`，降低正文中出现 "COURSE" 字样的误触发率

### #13: 新版 RecommendReasonAgent prompt
- 不再要求 JSON，改为纯文本自然语言输出
- 规则：
  1. 总起语（无 marker）介绍推荐思路
  2. 每门课以 `[COURSE:course_id:course_name]` 开头
  3. 理由 40-80 字，说明匹配度
  4. 风险提示柔和嵌入理由中（不另起 warning 注入）
  5. 最终无总结段，串完即停
- 风险提示由 LLM 自然嵌入，CourseFeasibilityAgent 的 warning 数据仍然保留给前端 done 事件

### #14: Phase 1 / Phase 2 内部实现
- **A 方案**：不改 agent 运行方式，仍用 `asyncio.gather` 并行等待完整结果，拿到后 yield `phase` 事件

### #15: done 事件的 payload
- 包含：`request_id`、`user_id`、`courses`（final 课程列表）、`recommendation_reasons`、`selection_warnings`、`experiment_group`、`agent_results`、`total_latency_ms`
- 去掉 e-commerce 残留字段：`products`、`marketing_copies`、`review_summaries`、`image_scores`、`price_adjustments`、`fraud_assessment`、`service_recommendation`、`agent_latencies`

### #16: error 事件的 payload
- **A 方案（详细版）**：`{"code": "COURSE_RECALL_FAILED", "message": "...", "phase": "phase1", "agent": "course_recall", "request_id": "xxx"}`
- HTTP 状态码保持 200，最后一个事件为 `error` 而非 `done`

### #17: StreamTokenMarkupParser 的 yield 格式
- **B 方案**：yield 结构化 dict `{"type": "course_start"|"course_end"|"text", "course_id": "...", "token": "..."...}`，parser 做 buffer 拼合，对外干净

### #18: BaseAgent retry 在 streaming 下的处理
- **A 方案**：streaming 不走 retry，由 supervisor 在外部 try/except 包裹，捕获后发 `error` 事件

### #19: 新 streaming endpoint 路径
- **A 方案**：新增 `POST /api/v1/recommend/stream`，旧端点 `/api/v1/recommend` 不变
- 同时新增加 `/api/v1/recommend/graph/stream`（后取消，见 #21）
- LangGraph 端点加不加？先考虑加

### #20: LangGraph streaming 的实现方式
- 最初选了 **A（独立 graph streaming）**
- 后因 StateGraph 的 `astream()` 只支持节点级粒度（不支持 token 流），且节点内部已有 `asyncio.gather` 并行

### #21: LangGraph graph/stream 端点最终决定
- **零改动**：`POST /api/v1/recommend/graph` 和 `build_recommendation_graph()` 完全不改

### #22: SSE HTTP 响应头
- `StreamingResponse(media_type="text/event-stream")`
- Headers: `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no`
- 前端用 `fetch` + ReadableStream 消费 SSE（支持 POST 自定义 headers）

### #23: Settings 配置新增
- **B 方案**：`RecommendationReasonAgent` 独立构造 `streaming=True` 的 LLM 实例
- 新增 `ECOM_STREAM_TIMEOUT_SECONDS=60`，其他 agent 不受影响

### #24: 单 LLM 实例 vs. 双实例
- 单实例 `streaming=True`：`ainvoke()` 内部 LangChain 自行收集所有 chunk 后返回完整 `AIMessage`，对旧 `_execute()` 调用不影响

### #25: build_chat_openai() 新增 streaming 参数
- 加 `streaming: bool = False` 参数
- `StudentProfileAgent`、`CourseRerankAgent` 保持默认 `False`
- 仅 `RecommendationReasonAgent` 传 `streaming=True`
- Agent 的 `astream_reasons()` 内部构造 prompt → `self.llm.astream(messages)` → 传 raw AsyncGenerator 进 parser → parser 产出结构化 dict → yield 向上

### #26: stream_recommend() 行为
- async generator 自然结束（不显式 `return` 值）
- `done` 事件作为最后一个 yield
- Supervisor 内部用 `asyncio.wait_for` 配合 `ECOM_STREAM_TIMEOUT_SECONDS` 做整体超时，超时时 yield `error` 事件后 return

### #27: StreamTokenMarkupParser buffer 行为
- 最大 256 字符
- 完整 marker 格式 `[COURSE:<id>:<name>]`，遇到 `]` 后严格正则校验
- buffer 超 cap → flush 为普通文本
- 收到不匹配内容 → flush 为文本
- 遇到 `[` → 重置旧 buffer

### #28: 前端卡片 UI 适配
- 因前端需要逐课卡片弹出打字效果 → 改为 **`course_start` + `course_end` 显式事件**
- marker `[COURSE:id:name]` 不再出现在 text 中 → parser 把它转换为 `course_start` + `course_end` 事件
- `course_end` 由 parser 在检测到下一个 `course_start` 时自动发送；最后一门课由 parser generator exhaustion 自动补发

---

## SSE 完整事件时序

```
[连接建立]
event: phase,   data: {"phase": "start", "request_id": "...", "num_items": 10}
event: phase,   data: {"phase": "phase1_complete", ...stats}
event: phase,   data: {"phase": "phase2_complete", ...stats}
event: phase,   data: {"phase": "phase3_start"}
event: course_start, data: {"course_id": "GXK001", "course_name": "电影鉴赏", "index": 0}
event: text,    data: {"course_id": "GXK001", "token": "该"}
event: text,    data: {"course_id": "GXK001", "token": "课程"}
...
event: course_end, data: {"course_id": "GXK001"}
event: course_start, data: {"course_id": "GXK002", "course_name": "Python程序设计", "index": 1}
...
event: phase,   data: {"phase": "phase3_complete"}
event: done,    data: {request_id, courses, selection_warnings, agent_results, total_latency_ms, ...}
```

---

## 文件变更清单

### 新建文件

| 文件 | 职责 |
|---|---|
| `python/services/stream_token_markup_parser.py` | 消费 LLM raw token 流，检测 `[COURSE:id:name]` marker，产出 `{type, course_id, course_name, index, token}` 结构化事件 |
| `python/tests/test_stream_token_markup_parser.py` | Parser 单元测试 |
| `python/tests/test_stream_recommend.py` | Streaming 集成测试 |

### 修改文件

| 文件 | 改动 |
|---|---|
| `python/config/settings.py` | 新增 `stream_timeout_seconds: float = 60.0` |
| `python/services/llm_client.py` | `build_chat_openai()` 新增 `streaming: bool = False` 参数，透传到 `ChatOpenAI(streaming=...)` |
| `python/services/__init__.py` | 导出 `StreamTokenMarkupParser` |
| `python/agents/recommendation_reason_agent.py` | 单 `streaming=True` LLM 实例；SYSTEM_PROMPT 改为自然语言输出格式；新增 `astream_reasons()` 方法，内部调 LLM + parser |
| `python/orchestrator/supervisor.py` | 新增 `stream_recommend()` async generator 方法 |
| `python/main.py` | 新增 `POST /api/v1/recommend/stream` 端点，返回 `StreamingResponse` |

### 不改动的文件

- `agents/student_profile_agent.py`
- `agents/course_recall_agent.py`
- `agents/course_rerank_agent.py`
- `agents/course_feasibility_agent.py`
- `agents/base_agent.py`
- `models/schemas.py`
- `orchestrator/graph.py`
- `services/embedding_client.py`
- 所有 `repositories/`
- 所有 `tests/` 现有文件（仅新增）

---

## 组件设计摘要

### StreamTokenMarkupParser

- **输入**: `AsyncGenerator[str, None]` — LLM 逐 chunk 产出的 token 流
- **输出**: `AsyncGenerator[dict, None]` — 结构化 chunk
- **状态机**:
  ```
  IDLE ──[ '[' ]──> BUFFERING ──[ ']' ]──> VALIDATE
                           │
               匹配 ^\[COURSE:\w+:[\w\u4e00-\u9fff]+/\]$ ?
               ├─ YES → yield course_end (previous)
               │         yield course_start (new)
               │         → IDLE
               └─ NO →  flush buffer 为 text chunks → IDLE
  
  BUFFERING ──[ buffer > 256 ]──> flush → IDLE
  BUFFERING ──[ 再遇 '[' ]──> flush 旧 buffer → 重启
  Token in IDLE → yield {"type": "text", "course_id": ..., "token": chunk}
  Exhaustion → yield course_end (last)
  ```
- 输出 dict 字段: `type` (`"course_start"` | `"text"` | `"course_end"`), `course_id`, `course_name` (仅在 `course_start`), `index` (仅在 `course_start`), `token` (仅在 `text`)

### RecommendationReasonAgent 改动

- `self.llm = build_chat_openai(temperature=0.55, max_tokens=1536, streaming=True)` — 不再是 `streaming=False`
- 旧 `_execute()` 保留不动：`ainvoke()` 在 `streaming=True` 下仍能正常收集结果，不作废
- 新 prompt（`REASON_STREAM_PROMPT`）：自然语言输出规范 + marker 约定
- 新方法 `astream_reasons(profile, courses, warnings) -> AsyncGenerator[dict, None]`：
  1. 用当前 messages 构造逻辑
  2. `raw_stream = self.llm.astream(messages)`
  3. 将 `AIMessageChunk.content`（统一为 str）传入 parser
  4. `async for chunk in parser.parse(raw_stream): yield chunk`

### Supervisor 改动

- 新增 `stream_recommend(request: RecommendationRequest) -> AsyncGenerator[dict, None]`
- Phase 1/2: 与 `recommend()` 保持一致（`asyncio.gather` 并行跑完）
- Phase 3: `async for chunk in agent.astream_reasons(...)` → yield `{"event": chunk["type"], "data": chunk}`
- 整方法用 try/except 包裹，catch 后 yield error 事件
- 整体超时用 `asyncio.wait_for` + `ECOM_STREAM_TIMEOUT_SECONDS`

### Main 改动

- 新端点：
  ```python
  @app.post("/api/v1/recommend/stream")
  async def recommend_stream(request: RecommendationRequest):
      return StreamingResponse(
          _sse_wrapper(supervisor.stream_recommend(request)),
          media_type="text/event-stream",
          headers={
              "Cache-Control": "no-cache",
              "Connection": "keep-alive",
              "X-Accel-Buffering": "no",
          },
      )
  ```
- `_sse_wrapper()`: `async for event in generator: yield "event: {event}\ndata: {json}\n\n"`

---

## 测试覆盖计划

### test_stream_token_markup_parser.py

- 完整 marker 从单个 chunk 检出 → 产出 `course_start` + `course_end`
- 完整 marker 从多个 chunk 检出（跨 buffer）
- 非法 marker 格式 → flush 为普通 text
- buffer 超过 256 字符 → flush 为 text
- 空输入流 → 无异常退出
- 纯文本无 marker → 全部作为 text chunk
- 连续多个 marker → 每个正确 course_start/course_end
- marker 中内嵌 `[` → 重置 buffer，旧 buffer flush 为 text
- 自然结束 → 最后一门课自动 course_end

### test_stream_recommend.py

- 完整 SSE 事件序列验证（mock agent）
- 无 profile 情况 → 跳过 refined recall 分支
- 相中学 agent 抛异常 → error 事件
- empty courses → 空理由，仍正常 done
- 验证事件顺序：phase/start → phase1 → phase2 → phase3_start → course_start/text/course_end → phase3_complete → done
