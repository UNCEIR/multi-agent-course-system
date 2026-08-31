# v2.0.0 代码证据链（Code Walkthrough）

> v1 文档按"v1 supervisor → ReAct 工具"走 v1 路径。v2 升级到 **main_agent（deepagents）统一入口** + 4 业务模块 + 知识库 RAG + MCP 工具。本文件按 v2 现状重写请求链路代码证据，配套 `docs/architecture.md` + `docs/v2.0.0/eval-system.md` + `notes/2026-08-18-phase3-sse-resumability-and-cancellation.md`。

## 1. 入口总览（v2）

| 入口 | 端点 | 调用栈 | 用途 |
| --- | --- | --- | --- |
| 主智能体对话 | `POST /api/v1/chat/stream` | lifespan → `agent.runtime.main_agent` → `astream_events` | 知识库问答 + 推荐路由 + 报告路由 + 评价路由 + 论文写作 + 网页搜索 |
| 直接推荐 | `POST /api/v1/recommend/stream` | `api/recommend.py` → `supervisor.stream_recommend_unified()` | 不经 main_agent 的快速推荐（兼容 v1 入口） |
| 报告生成 | `POST /api/v1/report` | `api/report.py` → `report.service.stream_report` | 批量 Excel → 1.html → WeasyPrint PDF |
| 评价寄语 | `POST /api/v1/evaluation` | `api/evaluation.py` → `evaluation.service`（五层反幻觉） | 教师端生成学生评语 |
| 文档摄入 | `POST /api/v1/documents/upload` | `api/documents.py` → `documents.service` | 知识库文档解析 + 分块 + 向量化 |
| 健康/指标/实验 | `GET /health /api/v1/metrics /api/v1/experiments` | `api/health.py` | 监控 + A/B 实验元数据 |

## 2. chat/stream 链路（v2 主流入口，决策 17）

### 2.1 入口与 lifespan

```python
# python/api/chat.py:140-150
@router.post("/api/v1/chat/stream")
async def chat_stream(req: ChatRequest, raw: Request):
    agent = runtime.main_agent        # lifespan 启动时 build_main_agent() 预热
    if agent is None:
        raise RuntimeError("main_agent 未初始化...")
    return StreamingResponse(_generate(), media_type="text/event-stream", ...)
```

```python
# python/agent/runtime.py:163-166 (lifespan)
main_agent = await build_main_agent()   # deepagents factory
```

### 2.2 _generate() 内部

```python
# python/api/chat.py:154-228
async def _generate():
    # 1. 读 session_id / user_id / messages（含记忆注入 + 图片）
    from agent.memory.injector import inject_memory_entries
    memory_prefix = await inject_memory_entries(repo, session_id, user_id)
    messages = [{"role": "user", "content": memory_prefix}, ...]

    # 2. user_context 注入（决策 21）—— ContextVar 让工具拿当前 user
    with user_context(req.user_id):
        # 3. astream_events 触发 LLM 决策 + 工具调用
        async for event in agent.astream_events(
            {"messages": messages}, config={"configurable": {"thread_id": ..., "user_id": ...}},
            version="v1",
        ):
            kind = event.get("event")
            if kind == "on_chat_model_stream":      # token 增量
                yield _sse("text", {"token": ..., "session_id": ...})
            elif kind in ("on_tool_start", "on_tool_end"):
                yield _sse("tool", {"tool": ..., "status": ..., "args": ...})  # 决策 17 + 路 2 SSE 协议
            # else: 丢弃中间事件，只透传 token / tool / done / error
```

### 2.3 main_agent.factory.build_deep_agent

```python
# python/agent/main/factory.py:41-126
async def build_deep_agent(spec: AgentSpec, *, tools=None):
    settings = get_settings()
    backend = build_agent_backend()
    checkpointer = await build_checkpointer() if spec.use_checkpointer else None  # 决策 20: SqliteSaver

    llm = build_chat_openai(        # 不直接 new ChatOpenAI（决策 17）
        temperature=spec.temperature, max_tokens=spec.max_tokens,
        streaming=spec.streaming, task_name=spec.task_name,
    )

    # 工具白名单（路 3 锁死：dispatch_module 必含）
    if tools is None:
        tools = runtime.tool_registry.get_all(allowed=list(spec.allowed_tools))

    # 摘要 + 工具结果落盘 + 渐进式 skill
    summarization = SummarizationMiddleware(model=llm, ..., summary_prompt=...)
    middleware = [summarization, SummarizationToolMiddleware(summarization)]

    # 决策 19：禁写 /memories/AGENTS.md
    permissions = [FilesystemPermission(operations=["write"], paths=["/memories/AGENTS.md"], mode="deny")]

    agent = create_deep_agent(model=llm, tools=tools, backend=backend, skills=spec.skills,
                              memory=spec.memory, checkpointer=checkpointer,
                              system_prompt=spec.system_prompt, middleware=middleware, permissions=permissions)
    return agent.with_config(run_name=spec.task_name.value)
```

