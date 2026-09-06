# Phase 4 总设计（v2.0.0 Master Design）— 深度增强

> 输入依据：
> - `docs/v2.0.0/plan.md` Phase 4（深度增强，**剔除 FastGPT 相关项**）
> - `docs/v2.0.0/eval-system.md`（评测体系总述：6 集 + LLM-as-judge 预留）
> - pi 移植三份 notes：`2026-08-31-pi-memory-compaction-mapping.md`、`2026-09-01-pi-skill-tool-harness-mapping.md`、`2026-09-01-pi-model-auth-server-mapping.md`
> - 代码 grep 的 Phase 4 预留项：`eval/runner.py --judge` 占位、`observability/metrics.py` 内存收集（注释"swap to Prometheus"）、`requirements.txt` 已含 prometheus-client、kb_retrieval 标注待重写、BFF（决策 22）预留
>
> 版本：2026-09-01（v1.2：v1.1 按 4 份初评修正；v1.2 按 2 份复评收敛——metrics 契约体 / agent_tree 字段级契约与数据来源 / 前端 res.text 消费 / tool result 脱敏；评审决议与已核实代码事实见 `notes/2026-09-01-phase4-review-fixes.md`；编码清单见 `plans/phase4-coding-plan.md`）
> 执行状态：✅ 2026-09-01 已按编码清单实装，验证截至 pytest 全绿 + runner 非 live 断言式；live/judge 真实评估留待后续
>
> 范围排除：**FastGPT 插件市场 / FastGPT KB 桥接一律不进入本设计**（决策：Phase 4 以 deepagents 原生能力 + 自有 MCP 客户端实现同等能力）。

---

## 1. 目标与范围

### 1.1 目标
把 Phase 0~3 从「功能可用」推向「工程深度可验证」：
1. **端到端评测体系**：LLM-as-judge 全量实装（faithfulness / answer_relevancy / rubric），指标矩阵可观测、可对比；
2. **monitor agent 在线表现**：/metrics 监控退化 → 指标驱动检索/推荐策略调优；
3. **多模态**：图片识别已通，补课程图谱可视化、成绩趋势图识别；
4. **agent harness 深化**：think→act→observe 可视化、工具调用链路追踪、subagent 委派树、checkpointing 恢复；
5. **兜底演示**：工具链路断裂（熔断→兜底→部分结果→恢复）、幻觉兜底（schema 拦截→引用→compaction 落盘→隔离）；
6. **pi 移植地基**（并入本 Phase 前置）：压缩落库与 fallback、模型元数据目录、类型化 LLM 错误码、工具横切钩子、意图说明书式 description、每 agent 记忆点。

### 1.2 范围排除（明确不做）
- FastGPT 插件市场、FastGPT KB、FastGPT MCP 桥接（MCP 动态发现用自有 `tools/mcp_client.py` + 外部服务实现）；
- Java 数据服务 / BFF 实装（决策 22 仅预留 `app/api/`，本 Phase 不动）。

---

## 2. 总体架构（新增组件与现有分层关系）

```
┌─ 前端 monitor/ 页面（现有）扩展 ─────────────────────────────┐
│  指标看板（prometheus 渲染）+ harness 可视化（think→act→observe / 委派树 / 课程图谱）│
└──────────────┬─────────────────────────────┘
               │ /metrics（Prometheus 文本格式，复用 8000）+ /api/v1/metrics（冻结 JSON）
┌──────────────▼─────────────────────────────┐
│ observability/                              │
│   metrics.py（MetricsCollector → Prometheus 后端）│
│   prometheus.py（指标注册/导出，v1.1 新增）        │
│   monitor.py（规则式 monitor，v1.1 新增）         │
│   tracing.py（OpenTelemetry 工具调用 span，可选）   │
└──────────────┬─────────────────────────────┘
               │ 埋点：chat/report/evaluation/recommend 四端（v1.1 补齐）
┌──────────────▼─────────────────────────────┐
│ 编排层 agent/  +  能力层 tools/（AgentMiddleware 工具横切钩子）      │
│  压缩落库（chat_session_compactions）+ 记忆分层（agent_name）    │
└────────────────────────────────────────────┘
```

