# pi 模型层/认证/服务端托管/eval 新增探索 → 本项目移植评估（2026-09-01）

> 研究目标：在已完成「记忆/compaction」「Skill/Tool/Harness」两轮调研后，**自行深挖 pi 此前未覆盖的模块**
> （模型目录、认证解析、服务端托管 agent、prompt 缓存、配置纪律、eval 体系），评估对本项目的移植价值。
> 来源：本会话直接只读阅读 `E:\Agent\pi` 对应源码（model-catalog / auth / server / openai-prompt-cache /
> constrained-sampling / coding-agent config / evals）。
> 关联：`2026-08-31-pi-memory-compaction-mapping.md`（记忆/compaction）、`2026-09-01-pi-skill-tool-harness-mapping.md`（Skill/Tool/Harness）。

---

## 1. 新增探索结论（按移植价值排序）

| # | pi 模块 | 机制 | 本项目移植价值 |
|---|---|---|---|
| **A** | `packages/ai` **Model catalog / 模型元数据** | 每个模型类型化元数据：`id / name / cost(input+output 阶梯价 tiers.inputTokensAbove) / contextWindow / maxTokens / headers / supportsReasoningEffort / maxTokensField / requiresToolResultName / supportsUsageInStreaming`；`flattenModelCatalog` 把「provider × 模型组」拍平成 ID→Model 映射 | **高**：压缩阈值/成本/容错现在硬编码（`agent_context_window_tokens=128000`）；按模型 catalog 一处配置全链生效（每模型 contextWindow + reserve/keep + 成本统计） |
| **B** | `packages/ai/auth/resolve.ts` **认证解析纪律** | `resolveProviderAuth`：**凭据库拥有 provider；ambient/env 只在无存储时兜底；刷新失败后绝不静默回退**；`overlayEnvAuthContext` 支持按请求覆盖；`ModelsError` 带类型化 code（model_source/model_validation/provider/stream/auth/oauth） | **中高**：LLM 客户端单 provider，故障难结构化；类型化错误码 + 「刷新失败不静默回退」可直接映射为 SSE 结构化 `error` 事件，缓解「SSE 卡住=配额」排查 |
| **C** | `packages/server` **服务端托管 agent** | supervisor + RPC 实例注册表 + SSE subscribers + `instances.json` 持久化；`SESSION_METADATA_COMMANDS` 纪律——**只在会改变身份/会话元数据的命令（new_session/switch_session/fork/clone/rename/prompt）后才刷新持久化会话元数据** | **中（未来）**：为将来 Java BFF/多服务铺路：实例/会话注册表 + 「仅 mutating 命令后刷元数据」的 IO 纪律 |
| **D** | `packages/ai/api/openai-prompt-cache.ts` | prompt cache key 截断（`clampOpenAIPromptCacheKey` ≤64 字符）；一次性摘要请求 `cacheRetention:"none"` 不写缓存 | 中：摘要/compaction 请求不写缓存（压缩落库时用） |
| E | `coding-agent/config.ts` | `APP_NAME` 前缀环境变量（`PI_CODING_AGENT_DIR` / `PI_CODING_AGENT_SESSION_DIR`）+ `expandTildePath` + `PI_PACKAGE_DIR` 覆盖 | 低：settings.py 已用 pydantic env；可补 tilde 展开小优化 |
| F | `packages/evals` | eval 以**代码 + 夹具**形式跑（`*.eval.ts`），非 JSONL 断言 | 中：我们 eval 是 JSONL 断言式；可借鉴「eval 即代码 + fixture」的可维护性，但改动面大，暂缓 |

---

## 2. 移植优化方案（pi → 本项目）

### A. 模型元数据目录（推荐优先）

| 项 | 说明 | 涉及文件 | 优先级 |
|---|---|---|---|
| 每模型元数据 | 新 `python/config/model_catalog.py`：`ModelMeta(context_window, max_tokens, cost_input, cost_output, cost_tiers, supports_thinking, max_tokens_field)`；`get_model_meta(model)` 按 `LLM_MODEL` 查 | `python/config/model_catalog.py`(新)、`config/settings.py` | P1 |
| 压缩阈值按模型 | `agent_context_window_tokens` 改为「查 catalog，缺省回退 128000」；`reserve/keep` 同源 | `agent/memory/tokens.py`(新，见记忆文档 P0)、`factory.py` | P0（依赖记忆 P0） |
| 成本记账 | compaction/会话 usage 按 catalog cost 计算 `cost_total`，落 `usage_json`/`chat_session_compactions.usage_json` | `storage/mysql/chat_session_repo.py`、`agent/memory/compaction.py` | P1 |
| 容错（预留） | 未来多 provider 时：模型 ID→provider 静态映射 + provider 级 failover（catalog 是第一步） | — | P3 |

### B. 认证解析纪律 + 类型化错误码

| 项 | 说明 | 涉及文件 | 优先级 |
|---|---|---|---|
| 类型化 LLM 错误码 | `ai/llm_client.py` 抛错带 code（`provider/stream/auth/model_validation/…`），不静默吞；映射到 SSE `error` 事件 | `ai/llm_client.py`、`services/sse_event_buffer.py` | P1 |
| 不静默回退 | LLM key/base_url 刷新失败后**不再静默回退旧值**，显式报错 | `ai/llm_client.py`、`config/settings.py` | P2 |
| 按请求覆盖 | `build_chat_openai` 已支持 model/base_url/api_key 覆盖（与 pi `overrides` 同构，保留） | `ai/llm_client.py` | 现状已具备，P2 补纪律 |

### C. 服务端托管 agent / 会话元数据纪律（未来）

| 项 | 说明 | 涉及文件 | 优先级 |
|---|---|---|---|
| 实例/会话注册表 | 多服务时：后端维护 `agent_instance(instance_id, session_id, status, cwd)` 注册表 + 心跳 | 未来 Java BFF / `sql/init-db.sql` | P3 |
| 仅 mutating 刷元数据 | 只在会改身份/元数据的操作（新建会话/改名/fork）后刷新持久化元数据，避免每次轮询白刷 IO | 未来 BFF | P3 |

### D. Prompt 缓存纪律（顺手）

- 摘要/compaction 等一次性请求 `cacheRetention="none"`（不污染 prompt cache）；需要缓存 key 时 clamp ≤64 字符。涉及 `ai/llm_client.py`、`agent/memory/compaction.py`。优先级 P2。

---

## 3. 落地顺序建议

1. **P0（跟随记忆方案）**：压缩阈值由模型 catalog 驱动（A 与记忆文档 P0 的 `estimate_context_tokens` 同批落地）。
2. **P1**：`model_catalog.py` + 类型化 LLM 错误码 → SSE 结构化 error（B）。
3. **P2**：不静默回退纪律 + prompt cache 纪律。
4. **P3**：服务端托管 agent 注册表（等 Java BFF 立项再做）。

## 4. 一句话结论

本轮新增探索最有价值的是 **A（模型元数据目录）与 B（认证解析纪律/类型化错误码）**：A 把压缩/成本从硬编码变成「按模型一处配置」，B 把「配额耗尽」这类故障变成结构化 error——两者都与前两轮的记忆/工具方案正交、可直接并入 P0/P1 落地；C/D/E/F 价值中低，记录在案待未来（Java BFF / eval 重构）再动。
