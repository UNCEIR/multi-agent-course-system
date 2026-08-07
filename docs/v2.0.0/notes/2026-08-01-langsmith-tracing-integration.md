# LangSmith 全链路 Tracing 集成（AOP 全覆盖）

## 背景与问题

- **用户诉求**：在 LangSmith 平台看不到任何 trace，需要把 tracing 集成到整个系统，让所有涉及 LLM 的接口都能在 LangSmith 监控到链路。要求 AOP 思想，不要每个 Agent 类配置，抽取出来便于以后开发新 LLM 功能直接监控。
- **直接原因**：Docker 镜像没有 `--build`，容器里跑的是旧代码——`tracing.py` 不存在、`main.py` 没调 `configure_langsmith_tracing()`、`settings.py` 没 `langchain_*` 字段。`LANGCHAIN_*` 虽然被 docker-compose 的 `env_file` 注入到容器，但没有任何代码把它们映射为标准 `LANGCHAIN_*` 环境变量，langchain 完全看不到。
- **系统性问题**：即便修复上述问题，Embedding 调用走裸 `httpx`（`OpenAIEmbeddingClient`），是 LangSmith 盲区；且 `langsmith.utils.get_env_var` 有 `lru_cache`，若未来某模块在 import 阶段触发 tracing 读取，env 会被永久冻结为"未设置"，之后 `setdefault` 也无法改变。
- **影响范围**：所有 LLM 调用（5 个 Agent + Supervisor + Graph）均无法在 LangSmith 追踪；Embedding 调用（每次推荐 1 次 `embed_text`）也是盲区。

## 总体架构方案

采用**三个 AOP 单点**覆盖全链路，零侵入 Agent 代码：

| AOP 单点 | 文件 | 覆盖范围 |
|---------|------|---------|
| 配置激活层 | `python/services/tracing.py` | 启动时一次性写入 `LANGCHAIN_*` + `LANGSMITH_*` 双命名空间 |
| LLM 工厂 | `python/services/llm_client.py` | 所有 LLM 调用走 `build_chat_openai` / `build_tool_calling_llm` → `ChatOpenAI` → 自动 trace |
| Embedding 工厂 | `python/services/embedding_client.py` | 底层委托 `langchain_openai.OpenAIEmbeddings` + `@traceable` → 自动 trace |

**关键设计决策**：

- `configure_langsmith_tracing()` 从 `lifespan` 提前到 `main.py` 模块最顶部，在所有 langchain 相关 import 之前执行，彻底杜绝 `lru_cache` 冻结风险。
- 双命名空间写入（`LANGCHAIN_*` + `LANGSMITH_*`），因为 langsmith 0.10.10 的 `get_env_var` 优先读 `LANGSMITH_` 前缀（`namespaces=("LANGSMITH","LANGCHAIN")`）。
- Embedding 迁移到 `langchain_openai.OpenAIEmbeddings`（用户选择），底层走 langchain callback，外层加 `@traceable` 双保险。
- `os.environ.setdefault` 语义保留，允许外部 CI/CD 覆盖。
- v2.0.0 的 deepagents 和 FastGPT MCP 接入后自动覆盖（deepagents 接受外部 `BaseChatModel` 实例，MCP 工具转 `StructuredTool` 走 `Runnable` callback）。

## 细节实现

### 1. `python/services/tracing.py` —— 增强配置激活层

- 新增 `_make_mapping()` 把 settings 的 4 个字段映射为 base name 字典。
- `configure_langsmith_tracing()` 对每个 base name 写入 `LANGCHAIN_*` 和 `LANGSMITH_*` 两个命名空间。
- 新增 `get_tracing_status()` 读 `os.environ`（而非 settings），返回 `{enabled, tracing_v2, project, endpoint, api_key_configured}`，供 `/health` 暴露诊断信息。

### 2. `python/main.py` —— 提前激活 + /health 暴露

- `configure_langsmith_tracing()` 调用从 `lifespan`（第 58 行）移到模块顶部（第 22 行），在 `import orchestrator.supervisor`（触发 `import langchain_openai`）之前。
- `from services.tracing import ...` 只触发 `services/__init__.py`（顶层无 eager import langchain）+ `config/__init__.py`，此 import 链安全。
- `_health_payload()` 新增 `langsmith` 字段，调 `get_tracing_status()`。

### 3. `python/services/embedding_client.py` —— 迁移到 OpenAIEmbeddings

`OpenAIEmbeddingClient` 从裸 `httpx` 实现改为委托 `langchain_openai.OpenAIEmbeddings`：

```python
class OpenAIEmbeddingClient(EmbeddingClient):
    def __init__(self, api_key, model, dimension, base_url, batch_size,
                 timeout_seconds, verify_ssl=True):
        self._lc = OpenAIEmbeddings(
            openai_api_key=api_key,
            model=model,
            dimensions=dimension if dimension > 0 else None,
            openai_api_base=base_url or None,
            chunk_size=max(1, batch_size),
            http_client=httpx.Client(verify=verify_ssl, timeout=timeout_seconds),
            check_embedding_ctx_length=False,
        )

    @traceable(run_type="embedding", name="openai.embed_query")
    def embed_text(self, text: str) -> list[float]:
        return self._lc.embed_query(text)

    @traceable(run_type="embedding", name="openai.embed_documents")
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self._lc.embed_documents(texts)
```