### 2.4 工具路由（v1 supervisor 包装为 tool）

```python
# python/tools/recommend/recommend_courses.py（核心实现）
@tool(args_schema=RecommendCoursesInput)
async def recommend_courses(
    user_id: str, prompt: str, num_items: int = 5,
    scene: str = "course_selection",
    mode: Literal["pipeline", "react"] = "pipeline",  # 决策 4
) -> RecommendationResponse:
    request = RecommendationRequest(user_id=user_id, prompt=prompt, num_items=num_items, scene=scene, mode=mode)
    # 调 v1 supervisor（5 agent 流水线，详见 supervisor-main-orchestration.md）
    async for evt in supervisor.stream_recommend_unified(request, mode=mode):
        # 收集 phase/text/course_start/course_end/done → 最终拼成 RecommendationResponse
        ...
```

### 2.5 数据指标（eval_system.md + reports/）

| 测试 | 结果 | 报告 |
| --- | --- | --- |
| `chat_intent --live` | 4/4（路 1 修复后） + 20 case smoke | `eval/reports/chat_intent-2026-08-18.json` |
| `evaluation_comment_live` | 6/6 | `eval/reports/evaluation_comment_live-2026-08-17.json` |
| `report_math_live` | 2/2（37 学生 PDF 全成） | `eval/reports/report_math_live-2026-08-18.json` |
| `web_search` | 5/5 | `eval/reports/web_search-2026-08-16.json` |
| `image_generate` | 5/5 | `eval/reports/image_generate-2026-08-16.json` |

## 3. evaluation 链路（五层反幻觉直接管线，决策 16+17）

### 3.1 入口

```python
# python/api/evaluation.py:33-77
@router.post("/api/v1/evaluation")
async def evaluation(req: EvaluationRequest, raw: Request):
    buf = EventBuffer(thread_id=f"evaluation:{req.target_user_id}:{req.comment_type}")
    last_event_id = parse_last_event_id(raw.headers.get("Last-Event-ID"))

    async def _generate():
        # 续传：先回放缓存
        for buffered in await buf.replay_from(last_event_id):
            yield sse_with_id(buffered.event, buffered.payload, buffered.event_id)
        # 正常生成
        q = asyncio.Queue()
        task = asyncio.create_task(stream_evaluation(
            target_user_id=req.target_user_id, comment_type=req.comment_type,
            generated_by=req.generated_by, out_queue=q,
        ))
        try:
            while True:
                try:
                    event, data = await asyncio.wait_for(q.get(), timeout=0.5)
                    payload = json.dumps(data, ensure_ascii=False)
                    event_id = await buf.append(event, payload)
                    yield sse_with_id(event, payload, event_id)
                    if event in ("done", "error"):
                        break
                except asyncio.TimeoutError:
                    if task.done():
                        break
        finally:
            ...
```

### 3.2 stream_evaluation 五层管线

```python
# python/agent/evaluation/service.py
async def stream_evaluation(target_user_id, comment_type, generated_by, out_queue):
    # 1. 快照：拉取学生成绩单 + 学籍（MySQL evaluation_repo / chat_session_repo）
    snapshot = await get_academic_snapshot(target_user_id)
    if not snapshot:
        out_queue.put(("done", {"comment": "no_transcript_data", ...}))
        return

    # 2. 雷达方案：design_dimensions (5 维提案)
    radar = await design_dimensions(snapshot, comment_type)

    # 3. LLM 评语：generate_comment (按 comment_type 4 种驱动)
    comment = await generate_comment(snapshot, radar, comment_type, generated_by)

    # 4. 反幻觉核验：reference.assertion 拦截（comment 引用的数值必须来自 snapshot）
    # （generate_comment 内部断言）

    # 5. 落库：evaluation_records (MySQL)
    await evaluation_repo.insert(...)
```

### 3.3 工具链：3 个 @tool（决策 16 实装）