新增/改造模块一览（详见各设计域）：
| 模块 | 职责 | 新建/改造 |
|---|---|---|
| `python/eval/judge.py` | LLM-as-judge 三指标执行器（触发矩阵 + 成本控制） | 新建 |
| `python/eval/runner.py` | `--judge` 实装 + `_live_kb` 断链修复 + NDCG/F1 | 改造 |
| `python/observability/prometheus.py` | MetricsCollector → Prometheus 指标注册/导出 | 新建 |
| `python/observability/monitor.py` | 规则式 monitor（阈值表/调度/告警去重） | 新建 |
| `python/observability/tracing.py` | OpenTelemetry 工具调用 span（可选，见 D） | 新建 |
| `python/config/model_catalog.py` | 每模型元数据（contextWindow/maxTokens/cost） | 新建 |
| `python/agent/memory/{compaction,tokens,summarization_sync}.py` | 压缩落库 + 增量合并 + token 估算 + fallback + 写后同步（middleware 子类） | 新建 |
| `python/agent/middleware/tool_hooks.py` | AgentMiddleware 工具横切钩子（熔断/失败上限/审计） | 新建 |
| `python/tools/registry.py` | 校验三件套；钩子不依赖 `registry.call()` | 改造 |
| `python/storage/mysql/chat_session_repo.py` | compaction/记忆点（agent_name）/usage_json 接口 | 改造 |

---

## 3. 设计域 A：端到端评测体系（LLM-as-judge 全量）

### 3.1 现状与预留（v1.1 修正）
- eval_sets 6 集（chat_intent / report_math / evaluation_comment / kb_retrieval / web_search / image_generate）全 live 可跑，断言式（exact/code/recall）；
- `eval/runner.py --judge` 当前占位（仅打印"未实装"）；
- **断链（已核实）**：`eval/runner.py:343` 仍 `from tools.knowledge.query_knowledge import query_knowledge`（该模块已删）→ `_live_kb` 必崩；
- **触发数据缺失（已核实）**：72/72 case `judge.rubric` 为空、`judge.mode` 无 `llm`、`reference.contexts` 仅 kb 集有 → 触发矩阵受约束；
- kb oracle 已重写为 `handbook_2025_<hash>:N`（commit a4f1549），但 expected 集合过大（kb_04=51、kb_10=71），`|expected| > top_k=5` → recall 结构性不可过 ≥0.6；
- `scripts/import_langsmith_dataset.py` 已把 JSONL 导入 LangSmith Dataset（inputs/outputs/reference）。

### 3.2 设计（v1.1 修正）
1. **`python/eval/judge.py`**：三个 judge 执行器（复用 `ai.llm_client.build_chat_openai` + 各自 `LLMTaskName`，新增 `EVAL_JUDGE`）：
   - `faithfulness(question, answer, contexts) -> score`：逐句核对 answer 陈述是否可被 contexts 支持（防幻觉）；**仅 kb 集触发**（需 contexts）；
   - `answer_relevancy(question, answer) -> score`：answer 是否切题；**全集触发**；
   - `rubric(question, answer, reference, rubric) -> score`：按 case `judge.rubric` 规则打分；**降 P1**（当前 rubric 全空，需 authoring 补规则后启用）。
   - 输出统一 `{score: 0~1, passed: bool, detail}`；LLM 失败 → 结构化 error + 该 case 标记 `judge_failed`（不静默）。
   - **成本控制**：`--judge-model`（默认同主模型）/ `--judge-sample N`（每集采样）/ `--judge-cache`（结果落盘复用）；预算公式 `cost ≈ Σ sample × (in+out tokens) × rate`，超预算显式提示。
