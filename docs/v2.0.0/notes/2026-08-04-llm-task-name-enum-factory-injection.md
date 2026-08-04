# LLMTaskName 枚举 + 工厂注入 trace 名称（2026-08-04）

## 背景与问题

- **本轮要解决的问题**：LangSmith 追踪到的每个 LLM 调用 trace 都显示默认类名 `ChatOpenAI`，无法区分是哪个 Agent 发起的调用。用户无法按业务维度分析 LLM 用量和延迟。
- **触发原因**：上轮 LangSmith 集成已经让所有 LLM 调用被追踪到，但 trace 名称全部是默认的 `ChatOpenAI`，在监控平台无法区分 `student_profile`、`course_rerank`、`recommendation_reason` 等不同业务场景。
- **用户补充诉求**：Embedding 调用同样没有绑定业务名称，所有 embedding trace 显示固定的 `openai.embed_query`。
- **影响范围**：所有 LLM 调用（5 个 Agent + Supervisor + Graph）和 Embedding 调用（在线召回 + 离线回填/导入）。

## 总体架构方案

采用**枚举 + 工厂参数注入**方式，零侵入 Agent 业务代码，在工厂层通过 `with_config` 注入 trace 名称：

| 层 | 文件 | 方案 |
|---|---|---|
| 枚举定义 | `python/services/llm_task_name.py` | 新建 `LLMTaskName(str, Enum)`，区分 LLM 和 Embedding 两类场景 |
| LLM 工厂 | `python/services/llm_client.py` | `build_chat_openai` / `build_tool_calling_llm` 增加 `task_name` 参数，通过 `.with_config({"run_name": task_name.value})` 注入 |
| Embedding 工厂 | `python/services/embedding_client.py` | `build_embedding_client` 增加 `task_name` 参数，`OpenAIEmbeddingClient` 运行时动态绑定 `@traceable(name=task_name)` |
| 调用点 | 各 Agent / Supervisor / Graph / 脚本 | 传入对应的 `LLMTaskName` 枚举值 |

**关键设计决策**：

- `Runnable.with_config({"run_name": "..."})` 返回 `RunnableBinding`，在 invoke 时 `config.get("run_name")` 被 `on_chat_model_start` 接收为 `name` 参数，写入 LangSmith trace。
- `bind_tools` 返回的 `RunnableBinding` 会丢失外层 `with_config` 配置，因此在 `build_tool_calling_llm` 中对 `bind_tools` 结果再调用 `with_config`。
- Embedding 侧 `OpenAIEmbeddings` 的 `embed_query`/`embed_documents` 被 `@traceable` 装饰，名称来自装饰器参数。改造为运行时动态绑定 `@traceable(name=...)`，允许每个实例有独立 trace 名称。

## 细节实现

### 1. 新建 `python/services/llm_task_name.py`

```python
class LLMTaskName(str, Enum):
    # LLM 场景
    STUDENT_PROFILE = "student_profile"
    COURSE_RERANK = "course_rerank"
    COURSE_FEASIBILITY = "course_feasibility"
    RECOMMENDATION_REASON = "recommendation_reason"
    SEMANTIC_FILTER = "semantic_filter"
    REACT_ORCHESTRATOR = "react_orchestrator"
    GRAPH_SEMANTIC_FILTER = "graph_semantic_filter"
    # Embedding 场景
    COURSE_RECALL = "course_recall"
    BACKFILL = "backfill"
```

### 2. 改造 `python/services/llm_client.py`

`build_chat_openai` 和 `build_tool_calling_llm` 新增 `task_name` 参数，在返回前调用 `.with_config({"run_name": task_name.value})`：

```python
def build_chat_openai(*, temperature, max_tokens, streaming=False, task_name=None):
    llm = _create_chat_openai(...)
    if task_name is not None:
        llm = llm.with_config({"run_name": task_name.value})
    return llm

def build_tool_calling_llm(tools, *, temperature=0.1, max_tokens=4096, task_name=None):
    llm = _create_chat_openai(...)
    bound = llm.bind_tools(tools, tool_choice="auto")
    if task_name is not None:
        bound = bound.with_config({"run_name": task_name.value})
    return bound
```

