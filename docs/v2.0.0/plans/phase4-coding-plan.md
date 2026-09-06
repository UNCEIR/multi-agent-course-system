# Phase 4 编码实施计划 — 深度增强（评测 / 可观测 / 多模态 / harness / 兜底 + pi 移植地基）

> 本文档是 `plans/phase-4-master-design.md`（总设计）的**编码执行清单**：按工作流拆解为文件级任务，带依赖顺序与验证命令。编码时以本文件为任务主索引，设计细节（指标定义/表结构/事件协议）回查总设计。
> 日期：2026-09-01（v1.2：v1.1 已按 4 份初评修正；v1.2 再按 2 份复评收敛——A0 流式 usage 落库 / A4 fallback 前缀检测 / metrics 契约体 / agent_tree 字段级契约 / zod strip 注释，评审决议见 `notes/2026-09-01-phase4-review-fixes.md`）
> 状态：✅ 编码完成（2026-09-01）——P0-A/B + P1-C/D/E/F + P2-G 全部实装；验证截至 **pytest `not slow` 全绿（449 passed）+ runner 非 live 断言式 smoke 全过 + 前端 lint/test/build 三件套**；`--live` 与 `--judge` 真实评估按用户要求留待后续（代码已就绪，未跑真实调用）
> 范围排除：FastGPT 相关（插件市场/KB 桥接）不进入任何工作流；`app/api/` BFF 仅预留不实装。

## 一、概览

### 1.1 工作流划分与依赖

```
P0-A 记忆地基（压缩落库+fallback+token+model_catalog+usage_json） ──┬→ P1-D 工具/记忆增强（middleware 钩子/意图/agent记忆点/错误码） ──┬→ P1-F 兜底演示
P0-B 评测（judge.py + --judge + kb oracle 质量修正） ─────────────────┴→ P1-C 可观测（prometheus+/metrics+monitor，排在 P1-D 后）────┴→ P2-G 增强
P1-E 多模态/harness（识别/图谱/委派树/可视化）────────────────────────（可并行）
```

| 工作流 | 内容 | 依赖 | 阶段产物 |
|--------|------|------|---------|
| P0-A | 压缩落库 `chat_session_compactions` + SummarizationMiddleware 子类写后同步 + 双模板增量合并 + 规则式 fallback + `usage_json` 前置落库 + `estimate_context_tokens/should_compact` + `model_catalog.py` | 无 | 压缩可落库、LLM 失败有兜底、usage/阈值/成本按模型配置 |
| P0-B | `eval/judge.py` 三执行器（faithfulness/answer_relevancy，rubric 降 P1）+ `runner --judge` 实装 + `_live_kb` 断链修复 + kb oracle 质量修正 | 无 | LLM-as-judge 可跑（受触发矩阵约束）、oracle 可满足 |
| P1-C | prometheus 指标注册 + 埋点补齐 + `/metrics` + `/api/v1/metrics` JSON 契约冻结 + 规则式 monitor agent | P0-A（cost）、P1-D（错误码/middleware） | `/metrics` 可抓取、monitor 告警+调优建议 |
| P1-D | AgentMiddleware 工具横切钩子（wrap_tool_call）+ 校验三件套 + 同工具失败上限 + 意图说明书 description + `chat_memory_entries.agent_name` + 类型化 LLM 错误码 | P0-A | 工具横切可插拔、描述消歧、每 agent 记忆点、错误结构化 |
| P1-E | 成绩趋势图识别 + 课程图谱 JSON（新 nodes/edges）+ 委派树（agent_tree 契约）+ think→act→observe（chat 链） | 无 | 多模态识别可溯源、前端三阶段流水 |
| P1-F | 工具断裂兜底演示 + 幻觉兜底演示（脚本 + eval 反例扩展） | P0-A/B、P1-D | 可复现演示脚本、反例集 |
| P2-G | NDCG/F1 聚合 + LangSmith evaluator 回调 + monitor 调优联动 + 前端打磨 + OpenTelemetry（可选）+ 取舍记录 | 全部 | 增强与收尾 |