```python
# python/tools/evaluation/{get_academic_snapshot,tool_wrappers}.py
# 路 3 实装：把 5 层直接管线暴露为 3 个独立 @tool，给 main_agent 调

# 1. get_academic_snapshot (Step 1 快照)
@tool(args_schema=SnapshotInput)
async def get_academic_snapshot(user_id: str) -> dict:
    """拉取学生完整成绩单 + 学籍 JSON"""
    return await snapshot_repo.get_user_full_record(user_id)

# 2. design_dimensions (Step 2 雷达方案)
@tool(args_schema=DimensionsInput)
async def design_dimensions(snapshot: dict, comment_type: str) -> list[dict]:
    """3 维固定（gpa/credit/balanced）+ 2 维 LLM 提案"""

# 3. generate_comment (Step 3 评语)
@tool(args_schema=CommentInput)
async def generate_comment(snapshot: dict, radar: list[dict], comment_type: str) -> str:
    """LLM 按 comment_type 4 种驱动，反幻觉核验"""

# 4. compute_radar_values (Step 2.5 重算雷达)
@tool(args_schema=RadarInput)
async def compute_radar_values(snapshot: dict, dimensions: list[dict]) -> list[dict]:
    """雷达图数值计算（5 维）"""
```

### 3.4 4 种 comment_type（决策 5 修订）

| comment_type | 评语风格 | 数据指标 |
| --- | --- | --- |
| `semester_summary` | 学期总结 + 优势科目 | 6/6 live 通过（核心） |
| `encouragement` | 鼓励寄语 | 6/6 live |
| `improvement_advice` | 改进建议 | 6/6 live |
| `recommendation` | 学业推荐 | 6/6 live |

## 4. report 链路（决策 5 修订）

### 4.1 入口与四决策点

```python
# python/agent/report/service.py
async def stream_report(files, semester, user_message, out_queue):
    # 1. inspect_score_excels: openpyxl 解析 → subject + grades JSON
    # 2. merge_students: 多科 → 学生级 JSON
    # 3. fill_report_html: 1.html Jinja2 填表（学生信息 + 成绩 + 教师评语）
    # 4. compute_weighted_grade: 0.3×display + 0.7×exam + bonus（路 3 实装 tools/report/compute_weighted_grade.py）
    # 5. render_pdf: WeasyPrint → MinIO 上传 → HMAC token URL
```

### 4.2 加权公式（关键业务指标）

```python
# python/tools/report/compute_weighted_grade.py
def compute_weighted_grade(display_score: float, exam_score: float, bonus: float = 0.0) -> float:
    return 0.3 * display_score + 0.7 * exam_score + bonus
```

**实测数据**（`eval/reports/evaluation_comment_live-2026-08-17.json`）：
- 学生 3123003252 真实成绩单：71 门课 / 144.5 学分 / 加权均分 **85.85**
- 评语引用了 compute_weighted_grade 算出的真实数值 —— 反幻觉闸放行
- 6 个 case 全部通过

### 4.3 数据指标

| 维度 | 状态 | 证据 |
| --- | --- | --- |
| **report_math_live** | ✅ 2/2（37 学生 PDF 全成） | `eval/reports/report_math_live-2026-08-18.json` |
| **单 PDF 延迟** | 910s/722s | 批处理 37 学生 |
| **HMAC token 下载** | 24h 有效 | `report/download` 端点 |
| **MinIO bucket** | `report-artifacts` | docker-compose 端口 9002 |

## 5. RAG 知识库（Phase 1 决策 6 修订）

### 5.1 摄入流水线

```
document → scripts/ingest_*.py
  → parse (pypdf / pymupdf 兜底)
  → NFKC normalize
  → desensitize (姓名 → [姓名], 学号 mask, 班级 → 年级, 日期 → 年)
  → recursive chunking (heading-aware + 中文分隔符)
  → embed (text-embedding-v4, 1024 维)
  → Milvus.upsert (user_id partition: public / user)
  → MySQL.document_records + document_chunks (回填正文)
```

### 5.2 query_knowledge tool（决策 19 + 21）

```python
# python/tools/knowledge/query_knowledge.py
@tool(args_schema=QueryKnowledgeInput)
async def query_knowledge(query: str, top_k: int = 5) -> str:
    user_id = get_current_user_id()      # 决策 19：ContextVar 注入
    repo = runtime.document_vector_repo
    allowed = [PUBLIC_USER]
    if user_id and user_id != PUBLIC_USER:
        allowed.append(user_id)            # public + 当前 user 分区
    query_vector = repo.embedding_client.embed_text(query)
    hits = repo.search(query, top_k, user_ids=allowed, query_vector=query_vector)
    contents = await asyncio.to_thread(runtime.document_repo.get_chunk_contents, ...)
    # LLM 回答 + 强制引用来源 [来源: 学生手册 第X页]
```

### 5.3 数据指标

| 维度 | 状态 | 证据 |
| --- | --- | --- |
| **kb_retrieval live** | ⚠️ 0/3（标注与真实 chunk_id 不匹配） | `eval/reports/kb_retrieval-2026-08-17.json` |
| **context_recall** | 0.285 | 标注需重写 |
| **context_precision** | 0.933 | 反证检索质量高 |
| **Phase 4 重写标注** | 待办 | eval-system.md §6 登记约定 |