2. **`eval/runner.py`**：`--judge` 实装——**先修 `_live_kb` 断链**（切 `query_handbook.ainvoke`，公开 user_id=public 分区，并透出 rank/score 供 NDCG），再按触发矩阵对带 `reference.answer` 的集跑 judge；报告加 `judge` 段（平均分/分档/逐 case/`judge_failed` 计数）。
3. **指标矩阵**（报告 + LangSmith）：
   - 意图识别准确率、工具调用成功率（来自 trace/usage）；
   - 检索：recall@k、precision、F1、NDCG@k（定义见 G1；`_live_kb` 透出 rank/score 后按序计算）；
   - 幻觉率（faithfulness < 阈值占比）、端到端延迟 P50/P95。
4. **kb_retrieval oracle 质量修正**（重定义）：oracle 已对齐真实 chunk_id 体系；**真问题是 expected 集合过大**。修正：① expected 收敛——每 case `|expected| ≤ k`（章节定位 + embedding 语义相似度取 top-k，不再关键词子串全命中）；② 可满足性校验——`scripts/refresh_kb_retrieval_oracle.py` 生成时断言 `|expected| ≤ k`，不满足显式报错；③ 大关键词按语义筛选到目标章节。
5. **验收**：`python eval/runner.py --set kb_retrieval --live --judge` 输出含 faithfulness/answer_relevancy 分；`report_math` / `evaluation_comment` 的 answer_relevancy 分可复现（rubric 待 authoring）。

### 3.3 优先级
P0：judge.py（faithfulness + answer_relevancy）+ runner --judge + 断链修复 + kb oracle 质量修正（需真实 LLM 端测，P0 只保证结构/单测/smoke）。
P1：rubric（需 authoring 补 `judge.rubric`）；NDCG + F1 聚合；LangSmith evaluator 回调（把 judge 结果回写 Dataset）。
P2：指标看板页展示 judge 历史。

---

## 4. 设计域 B：可观测性与 monitor agent 在线表现

### 4.1 现状与预留（v1.1 修正）
- `observability/metrics.py`：内存 `MetricsCollector`（AgentMetric: call_count/success_count/total_latency_ms/errors；business_events）；注释已声明"swap to Prometheus in production"；
- **埋点缺失（已核实）**：`record_agent_call` 仅 `api/recommend.py:69` 调用，chat/report/evaluation 无埋点；
- `requirements.txt` 已含 `prometheus-client>=0.21.0`；前端已有 `/monitor` 页；
- LangSmith tracing 已开启（`ai/tracing.py`）。

### 4.2 设计（v1.1 修正）
1. **`python/observability/prometheus.py`**：`MetricsCollector` 后端切换/并存——注册 Prometheus 指标：
   - `agent_call_total{agent, result}`、`agent_call_latency_seconds{agent}`（Histogram）、`business_event_total{code, phase}`、`sse_stream_latency`、`retrieval_*`（top_k 命中/缓存命中）；
   - **埋点补齐**：chat/report/evaluation 在 agent 完成/失败时 `record_agent_call`（对齐 recommend.py:69 模式）；
   - `/metrics` 端点输出 Prometheus 文本格式（复用 8000）；`/api/v1/metrics` JSON **契约冻结**（v1.2 补契约体）：`{code: 200, success: true, data: {agents: [{name, call_count, success_count, success_rate, avg_latency_ms, errors: []}], business: [{code, phase, count, last_ts}], generated_at}}`（统一信封，字段名/类型/语义写死本文档，前端 `MetricsResponse` 与 C4 测试引用同一契约防漂移）；**前端消费（v1.2）**：`/metrics` 走 `fetch().text()`（Prometheus 文本，不走信封），`/api/v1/metrics` 走 JSON 信封。
2. **monitor agent（规则式）**：`python/observability/monitor.py`（确定性规则，非 LLM）：
   - **阈值表**：每规则定义（指标 / 窗口 / 阈值 / 严重级）；**数据源**：metrics + business_events；**调度**：周期扫描；**告警去重**：同 code+agent 短窗内只发一次；
   - 规则：成功率下降、延迟 P95 超阈、业务 error 突增、LLM 配额类 error（类型化错误码，见 F/D7）；
   - 命中 → 记录告警 + 触发「指标驱动调优建议」：如 kb 检索 top_k / 语义缓存阈值（0.95）/ 分块策略 / rerank 权重——输出为可读建议（人工确认后改配置，不自动改生产）。