### 1.2 编码纪律

- 所有 ChatOpenAI 构造走 `ai.llm_client.build_chat_openai` + 带 `LLMTaskName`（新增 judge 用 `LLMTaskName.EVAL_JUDGE`）；LLM 层异常统一 `LLMError(code, message)`（D7）
- 工具错误返回结构化 `{code, message}`/`isError`，**禁止吞异常当成功返回**
- 前端新 API 走 SSE（done 终结 + 结构化 error）；`/metrics` 与 `/api/v1/metrics` 除外（Prometheus 文本 / 冻结 JSON 契约，供抓取与看板）
- **user_id 只走 ContextVar / `configurable`，绝不进工具 `args_schema`**；新工具/端点沿用
- **记忆点/压缩摘要一律落 DB**（`chat_memory_entries` / `chat_session_compactions`），**不写 `python/memories/AGENTS.md`**（该文件只读作全局长期记忆）
- 测试 marker 只用既有 `unit/integration/slow/agent/api`；`config.get_settings()` mock 须完整
- 每工作流结束跑对应验证命令；P0-A/B 起每步保持 `cd python && python -m pytest tests/ -m "not slow" -q` 全绿；前端改动每步 `npm run build` 通过

---

## 二、工作流 P0-A：记忆地基（压缩落库 + fallback + model_catalog）

**目标**：短期 checkpoint 塞满时 compact 汇总落库到 `chat_session_compactions`（自包含行），LLM 失败有确定性兜底，压缩阈值/成本按模型 catalog 配置。