## 6. SSE 协议（路 2 升级）

### 6.1 后端 EventBuffer

```python
# python/services/sse_event_buffer.py
class EventBuffer:
    async def append(self, event: str, payload: str) -> int:
        client = await self._connect()
        if client:
            # INCR 全局自增 → 跨实例/跨重启单调递增
            event_id = int(await client.incr(self.counter_key))
            await client.expire(self.counter_key, ...)
        else:
            self._counter += 1
            event_id = self._counter
        # LPUSH + LTRIM 环形缓冲
        await client.lpush(self.key, json.dumps({...}))
        await client.ltrim(self.key, 0, self.max_size - 1)
        return event_id

    async def replay_from(self, last_event_id: int | None) -> list[BufferedEvent]:
        if last_event_id is None or last_event_id <= 0: return []
        raws = await client.lrange(self.key, 0, self.max_size - 1)
        out = []
        for raw in raws:
            item = json.loads(raw)
            if item.get("id", 0) > last_event_id:
                out.append(BufferedEvent(...))
        out.sort(key=lambda e: e.event_id)
        return out
```

### 6.2 前端 consumeSSEWithRetry

```typescript
// frontend/src/lib/sse.ts
export async function* consumeSSEWithRetry(
  url: string, init: RequestInit, signal?: AbortSignal,
  options: ConsumeSSEOptions = {},
): AsyncGenerator<SSEParsedEvent> {
  const maxAttempts = options.maxAttempts ?? 3
  const baseMs = options.retryBaseMs ?? 500
  let lastEventId: string | undefined

  while (attempt < maxAttempts) {
    attempt++
    if (signal?.aborted) return
    const headers = { ...init.headers, ...options.extraHeaders }
    if (lastEventId !== undefined) headers['Last-Event-ID'] = lastEventId
    try {
      const res = await fetch(url, { ...init, headers, signal })
      if (!res.ok) throw new Error(...)
      for await (const evt of parseSseStream(res.body!, signal)) {
        if (evt.id) lastEventId = evt.id
        yield evt
      }
      return
    } catch (err) {
      if (signal?.aborted) return
      if (attempt < maxAttempts) {
        const delay = baseMs * 2 ** (attempt - 1)
        options.onRetry?.(attempt, delay, lastEventId)
        await sleep(delay, signal)
        continue
      }
      throw err
    }
  }
}
```

## 7. 主要单测入口（v2）

```bash
# 后端
cd python
python -m pytest tests/test_chat_intent_prompt.py -v    # 20 个 prompt 内容契约测试
python -m pytest tests/test_sse_event_buffer.py -v       # 16 个 EventBuffer 单测
python -m pytest tests/ -m "not slow" -q                 # 335 passed

# 前端
cd frontend
npm test -- tests/lib/sse.spec.ts                        # 11 个 consumeSSE/retry
npm test -- tests/components/StreamView.spec.tsx         # 11 个流式输出 + 取消 + a11y
npm test -- tests/components/CourseFields.spec.tsx      # 18 个共享字段层
npm test                                                 # 127 passed
```

## 8. 复盘笔记交叉索引

| 主题 | 笔记 |
| --- | --- |
| SSE 续传 + 取消按钮 + aria-live | `notes/2026-08-18-phase3-sse-resumability-and-cancellation.md`（路 2） |
| chat_intent 4 case 修复（教师端 dispatch_module 路由） | `notes/2026-08-18-chat-intent-4-badcase-fix.md`（路 1） |
| 4 个边界 case 增补 + prompt 内容契约 | `notes/2026-08-18-phase3-nlu-tuning-and-proxy-fix.md`（路 4） |
| 错误反馈统一层（zod/useNotify/Prettier） | `notes/2026-08-18-phase3-error-unification-and-prettier.md`（路 3） |
| 课程卡共享字段层 | `docs/v2.0.0/frontend-architecture.md`（路 7） |
| Phase 3 真实端测兑现 | `notes/2026-08-18-phase3-live-eval-fulfillment.md` |
| docker rebuild + proxy 502 | `notes/2026-08-18-phase3-live-eval-docker-rebuild.md`（路 5） |

## 9. 不在 v2 范围

- Phase 4 全量 LLM-as-judge 评测（faithfulness / answer_relevancy / NDCG）
- A/B 实验 runtime 切换（当前 metrics 进程内，决策 21 计划外移 RabbitMQ）
- 跨语言 Java 数据服务 + BFF 真正启用
- 多模态 LLM 接入（决策 4 修订：图片生成/识别仍独立路径）