- `EmbeddingClient` ABC 接口不变（`embed_text` / `embed_texts`），调用方零改动。
- `@traceable` 是双保险：即便 `OpenAIEmbeddings` 的 `Embeddings` 接口（非 `Runnable`）不自动 trace，装饰器也确保 embedding 作为独立 run 出现。
- `LocalDeterministicEmbeddingClient` 和 `DashScopeMultimodalEmbeddingClient` 保持不变。

### 4. `python/tests/test_tracing.py` —— 3 → 6 个测试

新增：
- `test_configure_langsmith_tracing_maps_settings_to_both_namespaces`：验证双命名空间写入
- `test_get_tracing_status_enabled`：验证 tracing 激活后状态正确
- `test_get_tracing_status_disabled_without_api_key`：验证无 api_key 时 enabled=False
- `test_get_tracing_status_falls_back_to_langchain_namespace`：验证 LANGSMITH_* 未设置时 fallback 到 LANGCHAIN_*

fixture 更新：清理范围从 `LANGCHAIN_*` 扩展到 `LANGCHAIN_*` + `LANGSMITH_*` 双命名空间。

### 5. `CLAUDE.md` —— 更新 LangSmith Tracing 章节

- 标注三个 AOP 单点（配置激活层 + LLM 工厂 + Embedding 工厂）。
- 记录 `configure_langsmith_tracing()` 必须在 import langchain 前调用。
- 记录 v2.0.0 deepagents/FastGPT 自动覆盖机制。
- 常见陷阱新增："Docker 改 tracing/embedding 代码后必须 `--build`"。
- 核心文件表更新 `tracing.py` 和 `embedding_client.py` 的描述。

## Debug 结论

- **根因**：Docker 镜像未重建，容器跑旧代码。`tracing.py` 不存在于容器内，`main.py` 无 `configure_langsmith_tracing()` 调用，`settings.py` 无 `langchain_*` 字段。
- **排查证据**：
  - `docker exec ... ls /app/services/tracing.py` → 不存在
  - `docker exec ... grep configure_langsmith_tracing /app/main.py` → 无匹配
  - `docker exec ... grep langchain_ /app/config/settings.py` → 无匹配
  - 容器日志无 `langsmith.tracing_configured`
  - 但 `LANGCHAIN_*` 环境变量存在（被 `env_file` 注入）
- **解决方式**：`docker compose -f docker-compose.python.yml --profile python up -d --build python-api` 重建镜像。

## 测试与验证

- **单元测试**：`python -m pytest tests/ -m "not slow" -v` → **53 passed**（含 6 个 tracing 测试）。
- **语法编译**：`python -m py_compile main.py services/tracing.py services/embedding_client.py` → 通过。
- **Docker 重建**：镜像构建成功，容器启动。
- **启动日志**：`langsmith.tracing_configured enabled=True project=multi-agent-course-system` 正常输出，8 个 keys 全部写入。
- **/health**：`langsmith.enabled=true`，`project=multi-agent-course-system`，`api_key_configured=true`。
- **/api/v1/recommend**：HTTP 200，推荐 5 门课程，`experiment_group=react`，`total_latency_ms=116174`。
- **LangSmith trace 上报**：容器日志中 `langsmith.tracing_configured` 确认配置已激活，`LANGCHAIN_TRACING_V2=true` 生效，后续 LLM 调用会随 langchain callback 自动上报到 `multi-agent-course-system` project。需在 LangSmith UI 刷新查看。

## 经验与后续

- **本轮经验**：
  - Docker 是最大坑——改完代码没 `--build`，查了半天的 lru_cache 时序风险、import 链路、langchain 源码，最后发现是容器里跑旧代码。这是 CLAUDE.md 已记录的陷阱第一条，但不踩一次记不住。
  - `langsmith.utils.get_env_var` 的 `lru_cache` 是真实风险：实测 import 阶段不触发 `TRACING_V2` 读取（只读了 `RUN_COMPRESSION_LEVEL` 和 `RUN_COMPRESSION_THREADS`），但未来代码变化可能引入。把 `configure_langsmith_tracing()` 提前到 `main.py` 最顶部是"防御性正确"的做法。
  - langchain 1.x 没有 `langchain_core/settings.py` 单例——tracing 开关是每次 `_configure` 时动态调 `tracing_is_enabled()`，但最终落到 `lru_cache` 的 `get_env_var`。`Client.__init__` 用 `_get_langsmith_env_var_uncached`（无缓存），所以 client 配置不受 lru_cache 影响。
  - `@traceable` 装饰器是给非 `Runnable` 函数（如裸 httpx embedding）加 trace 的最简方案，比迁移到 `OpenAIEmbeddings` 侵入小，但用户选了后者更彻底。
  - `os.environ.setdefault` 的语义要理解清楚：外部已设的 env 不会被覆盖，这是特性不是 bug。
- **后续建议**：
  - 到 LangSmith UI 的 `multi-agent-course-system` project 下查看 trace，确认看到完整 LLM 调用链（Supervisor → 各 Agent）+ embedding run。
  - v2.0.0 接入 deepagents 时，确保 `create_deep_agent(model=build_chat_openai(...))` 传工厂实例，不要直接 `ChatOpenAI(...)`。
  - v2.0.0 接入 FastGPT MCP 时，工具调用边界自动 trace，但 FastGPT workflow 内部是 TS 侧黑盒——若需内部观测，需在 FastGPT 侧另接。
  - 离线 embedding 脚本（ingest/backfill）不在请求链路中，未接入 trace，这是有意的（trace 了也是噪音）。