> 评审修正（v1.1）：写后同步**不能**放 chat.py 事后对比（竞态/脆弱），必须子类化 deepagents `SummarizationMiddleware`（`summarization_sync.py`）；`chat_messages.usage_json` 目前从未写入（`persist_turn` 未传参，repo 的 `append_message(..., usage_json=None)` 形参空挂）→ A3「provider usage 优先」无数据源，新增 A0 前置任务。

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| A0 | `usage_json` 前置落库 | `python/agent/memory/persistence.py`、`python/api/chat.py`、`python/storage/mysql/chat_session_repo.py` | `persist_turn` 增 `usage_metadata` 参数并提取 `message.usage_metadata`（prompt/completion/total tokens）→ 序列化传 `append_message(..., usage_json=...)`；**流式路径（v1.2）**：`/api/v1/chat/stream` 的 usage 聚合在 `_generate()` 局部变量（`on_chat_model_end` 累积），done 前 `persist_turn(..., assistant_msgs=[{...}])` 传的是纯 dict 无 usage → 由 chat.py 把聚合 usage dict 显式传入 `persist_turn`（非流式 `/api/v1/chat` 传 `last`=AIMessage 的 usage_metadata）；补 `tests/test_chat_session_repo_sql.py` 断言 usage_json 可读回；A3 与 C1 成本记账的数据源 |
| A1 | `chat_session_compactions` 表 | `sql/init-db.sql` | `id PK, user_id, session_id, summary MEDIUMTEXT, prev_compaction_id, first_kept_message_id, tokens_before, tokens_after, reserve_tokens, keep_recent_tokens, model, reason('threshold'\|'overflow'\|'manual'\|'fallback'), status('ok'\|'failed'\|'aborted'\|'fallback'), usage_json, details_json, created_at, INDEX(user_id, session_id, created_at)`；列存在性迁移守卫（对齐 report_uploads 模式） |
| A2 | repo 接口 | `python/storage/mysql/chat_session_repo.py` | `append_compaction(...)` / `get_latest_compaction(session_id)` / `list_compactions(session_id)` / `list_entries_after_seq(session_id, seq)` |
| A3 | token 估算 | `python/agent/memory/tokens.py`（新） | `estimate_context_tokens(messages)`（**依赖 A0 写入的 usage_json.total_tokens 优先**，缺失时字符估算：中文按 `chars/2`、英文按 `chars/4`）+ `should_compact(tokens, window, reserve)` 单点决策；单测两路（mock usage / 纯字符） |
| A4 | 压缩 middleware 子类（写后同步 + fallback） | `python/agent/memory/summarization_sync.py`（新）、`python/agent/main/factory.py` | 子类化 deepagents `SummarizationMiddleware`，在 `factory.py` 替换原装配（**factory.py 的 `SummarizationToolMiddleware(summarization)` 第二项必须同步传子类实例**，v1.2）：① 覆写 `awrap_model_call`：从返回值 `_summarization_event`（含 cutoff_index/summary_message/file_path）取摘要 → 写后同步（A6）；② **fallback 检测点（v1.2 修正）**：deepagents/langchain 把 LLM 异常吞成 `"Error generating summary: ..."` 前缀字符串返回、**不会冒泡**——子类里 `except` 捕获 LLM 异常是死路；主检测点 = 覆写 `_acreate_summary`（或 `awrap_model_call`）检查 `super()` 返回值 / `summary_message.content` 的该前缀 → 规则式截断（最旧 N 条 + 保留最近）+ `status='fallback'`；③ 防抖/单次恢复：同 session 短窗（60s）内不重复触发，恢复后重置 |
| A5 | 增量合并模板（双模板） | `python/agent/main/prompts/summarize.txt` + `summarization_update.txt`（新） | 单模板无法注入 `<previous-summary>` → **覆写 `_acreate_summary` 二选一**：首轮用六节 `summarize.txt`（移植 pi `SUMMARIZE_PROMPT` 六节）；已有 compaction 用 `summarization_update.txt`（保留/添加/更新/可删规则 + `<previous-summary>` 占位）；**旧 `prompts/summarization.txt` 去向（v1.2）**：factory.py `_load_summarization_prompt()` 现读旧文件（决策 11 五字段）——过渡为 `summarize.txt` 后旧文件废弃、读取路径改指向新首轮模板，避免双模板与读取打架 |
| A6 | 写后同步 + 读路径 | `python/agent/memory/summarization_sync.py`、`python/agent/main/context.py`、`python/agent/memory/injector.py` | **写路径**：middleware 子类从 `langgraph.config.get_config()["configurable"]` 取 thread_id/user_id → `append_compaction` **先落库成功再推进**（失败仅告警不阻塞）；**读路径（v1.1 补）**：上下文组装时（main_agent 首轮/续轮注入）读取 `get_latest_compaction(session_id)` 摘要注入（双向闭环，避免只写不读）；**续轮挂载点（v1.2）**：`inject_memory_entries` 首轮后即 `return None`、chat.py 仅首轮调用一次——续轮 compaction 摘要注入以 chat.py messages 组装点为唯一入口显式追加 |
| A7 | 模型 catalog | `python/config/model_catalog.py`（新） | `ModelMeta(context_window, max_tokens, cost_input, cost_output, cost_tiers)` + `get_model_meta(model)`（缺省回退 128000/8192）；`settings.agent_context_window_tokens` 改为查 catalog |
| A8 | 配置与 trigger 优先级 | `python/config/settings.py` | 增 `agent_compaction_reserve_tokens=16384`；`agent_context_window_tokens` 语义改为「缺省，被 catalog 覆盖」；**trigger 优先级理顺**：`agent_compaction_trigger_messages`（消息数）优先 → 未设置时用 token 阈值 `catalog.context_window - reserve` → `should_compact` 单点决策（不再双路径打架） |
| A9 | 测试 | `python/tests/test_memory_compaction.py`、`test_summarization_sync.py`（新）、`test_model_catalog.py`（新）、`test_chat_session_repo_sql.py`（扩展） | 落库/fallback（前缀+异常两路）/增量合并保留旧节/防抖单次/双模板选择、token 估算两路、catalog 查找与回退、usage_json 写入断言 |