### 3. 改造 `python/services/embedding_client.py`

`OpenAIEmbeddingClient.__init__` 新增 `task_name` 参数，运行时动态绑定 `@traceable`：

```python
class OpenAIEmbeddingClient(EmbeddingClient):
    def __init__(self, ..., task_name="openai.embed_query"):
        ...
        self._traced_embed_query = traceable(
            run_type="embedding", name=task_name
        )(self._lc.embed_query)
        self._traced_embed_documents = traceable(
            run_type="embedding", name=task_name
        )(self._lc.embed_documents)
```

### 4. 调用点注入

| 文件 | 行 | 场景 | trace 名称 |
|------|-----|------|-----------|
| `agents/student_profile_agent.py` | 73 | 学生画像提取 | `student_profile` |
| `agents/course_rerank_agent.py` | 46 | 课程重排 | `course_rerank` |
| `agents/course_feasibility_agent.py` | 47 | 选课可行性 | `course_feasibility` |
| `agents/recommendation_reason_agent.py` | 64 | 推荐理由生成 | `recommendation_reason` |
| `orchestrator/supervisor.py` | 636 | Phase 1.75 LLM 初筛 | `semantic_filter` |
| `orchestrator/supervisor.py` | 685, 849 | ReAct 编排器 | `react_orchestrator` |
| `orchestrator/graph.py` | 203 | LangGraph 语义筛选 | `graph_semantic_filter` |
| `main.py` | 56 | 在线探活/搜索 | `course_recall` |
| `agents/course_recall_agent.py` | 27 | 在线召回向量搜索 | `course_recall` |
| `scripts/backfill_milvus_vectors.py` | 86 | 离线批量回填 | `backfill` |
| `scripts/ingest_course_dataset.py` | 64 | 数据导入 | `backfill` |

### 5. `python/services/__init__.py`

导出 `LLMTaskName`，加入 `__all__` 和 `__getattr__`。

## Debug 结论

- **无 Debug 问题**：本轮是纯功能新增，所有改动通过语法检查和测试验证。

## 测试与验证

- **语法检查**：`python -m compileall` 涉及的全部文件通过 ✅
- **单元测试**：`python -m pytest tests/ -m "not slow" -v` → **53 passed, 1 deselected** ✅
- **Docker 重建**：`docker compose -f docker-compose.python.yml --profile python up -d --build python-api` 成功，启动日志确认 `langsmith.tracing_configured enabled=True`，8 个 keys 双命名空间写入 ✅
- **端到端推荐**：`POST /api/v1/recommend` → HTTP 200，返回 5 门课程，`experiment_group=react`，`total_latency_ms=90477`，链路日志完整 ✅
- **未执行**：LangSmith UI 上查看 trace 名称变更（需要用户自行刷新确认）

## 经验与后续

- **本轮经验**：
  - `Runnable.with_config({"run_name": "..."})` 是 LangChain 官方推荐的注入 trace 名称方式，相比直接设置 `name` 属性更可靠。
  - `bind_tools` 返回的 `RunnableBinding` 会丢失外层 `with_config`，需要在 `bind_tools` 之后再调用 `with_config`。
  - `@traceable` 装饰器在函数定义时绑定，无法通过实例化不同参数获得不同名称 —— 需要运行时动态绑定：`traceable(name=...)(method)`。
  - Embedding 和 LLM 的 trace 名称注入机制不同：LLM 走 `config.run_name` → `on_chat_model_start(name=...)`，Embedding 走 `@traceable(name=...)`。
- **后续建议**：
  - Docker 重建后用户到 LangSmith UI 的 `multi-agent-course-system` project 下查看 trace，确认每个 LLM 调用显示对应业务名称。
  - 新增 LLM 功能时，务必走工厂并传入 `task_name`，禁止直接 `ChatOpenAI(...)`。
  - 新增 Embedding 功能时，务必走 `build_embedding_client(task_name=...)` 工厂。