3. **验收**：`/metrics` 可被 prometheus 抓取；四端埋点齐；monitor 规则命中「模拟 LLM 配额 error」→ 生成告警与调优建议（去重生效）。

### 4.3 优先级（v1.1 统一）
P1：prometheus 指标注册 + 埋点补齐 + `/metrics` + `/api/v1/metrics` 契约冻结 + 单元测试（**排在工具/记忆 P1-D 之后**，依赖错误码/middleware）。
P1：monitor 规则 + 告警落 `business_events` + 前端 /monitor 展示。
P2：调优建议与配置联动（人工确认）。

---

## 5. 设计域 C：多模态

- **已有**：`image_recognize`（视觉直连，qwen3-vl-plus）、`image_generate`（即梦两段式，B 链）。
- **新增**：
  1. **课程图谱可视化**：`recommend` 结果 → 课程图谱（课程/领域/前置关系）可视化；后端生成图谱 JSON——**不复用 MindMap DSL**（语义不兼容），新结构 `nodes[]: {id(唯一), type: course|domain|prerequisite, label}` + `edges[]: {source, target, relation(枚举: prerequisite|domain_of|related)}`（id 唯一 + 引用完整性校验，v1.2）；新建 `python/tools/mindmap/course_graph.py`；前端新组件 `CourseGraph` 渲染；
  2. **成绩趋势图识别**：`image_recognize` 增强——结构化输出 `{chart_type, series[], points[], trend, confidence, source_image}`（v1.1 补 schema），识别结果必须可溯源到图片否则拒绝（反幻觉），供 evaluation/report 引用。
- **验收**：上传成绩趋势图 → 结构化识别 + 数值可核对；推荐结果可渲染课程图谱。
- **优先级**：P1（识别增强 + 图谱 JSON）；P2（前端可视化打磨）。

---

## 6. 设计域 D：agent harness 深化

### 6.1 现状
deepagents `astream_events` 已透出 token/tool 事件；SSE 路 2 有 id + Last-Event-ID；report 长工具已实时转发（后台 drainer）。

### 6.2 设计（v1.1 修正）
1. **think→act→observe 可视化**：三阶段渲染落 **chat 消费链**（`frontend/src/app/(main)/chat/page.tsx` 或新共享组件 `AgentActivityTimeline`）——`StreamView.tsx` 只消费 recommend 流（无 tool 事件），不承担此职责（v1.1 修正）；复用 SSE text/tool/done 事件，缺 thinking 则仅 act/observe；**tool end 事件需附 result**（observe 载体，后端从 `on_tool_end` `data.output` 提取并摘要化/脱敏后追加到 tool 事件 payload，v1.2）；**前端流切换（v1.2）**：chat 页由 `chatStream` 切 `chatStreamWithRetry`（符合 SSE 优先 *WithRetry 约定）。
2. **工具调用链路追踪**：`observability/tracing.py`（OpenTelemetry 可选）——每个 tool_call 一个 span（tool 名/参数摘要/耗时/结果 isError），LangSmith 已有图级 trace；OpenTelemetry 作为可选导出。**决策：P1 用 LangSmith + 结构化日志即可，OpenTelemetry 后置**（避免过度工程，记入 §13 取舍）。
3. **subagent 委派树**：main_agent 委派 recommend/report/evaluation 时记录 `parent_run_id → child_run_id`，done 事件 `agent_tree` 契约**写死**（v1.2 补字段级类型/可空）：`{run_id: string, name: string, kind: "main"|"subagent"|"tool", status: string, args_summary: string|null, result_summary: string|null, latency_ms: number|null, children: AgentTree[]}`；null 字段前端不渲染，children 缺省 []；**数据来源（v1.2）**：chat.py 在 `astream_events` 捕获 `on_chain_*`/tool 事件的 parent/child run_id 组装（不依赖"已有"）；前端 `types/sse.ts` 显式声明 zod schema 并修正 L9/L200 注释（zod 默认 strip，非"放行未知键"）。
4. **checkpointing 恢复演示**：`/chat` 用 thread_id 恢复已演示；补「中断后重试恢复」脚本（断点续跑，工具幂等，记入 §13）。
- **优先级**：P1（可视化 + 委派树）；P2（OpenTelemetry/恢复演示）。