**验证**：
```bash
cd python && python -m pytest tests/test_memory_compaction.py tests/test_summarization_sync.py tests/test_model_catalog.py tests/test_chat_session_repo_sql.py -v
cd python && python -m pytest tests/ -m "not slow" -q
```
**风险卡点**：写后同步必须「先落库成功再推进」且失败不阻塞主流程；fallback 检测点在 middleware 子类内（SSE 层收不到 LLM 异常）；中文 token 估算别用 `chars/4`。

---

## 三、工作流 P0-B：评测（LLM-as-judge 实装 + oracle 质量修正）

**目标**：`--judge` 从占位到实装；修复 `_live_kb` 断链；kb oracle 满足 `|expected| ≤ k` 可满足性。

> 评审修正（v1.1）：① `eval/runner.py:343` 仍 import 已删除的 `query_knowledge` → `_live_kb` 必崩，B3 前置修断链；② kb oracle 已重写为 `handbook_2025_<hash>:N`（commit a4f1549），但关键词子串匹配产生超大 expected 集（kb_04=51、kb_10=71），`|expected| > top_k=5` → recall 结构性不可过 ≥0.6，B4 重定义为「oracle 质量修正」；③ `judge.rubric` 72/72 为空、`judge.mode` 无 llm、`reference.contexts` 仅 kb 集有 → 触发矩阵约束，rubric 降 P1（需 authoring）。

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| B1 | LLMTaskName 增枚举 | `python/ai/llm_task_name.py` | `EVAL_JUDGE = "eval_judge"`（三执行器共用 run name，detail 区分） |
| B2 | judge 执行器 | `python/eval/judge.py`（新） | `faithfulness(q, a, contexts)` / `answer_relevancy(q, a)` / `rubric(q, a, reference, rubric)`；输出 `{score, passed, detail}`；LLM 失败 → 结构化 error + `judge_failed` 标记（不静默）；**触发矩阵**：faithfulness=仅 kb_retrieval（需 contexts）；answer_relevancy=全集；rubric=P1 暂不接（等 authoring）；**成本控制**：`--judge-model`（默认同主模型）、`--judge-sample N`（每集采样）、`--judge-cache`（结果落盘复用）；预算公式 `cost ≈ Σ sample × (in+out tokens) × rate`，超预算显式提示 |
| B3 | runner 实装 --judge + 断链修复 | `python/eval/runner.py` | **前置**：`_live_kb` 的 `from tools.knowledge.query_knowledge import query_knowledge` 改为 `query_handbook`（`handbook.ainvoke({"query": query, "top_k": top_k})`，公开 user_id=public 分区），并透出每命中的 rank/score（G1 NDCG 需要）；先断言式，再按触发矩阵对带 `reference.answer` 的集跑 judge；报告加 judge 段（平均分/分档/逐 case/`judge_failed` 计数）；`--judge` 不再打印占位 |
| B4 | kb oracle 质量修正 | `python/scripts/refresh_kb_retrieval_oracle.py`（**改造既有脚本**，v1.2）、`python/eval_sets/kb_retrieval.jsonl` | 重定义：oracle 已对齐真实 chunk_id；**真问题是 expected 集合过大**。修正：① expected 收敛——每 case `|expected| ≤ k`（按章节定位 + embedding 语义相似度取 top-k，不再关键词子串全命中）；② 可满足性校验——脚本生成时断言 `|expected| ≤ k`，不满足显式报错；③ 大关键词（如「奖学金」）按语义筛选到目标章节 |
| B5 | judge 单测 | `python/tests/test_eval_judge.py`（新） | mock LLM：faithfulness 高/低、answer_relevancy、触发矩阵（无 contexts 不跑 faithfulness）、`--judge-sample/cache` 参数、LLM 失败 → judge_failed |

**验证**：
```bash
cd python && python -m pytest tests/test_eval_judge.py -v
cd python && python eval/runner.py --set kb_retrieval           # smoke 断言器自检（含 _live_kb 断链回归）
cd python && python eval/runner.py --set evaluation_comment     # smoke 自检
# ⏳ live --judge（真实 LLM 端测）算力允许时补跑；rubric 待 authoring 后启用
```

---

## 四、工作流 P1-D：工具/记忆增强（横切钩子 + 意图 + agent 记忆点 + 错误码）

**目标**：工具调用横切可插拔、错误结构化、意图消歧、每 agent 记忆点。

> 评审修正（v1.1）：① `registry.call()` 在主 agent 路径是死代码（deepagents ToolNode 直调 `StructuredTool.invoke`）→ 钩子必须用 **`AgentMiddleware.wrap_tool_call/awrap_tool_call`**；② `agent/main/agent.py` 无主循环 → D4 失败上限计数放工具 middleware；③ D6 需完整迁移明细 + repo 四方法 + `test_chat_session_repo_sql.py`；④ D7 用 `LLMError(code)` + `TypedChatOpenAI` 子类；⑤ D8 测试清单修正（`test_memory_injector.py` 不存在）。

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| D1 | 工具横切钩子（middleware） | `python/agent/middleware/tool_hooks.py`（新）、`python/agent/main/factory.py` | 实现 `AgentMiddleware.wrap_tool_call/awrap_tool_call`：before 返回 `{block, reason} | None`，after 记录 `(ok, latency_ms, error)`；在 `factory.py` middleware 列表注册（main + subagents 可选）；**不依赖 `registry.call()`**（仅测试/直连入口保留）；`ToolRegistry.get_all()/get()` 保持对象同一性（`test_tool_registry.py` 断言 `is` 不破坏） |
| D2 | circuit breaker 接入钩子 | `python/tools/circuit_breaker.py`、`python/agent/middleware/tool_hooks.py` | 熔断检查移入 wrap_tool_call before（block + reason），记账移入 after；工具本体保持纯粹；breaker 状态机不变 |
| D3 | 校验三件套 | `python/tools/registry.py`（或 middleware 内） | 参数校验错误格式：`Validation failed for tool "X": - field.path: reason\nReceived arguments: {...}`；先宽容类型转换再严格校验 |
| D4 | 同工具失败上限 | `python/agent/middleware/tool_hooks.py` | 工具 middleware 内维护「同工具连续失败 ≥3 → 强制换策略或终止」护栏（计数 + 告警落 business_events）；`agent/main/agent.py` 无主循环，不做此处 |
| D5 | 意图说明书 description | `python/tools/knowledge/query_handbook.py`、`query_transcript.py`、`tools/recommend/*` 等 | description 升级「一句话做什么 + 边界 + 何时用/何时不用（点名其他工具）」；`query_transcript` 与 `query_handbook` 互相点名；**M6 硬门槛**：描述缺任一段（做什么/边界/消歧）注册时校验报错 |
| D6 | 每 agent 记忆点 | `sql/init-db.sql`、`python/storage/mysql/chat_session_repo.py`、`python/agent/memory/{injector,extractor,consolidation}.py`、`python/agent/main/specs.py` | `chat_memory_entries.agent_name VARCHAR(64) NOT NULL DEFAULT 'main_agent'`；**迁移明细**：INFORMATION_SCHEMA 守卫查列 → ADD COLUMN → DROP 旧 `uq_memory_dedup (user_id, kind, content_hash)` → ADD UNIQUE `(user_id, agent_name, kind, content_hash)`；存量回填 DEFAULT 'main_agent'；**repo 四方法**带 agent_name：`upsert_memory_entry / list_memory_entries / delete_memory_entries / replace_memory_entries`（SELECT/DELETE 按 user_id+agent_name 过滤）；injector/extractor/consolidation 作用域按 agent_name；`AgentSpec.name` 初始化（subagents 用 spec.name）；`test_chat_session_repo_sql.py` 断言迁移与唯一键 |
| D7 | 类型化 LLM 错误码 | `python/ai/llm_client.py`、`python/api/chat.py` | `LLMError(code, message)` 异常类；`TypedChatOpenAI(ChatOpenAI)` 子类（在 `build_chat_openai` 内构造），LLM 异常统一包 `LLMError(code)`（provider/stream/auth/model_validation/…）；`api/chat.py:287` 现 `code=type(exc).__name__.upper()` → 改 `getattr(exc, "code", type(exc).__name__.upper())`；SSE error 事件携带结构化 code |
| D8 | 测试 | `tests/test_tool_middleware.py`（新）、`tests/test_tool_registry_consistency.py`（扩展）、`tests/test_llm_client_defaults.py`（扩展）、`tests/test_chat_session_repo_sql.py`（扩展） | middleware 钩子 block/记账、失败上限 ≥3、描述点名+硬门槛、agent 记忆点隔离、LLMError code 映射 |
| D9 | skills manifest 加载期校验 | `python/skills/*/SKILL.md`、`tests/test_skills_manifest.py`（新，v1.3 补） | 校验每个 SKILL.md frontmatter：name/description 必填、desc ≤1024、含「何时用/何时不用」消歧信号；**10 个技能 description 已补「何时不用」边界**（对齐 pi B 节） |
| D10 | disable-model-invocation（M7） | `python/tools/registry.py`（v1.3 补） | `mark_internal(name)` / `is_internal(name)` 受控暴露注册点（当前无敏感工具需标记，供后续成绩单写库/审批等接入）；工具横切钩子可据此 block |
| D11 | 引用 ID 清单 | `python/tools/knowledge/_common.py`（v1.3 补） | `_format_tool_result` 输出加 `referenced` 字段（chunk_id/source_doc_name/page_number 清单），幻觉兜底引用可核对（对齐总设计 §8 M9 补充） |