---

## 7. 设计域 E：兜底演示（断裂 / 幻觉）

### 7.1 工具链路断裂
- **流程演示**：故意断外部工具（如 tavily/即梦 MCP 不可用）→ 工具 middleware 熔断打开（v1.1：钩子在 `AgentMiddleware.wrap_tool_call`，非 `registry.call()`）→ 兜底（`_tavily_fallback` / 本地降级 / 规则兜底）→ 部分结果保留 → checkpointing 恢复 → 降级运行标记（`experiment_group=*_fallback` 已有模式）。
- **产出**：`scripts/demo_tool_fallback.py`（脚本级可复现）+ 前端 error 面展示「降级运行」提示。
- **验收**：熔断 → 兜底 → 恢复全链路日志与状态可核对。

### 7.2 幻觉兜底
- **流程演示**：LLM 试图自算统计 → `args_schema`/校验层拦截（确定性工具强制）→ 引用文件/知识库数值（query_handbook/query_transcript 强制引用）→ compaction 摘要落盘（`chat_session_compactions`）→ subagent 隔离（evaluation/report 独立 spec 无共享上下文）。
- **产出**：eval case（evaluation_comment 已有反例）扩展为「幻觉演示集」。
- **优先级**：P1。

---

## 8. 设计域 F：pi 移植地基（并入 Phase 4 前置）

> 三份 notes 的 P0/P1 落地项汇总（FastGPT 相关剔除；v1.1 补遗漏项）：

| 项 | 说明 | 来源 notes | 优先级 |
|---|---|---|---|
| 压缩落库 + fallback + 写后同步 | `chat_session_compactions` 表 + **SummarizationMiddleware 子类**写后同步（v1.1：不在 chat.py 事后对比）+ `summarize.txt`/`summarization_update.txt` **双模板**增量合并（v1.1：单模板无法注入 `<previous-summary>`）+ 规则式 fallback（LLM 异常被 langchain 吞成 `"Error generating summary..."` 前缀，检测点在 middleware 子类 `_acreate_summary`） | memory-compaction | P0 |
| **压缩读路径（v1.1 补）** | 上下文组装时读取最新 compaction 摘要注入 main_agent（A6/A7 双向闭环，不只写不读） | memory-compaction | P0 |
| token 估算 + `first_kept_seq` | `estimate_context_tokens`（**依赖 `usage_json` 落库前置**，v1.1）+ `should_compact`；**取舍**：pi 的 `retainedTail` 语义映射为本项目 `first_kept_message_id`（记录被保留的首条消息 seq，便于 `list_entries_after_seq` 续读） | memory-compaction | P0 |
| `usage_json` 落库（v1.1 补） | `persist_turn` 提取 `message.usage_metadata` 写 `chat_messages.usage_json`（现状从未写入）→ 压缩/成本记账数据源 | memory-compaction | P0 |
| 模型元数据目录 | `model_catalog.py`：每模型 contextWindow/maxTokens/cost → 压缩阈值 + 成本记账（**M8 cost 记账**） | model-auth-server | P0（依赖压缩 P0） |
| 类型化 LLM 错误码 | `LLMError(code)` + `TypedChatOpenAI(ChatOpenAI)` 子类（v1.1）→ SSE 结构化 error；`api/chat.py` 改 `getattr(exc,"code",…)` | model-auth-server | P1 |
| 工具横切钩子 | **`AgentMiddleware.wrap_tool_call/awrap_tool_call`**（v1.1：`registry.call()` 是死代码）+ block 语义 + 熔断/权限/风控/审计 | skill-tool-harness | P1 |
| 校验三件套 + 同工具失败上限 | 校验错误带字段路径；失败上限计数在**工具 middleware**（v1.1：`agent/main/agent.py` 无主循环）≥3 强制换策略/终止 | skill-tool-harness | P1 |
| 意图说明书 description | description 硬门槛（M6：一句话做什么 + 边界 + 何时用/何时不用点名其他工具，注册校验）；**M7 disable-model-invocation**：编排类工具标注不可被模型直接调用 | skill-tool-harness | P1 |
| 引用 ID 清单 | `details_json` + `<referenced-*>` 引用 ID 清单（v1.1 补：幻觉兜底引用可核对） | skill-tool-harness | P1 |
| isError 契约（M9） | 工具结果统一 `{code, message, isError}`，禁止吞异常当成功 | skill-tool-harness | P1 |
| 每 agent 记忆点 | `chat_memory_entries.agent_name`，每 spec 独立记忆点（v1.1：迁移明细见 §9） | skill-tool-harness / memory | P1 |