**验证**：
```bash
cd python && python -m pytest tests/test_tool_middleware.py tests/test_tool_registry_consistency.py tests/test_llm_client_defaults.py tests/test_chat_session_repo_sql.py -v
cd python && python -m pytest tests/ -m "not slow" -q
```

---

## 五、工作流 P1-C：可观测性（prometheus + /metrics + monitor）

**目标**：`/metrics` 可被 prometheus 抓取；埋点覆盖 chat/report/evaluation/recommend 四端；monitor 规则命中退化并给出调优建议。

> 评审修正（v1.1）：① 优先级统一——P1-C **排在 P1-D 之后**（依赖 D7 错误码与 D1 middleware 埋点）；② 埋点现状：`record_agent_call` 仅 `api/recommend.py:69` 调用，chat/report/evaluation 缺失 → C1 补埋点任务；③ `/api/v1/metrics` JSON 契约冻结。

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| C1 | Prometheus 指标 + 埋点补齐 | `python/observability/prometheus.py`（新）、`python/api/chat.py`、`python/api/report.py`、`python/api/evaluation.py`、`python/api/recommend.py` | `agent_call_total{agent,result}` Counter、`agent_call_latency_seconds{agent}` Histogram、`business_event_total{code,phase}`、`retrieval_*`；MetricsCollector 并行输出 Prometheus（保留 `/api/v1/metrics` JSON）；**埋点补齐**：chat/report/evaluation 在 agent 完成/失败时 `record_agent_call`（对齐 recommend.py:69 模式） |
| C2 | /metrics 端点 + JSON 契约冻结 | `python/api/metrics.py`（新） | `GET /metrics` → Prometheus 文本（`generate_latest`）；`/api/v1/metrics` **冻结 JSON 契约（v1.2 写死 schema）**：`{code: 200, success: true, data: {agents: [{name, call_count, success_count, success_rate, avg_latency_ms, errors: []}], business: [{code, phase, count, last_ts}], generated_at}}`（统一信封，字段名/类型/语义锁定；C4 与前端 `MetricsResponse` 引用同一契约）；**前端消费（v1.2）**：`lib/api.ts` 新增 `getPrometheusText()` 走 `fetch().text()`（/metrics 不走信封），`getMetrics()` 走冻结 JSON 信封 |
| C3 | monitor 规则 | `python/observability/monitor.py`（新） | **阈值表**（每规则：指标/窗口/阈值/严重级）+ 数据源（metrics + business_events）+ 调度（周期扫描）+ **告警去重**（同 code+agent 短窗内只发一次）；规则：成功率下降 / P95 超阈 / error 突增 / 类型化配额 error（D7）→ 告警（落 business_events）+ 调优建议（top_k/语义缓存阈值/分块/rerank 权重） |
| C4 | 测试 | `tests/test_prometheus_metrics.py`（新）、`test_monitor_rules.py`（新） | 指标注册/导出断言、埋点四端、monitor 命中（模拟指标）+ 告警去重 |

**验证**：
```bash
cd python && python -m pytest tests/test_prometheus_metrics.py tests/test_monitor_rules.py -v
curl -sS http://127.0.0.1:8000/metrics | head -20   # 手动抽查（起服务后）
```

---

## 六、工作流 P1-E：多模态 / harness 深化

**目标**：成绩趋势图识别可溯源；课程图谱 JSON；委派树 + think→act→observe 可视化。

> 评审修正（v1.1）：① E4 目标文件错位——`StreamView.tsx` 只消费 recommend 流（无 tool 事件），三阶段渲染应落 **chat 消费链**；② `agent_tree` done 事件契约未定义 + zod strip 未知字段（实测会被丢弃）→ 契约写死 + `types/sse.ts` 显式声明；③ E2 的 MindMap DSL 不可复用 → 新 nodes/edges 结构。

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| E1 | 成绩趋势图识别 | `python/tools/image/image_recognize.py` | 结构化输出 schema：`{chart_type, series[], points[], trend, confidence, source_image}`；识别结果必须可溯源（引用图片），否则拒绝；识别失败走结构化 error |
| E2 | 课程图谱 JSON | `python/tools/mindmap/course_graph.py`（新，v1.2 明确新建，不再列 mindmap_generator 作候选）+ 新前端组件 `CourseGraph` | **不复用 MindMap DSL**（语义不兼容）→ 新结构：`nodes[]: {id(唯一), type: course\|domain\|prerequisite, label}`、`edges[]: {source, target, relation(枚举: prerequisite\|domain_of\|related)}`（id 唯一 + source/target 引用完整性校验）；推荐结果 → 课程/领域/前置关系图谱 JSON |
| E3 | 委派树（agent_tree 契约） | `python/api/chat.py`（done payload）、`frontend/src/types/sse.ts` | done 事件 `agent_tree` 契约**写死**（v1.2 补字段级类型/可空）：`{run_id: string, name: string, kind: "main"\|"subagent"\|"tool", status: string, args_summary: string\|null, result_summary: string\|null, latency_ms: number\|null, children: AgentTree[]}`（null 字段前端不渲染，children 缺省 []）；**数据来源（v1.2）**：chat.py 在 `astream_events` 捕获 `on_chain_*`/tool 事件的 parent/child run_id 组装（不依赖"已有"）；**前端 zod（v1.2）**：`types/sse.ts` 显式声明 agent_tree 字段，并**修正 L9/L200 注释**——zod `z.object` 默认 strip 丢弃未声明字段（`.passthrough()` 才保留），注释不得再写"默认放行未知键" |
| E4 | think→act→observe | `frontend/src/app/(main)/chat/page.tsx` 或新共享组件 `AgentActivityTimeline.tsx` | 三阶段渲染落 **chat 消费链**；**前端流切换（v1.2）**：chat/page.tsx 现用无重试 `chatStream` → 改 `chatStreamWithRetry`（符合仓库 SSE 优先 *WithRetry 约定）；**tool end 附 result（v1.2）**：后端从 `on_tool_end` 事件 `data.output` 提取 result 追加到 tool 事件 payload，并定义摘要化/脱敏规则（长度上限、敏感字段截断，避免大 JSON/隐私进 SSE）；StreamView.tsx 只消费 recommend 流，不动 |
| E5 | 测试 | 后端 `tests/test_image_recognize.py`（扩展）+ chat stream tool 事件 result 断言；前端 `AgentActivityTimeline.spec.tsx`（新，或 chat 页扩展）+ `CourseGraph.spec.tsx`（新，v1.2） | 可溯源拒绝、图谱 JSON 结构（relation 枚举/id 唯一）、agent_tree 契约、三阶段渲染、CourseGraph 渲染 |