> **优先级统一（v1.1）**：prometheus 可观测整体 P1 且排在 P1-D（工具/记忆）之后——三处文档此前打架（总设计 §11 / 编码计划 1.1 / 验收口径），现统一。

---

## 9. 数据模型与接口变更（汇总，v1.1 修正）

| 变更 | 类型 | 说明 |
|---|---|---|
| `chat_session_compactions` | 新表 | summary/prev_compaction_id/first_kept_message_id/tokens_before·after/usage_json/details_json/status/reason |
| `chat_messages.usage_json` | 落库接线 | `persist_turn` 提取 `usage_metadata` 写入（A0 前置，现状零写入） |
| `chat_memory_entries.agent_name` | 加列 | 迁移：INFORMATION_SCHEMA 守卫 → ADD COLUMN（DEFAULT 'main_agent'）→ DROP 旧 `uq_memory_dedup (user_id, kind, content_hash)` → ADD UNIQUE `(user_id, agent_name, kind, content_hash)`；repo 四方法（upsert/list/delete/replace）带 agent_name |
| `config/model_catalog.py` | 新模块 | `get_model_meta(model) -> ModelMeta` |
| `/metrics` | 新端点 | Prometheus 文本格式（豁免 SSE） |
| `/api/v1/metrics` | 契约冻结 | JSON 字段名/类型/语义写死本文档，前端/测试锁定 |
| `eval/runner.py --judge` | 实装 | 消费 judge.py + reference/rubric（触发矩阵 + 成本控制） |
| 工具横切 | 改造 | `AgentMiddleware.wrap_tool_call` 钩子注册点（factory.py middleware 列表）；`registry.call()` 不承载主 agent 路径 |
| `chat_session_repo` | 改造 | `append_compaction/get_latest_compaction/list_memory_entries(agent_name=…)` 等 |

---

## 10. 测试与验收

- **单元**：judge.py 执行器（mock LLM 返回边界分 + 触发矩阵）、prometheus 指标注册/导出、compaction 落库/fallback（前缀+异常两路）/双模板、summarization_sync 子类（事件提取/防抖）、ToolRegistry/middleware 钩子（before block / after 记账/失败上限）、model_catalog 查找回退、`estimate_tokens` 中文系数、`usage_json` 写入断言。
- **API/流**：`/metrics` 内容断言；`/api/v1/metrics` 冻结契约断言；SSE 结构化 error（类型化错误码）消费断言；report/evaluation 既有流测试回归。
- **eval**：`kb_retrieval --live --judge` 出 judge 分；`chat_intent` 工具调用成功率；kb oracle 可满足性（`|expected| ≤ k`）校验。
- **前端**：/monitor 看板（mock 指标）、chat 链 AgentActivityTimeline think→act→observe 渲染、委派树组件、`agent_tree` 契约 zod 校验。
- **回归**：`pytest -m "not slow"` 全绿；前端 lint+test+build 三件套。

## 11. 落地顺序（v1.1 修正：可观测移到工具/记忆之后）