**验证**：
```bash
cd python && python -m pytest tests/test_image_recognize.py -v
cd frontend && npm test && npm run build
```

---

## 七、工作流 P1-F：兜底演示（断裂 / 幻觉）

**目标**：可复现的熔断→兜底→恢复；幻觉拦截→引用→compaction 落盘→隔离演示。

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| F1 | 断裂演示 | `python/scripts/demo_tool_fallback.py`（新） | 断外部工具 → 熔断（D1/D2 middleware 钩子）→ 兜底（_fallback）→ 部分结果保留 → checkpoint 恢复 → `*_fallback` 标记 |
| F2 | 幻觉演示集 | `python/eval_sets/evaluation_comment.jsonl`（扩展）、`eval_sets/README.md` | 补「幻觉演示」反例（自算统计被拦 / 引用缺失拒绝） |
| F3 | 演示脚本单测 | `tests/test_demo_fallback.py`（新，或并入既有） | 熔断→兜底→恢复链路状态断言 |

**验证**：
```bash
cd python && python scripts/demo_tool_fallback.py            # 冒烟
cd python && python -m pytest tests/test_demo_fallback.py -v
```

---

## 八、工作流 P2-G：增强与收尾

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| G1 | NDCG/F1 聚合 | `python/eval/runner.py` | **NDCG 定义**：`DCG@k = Σ_{i=1..k} rel_i / log2(i+1)`，`NDCG@k = DCG@k / IDCG@k`；rel_i 取真实命中（1/0）或检索 score；`_live_kb`（B3）透出 rank/score 供排序计算；报告加 NDCG@k/F1（kb 检索集） |
| G2 | LangSmith evaluator 回调 | `python/scripts/import_langsmith_dataset.py`（扩展） | judge 结果回写 Dataset（evaluator） |
| G3 | monitor 调优联动 | `python/observability/monitor.py` | 建议与配置联动（人工确认后改配置，不自动改生产） |
| G4 | 前端打磨 | `frontend/src/app/(main)/monitor/page.tsx` | 看板渲染 prometheus/monitor 数据（消费 `/api/v1/metrics` 冻结 JSON） |
| G5 | OpenTelemetry（可选） | `python/observability/tracing.py` | 工具调用 span 导出（默认 LangSmith + 结构化日志即可，OTel 后置） |
| G6 | 全量回归 + 文档同步 | `docs/v2.0.0/plans/phase-4-master-design.md`、`AGENTS.md` | 试金石核对、AGENTS.md 状态标注更新 |
| G7 | 取舍记录 | `docs/v2.0.0/plans/phase-4-master-design.md` §13 | 搁置项记录在案（rubric authoring、OTel、调优自动联动、judge 历史看板、checkpoint 中断恢复演示、openai 引用 ID 清单等），不静默消失 |

**验证**：`pytest -m "not slow"` 全绿 + 前端 lint/test/build 三件套 + eval live 抽查。

---

## 九、验收口径（总设计 §10 映射）

- P0 结束：`chat_session_compactions` 可查结构化记录（含 usage_json）；LLM 挂时 `status='fallback'` 上下文不崩；`runner --judge` 输出 judge 分（至少单测/smoke 可跑）；`_live_kb` 断链已修；kb oracle `|expected| ≤ k` 可满足。
- P1 结束：`/metrics` 可抓取 + 埋点四端齐；monitor 命中配额 error → 告警+建议（去重生效）；工具 middleware 钩子 block/记账/失败上限有测试；`query_transcript/query_handbook` 描述互相点名；每 agent 记忆点隔离（agent_name 唯一键）；agent_tree 契约前端可渲染。
- 全绿 = `pytest -m "not slow"` 全量 + 前端三件套 + eval live 抽查（算力允许）。