1. **P0（地基）**：usage_json 落库 + 压缩落库+写后同步（middleware 子类）+fallback+token 估算 + model_catalog（F 前四项）；
2. **P0（评测）**：judge.py（faithfulness/answer_relevancy）+ runner --judge + `_live_kb` 断链修复 + kb oracle 质量修正；
3. **P1（工具/记忆）**：AgentMiddleware 工具横切钩子 + 意图说明书 + 每 agent 记忆点 + 类型化错误码；
4. **P1（可观测）**：prometheus 指标 + 埋点补齐 + /metrics + /api/v1/metrics 契约冻结 + monitor 规则（依赖 3 的错误码/middleware）；
5. **P1（多模态/harness）**：成绩趋势图识别 + 图谱 JSON（nodes/edges）+ 委派树/think→act→observe 可视化（chat 链）；
6. **P1（兜底演示）**：断裂/幻觉演示脚本 + eval 反例扩展；
7. **P2**：rubric（authoring）、NDCG/F1 聚合、LangSmith evaluator 回调、monitor 调优联动、前端打磨、OpenTelemetry（可选）。

## 12. 假设与风险（v1.1 修正）

- **假设**：真实 LLM 配额可用（P0 judge/端测需算力）；kb oracle 收敛后 `|expected| ≤ k` 可满足；前端 /monitor 已具备基础壳；`/api/v1/metrics` 冻结契约体以本文档 §4.2 为准。
- **风险**：
  - LLM-as-judge 成本高 → 触发矩阵（faithfulness 仅 kb）+ `--judge-sample/--judge-cache/--judge-model` 控量，预算公式显式提示；
  - `_live_kb` 断链（import 已删 query_knowledge）→ B3 前置修复，smoke 回归；
  - kb oracle expected 过大 → recall 结构性不可过（数学上 `|expected|>k` 时上限 `k/|expected|`）→ B4 收敛 + 可满足性校验；
  - 写后同步竞态/脆弱 → SummarizationMiddleware 子类内同步（不在 chat.py 事后对比）；
  - LLM 异常被 langchain 吞 → fallback 检测点在 middleware 子类 `_acreate_summary`；
  - OpenTelemetry 过度工程 → 默认 LangSmith+结构化日志，OTel 后置；
  - 多模态识别幻觉 → 识别结果必须可溯源，否则拒绝；
  - zod strip 丢弃未声明字段 → agent_tree 契约在前端 `types/sse.ts` 显式声明。
- **排除确认**：FastGPT 相关（插件市场/KB 桥接）全部不在本设计内；`app/api/` BFF 仅预留不实装。

## 13. 取舍与记录在案（v1.1 新增）

P2 及以下项**不静默消失**，统一登记，后续阶段按需排期：
- rubric LLM-as-judge：需先 authoring 补 `judge.rubric`（72/72 现为空）；
- OpenTelemetry 工具 span 导出：P1 用 LangSmith + 结构化日志，OTel 后置；
- monitor 调优自动联动：仅人工确认后改配置，不自动改生产；
- judge 历史看板（P2 指标看板扩展）；
- checkpoint 中断后重试恢复演示脚本；
- openai 引用 ID 清单（`details_json` + `<referenced-*>`）落地到工具结果字段 → **v1.3 已落地**（`_format_tool_result` 输出 `referenced`，见编码计划 D11）；
- **skill 渐进式加载（索引/正文分离 + hasRead 门控 + 加载期校验）= deepagents 原生能力**（`deepagents/middleware/skills.py` progressive disclosure），Phase 1-3 已在用，Phase 4 无需移植（决策记录，v1.3）；
- **M7 disable-model-invocation → v1.3 已提供注册点**（`ToolRegistry.mark_internal`，见编码计划 D10），当前无敏感工具需标记；
- **skills description 意图消歧 → v1.3 已落地**：10 个 `SKILL.md` 补「何时不用」边界 + `tests/test_skills_manifest.py` 加载期校验（见编码计划 D9）；
- pi `retainedTail` → 本项目 `first_kept_message_id` 的语义映射（已在上表说明，勿再引入双命名）。