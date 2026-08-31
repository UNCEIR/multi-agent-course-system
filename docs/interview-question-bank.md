# 面试追问题库（v2.0.0 重写，28 题）

> v1 时代题库基于 supervisor 双模式 / ReAct 工具 / 硬约束锁死。v2 已升级到 **main_agent（deepagents）统一入口** + 4 业务模块 + 5 MCP 工具 + 知识库 RAG + SSE 续传协议。本题库按 v2 现状重写，每题含「结论 / 证据 / 真实边界」三段。

## 1. 架构设计类（Q1-Q6）

### Q1：为什么用 deepagents 而不是 LangGraph 裸用？
**结论**：deepagents 内置 SkillsMiddleware（渐进式 skill 披露）、SummarizationMiddleware（compaction 五字段摘要）、SqliteSaver（thread_id 跨会话恢复）、FilesystemPermission（禁写 /memories/AGENTS.md）；这些 LangGraph 全要手写。
**证据**：`docs/v2.0.0/plan.md` 决策 2/3；`python/agent/main/factory.py:41-126`；`notes/2026-07-29-phase-0-deepagents-poc详细计划.md`（Phase 0 POC GO）。
**边界**：当前是单实例 SqliteSaver（决策 20）；多实例部署时需要迁 RedisSaver。

### Q2：main_agent 与 v1 supervisor 是什么关系？
**结论**：v1 supervisor 被 main_agent 包装为 `recommend_courses` tool（决策 4）；main_agent 路由入口，supervisor 仍是推荐核心（5 agent 流水线 + 双模式 A/B）。
**证据**：`docs/supervisor-main-orchestration.md` §3.1；`python/tools/recommend/recommend_courses.py`；`chat_intent-2026-08-18.json`（4/4 路由到 recommend_courses）。
**边界**：supervisor.py 55KB 是 v1 时代的资产，未做模块化拆分；v1 历史在 `docs/v1.0.0/`。

### Q3：4 业务模块怎么解耦？
**结论**：
- `recommend_courses` 是**工具**（main_agent 调，包装 v1 supervisor）
- `report` / `evaluation` / `documents` 是**独立 SSE 端点**（main_agent 用 `dispatch_module` 路由）
- `query_knowledge` 是**工具**（直接查 Milvus）

**证据**：`docs/architecture.md` §3 总图；`python/agent/main/specs.py`（MAIN_AGENT_SPEC 工具白名单）；`python/api/{chat,recommend,report,evaluation,documents}.py` 5 个端点。
**边界**：dispatch_module 路由依赖 LLM 正确识别教师端意图；intent_04/05/06/07 修复后通过（路 1 复盘）。

### Q4：为什么用 MCP 而不是直接 HTTP/SDK？
**结论**：MCP 统一"工具即协议"，Python 侧熔断/降级链（CircuitBreaker）直接复用；tavily / 即梦 / e2b 都是 MCP server 暴露，避免每加一个外部能力写一份 SDK 集成。
**证据**：`docs/v2.0.0/plan.md` 决策 21（跨语言通信决策树）；`python/tools/mcp_client.py`；`python/tools/image/jimeng_mcp_server.py`（即梦自建 stdio 包装）。
**边界**：当前是 Python ↔ 外部 MCP；Java 数据服务（决策 22）走 BFF + REST，**不用 MCP**（决策 21 选型表）。

### Q5：决策树怎么选通信形态？
**结论**（决策 21）：
1. 同步请求-响应 → REST/OpenAPI
2. 异步任务/解耦 → RabbitMQ
3. 流式/长连接 → SSE
4. 跨语言工具调用 → MCP

**证据**：`docs/v2.0.0/plan.md` 决策 21 选型表。
**边界**：RabbitMQ 留待任务并发出现；当前 4 种通信形态都通过 Phase 0~3 实装验证。

### Q6：未来 Java 数据服务接入怎么改？
**结论**（决策 22）：前端永远只请求自己的 `/api`；Next.js Route Handlers 在服务端转发到 Python 或 Java；前端对"后端是谁"无感。
**证据**：`docs/v2.0.0/plan.md` 决策 22；`frontend/src/app/api/` 预留空目录。
**边界**：当前 `app/api/` 故意空（**不是 stub**），分线策略：Python SSE 直连、Java REST 走 BFF。

## 2. main_agent + dispatch_module 类（Q7-Q12）

### Q7：main_agent 的 system prompt 怎么写？
**结论**：教师端意图关键词路由表（决策 17）—— 显式列出 4 模块的关键词（成绩单/评语/PPT/图片）→ 必调 dispatch_module；禁止把"成绩单/评语"当知识库问答。
**证据**：`python/agent/main/prompt.py:8-19`；`tests/test_chat_intent_prompt.py` 20 个契约测试（parametrized 关键词覆盖）；`chat_intent-2026-08-18.json` 4/4 通过。
**边界**：prompt 不直接约束"禁止调 query_knowledge"；LLM 偶尔仍会调（chat_intent 路由漂移）—— Phase 4 NLU 调优目标。

### Q8：dispatch_module 的 4 个 intent 怎么设计？
**结论**：用 `Literal` 枚举（`report` / `evaluation` / `ppt` / `image_generate`）—— TypeScript Literal + Python Literal 双向校验，schema 漂移零容忍。
**证据**：`frontend/src/components/system/dispatch_module.ts`（`DispatchModuleInput` Literal）；`tests/test_chat_intent_prompt.py::test_main_agent_routing_module_values_match_intent_enum`；`eval_sets/chat_intent.jsonl` 增 4 个边界 case（路 4）。
**边界**：Literal 枚举 ≥ 4 个（当前正好 4）；新增 intent 需同步改 main_agent prompt + 路由表 + 文档。

### Q9：教师端 4 个失败 case 怎么修的？
**结论**（路 1 复盘 `notes/2026-08-18-chat-intent-4-badcase-fix.md`）：
1. prompt 顶部加"教师端意图关键词路由表"（必须先查）
2. 明确禁止"成绩单/评语/期末报告"当知识库问答
3. dispatch_module 改为**必含**在 MAIN_AGENT_SPEC.allowed_tools
4. 增 4 个边界 case（image_generate / ppt / 多轮上下文 / 跨意图）

**证据**：`python/agent/main/prompt.py:8-19`；`python/agent/main/specs.py:40-55`；`eval/reports/chat_intent-2026-08-18.json`（4/4 通过）。
**边界**：14 个 case 仍未复测；Phase 4 NLU 调优。

### Q10：main_agent 怎么拿 user_id？
**结论**（决策 19）：用 `ContextVar` 注入到 main_agent run，**不**放工具 `args_schema` 里；`/api/v1/chat` 和 `/api/v1/chat/stream` 在调 agent 前后用 `user_context(user_id)` 包装。
**证据**：`docs/v2.0.0/plan.md` 决策 19；`python/agent/main/context.py`（`user_context` / `get_current_user_id`）；`python/api/chat.py:185`（`with user_context(req.user_id):`）。
**边界**：未来个性化/授权工具必须同样模式；**绝不**让 LLM 猜 user_id。

### Q11：意图路由的关键词冲突怎么解决？
**结论**（路 1）：显式优先表 + prompt 顶部路由表；冲突场景（如"成绩单 + 评语"）→ hybrid（intent_20 设计），按顺序执行两个工具。
**证据**：`python/agent/main/prompt.py:8-19`；`eval_sets/chat_intent.jsonl::intent_20`（先查已选课 + 再推荐新课）；`chat_intent-2026-08-18.json`。
**边界**：3 个以上工具的 hybrid 尚未覆盖（intent_21~24 是边界 case，尚未复测）。

### Q12：tools 怎么限流？CORS？安全？
**结论**：ToolRegistry + allowlist 门控 + CircuitBreaker（失败 3 次熔断）；前端 → Next.js rewrites 代理（`next.config.ts`），**不直连 python-api**；CORS 走 Next.js proxy 头部。
**证据**：`python/tools/registry.py`（`register_many` + `get_all(allowed=...)`）；`python/tools/circuit_breaker.py`；`frontend/next.config.ts:6-16`（rewrites）。
**边界**：CircuitBreaker 当前是进程内（decision 4 修订），多实例需 Redis 共享状态。

## 3. 推荐 / RAG 类（Q13-Q18）

### Q13：v1 supervisor 5 agent 流水线怎么工作？
**结论**：画像（LLM 抽 8 维）→ 召回（Redis 候选 ID → MySQL + Milvus 合并）→ 硬约束（纯规则）→ [optional] 语义初筛（LLM）→ 重排（规则预筛 + LLM 精排）→ 可行性（LLM + 规则兜底）→ 流式理由。
**证据**：`docs/supervisor-main-orchestration.md` §4.2；`python/agent/recommend/supervisor.py`；`eval/reports/chat_intent-2026-08-18.json`（intent_01/02/03 smoke 通过）。
**边界**：当前 latency 8-15s（pipeline），react 模式 15-30s。

### Q14：硬约束为什么锁死不可跳过？
**结论**（决策 4 修订）：用户说"只要西校区"时推荐东校区是不可接受的——硬约束过滤在 react 模式中也是唯一不可跳过的工具；编排器在 react 循环结束后强制补调。
**证据**：`docs/architecture.md` §3.2（8 tool 锁死）；`python/agent/recommend/react_tools.py`（hard_constraint_filter 必调）；`notes/2026-08-09-recommend-react-optimization-and-skill-tools.md`。
**边界**：仅 hard_constraint 锁死；其他 6 个 tool 可选（re-rank / course_feasibility 等 LLM 决定）。

### Q15：query_knowledge 怎么分区？
**结论**（决策 6 修订 + 19）：Milvus `document_chunks` 按 `user_id` 分区——`public`（学生手册）+ 当前 user（个人成绩单）；个人数据**不**进共享检索。
**证据**：`docs/v2.0.0/plan.md` 决策 19；`python/storage/milvus/document_vector_repo.py`（分区查询）；`python/scripts/ingest_student_handbook.py`（public）+ `ingest_transcript_desensitized.py`（per-user）。
**边界**：kb_retrieval live 0/3（标注与真实 chunk_id 不匹配）；context_precision 0.933 反证检索质量高。

### Q16：context_recall 怎么测？
**结论**（eval-system.md §4）：标注集标注"应命中的 chunk_id"，跑 live 后对比 top-k 返回是否包含；当前 3 个 case recall@5 = 0.14/0.38/0.33（标注重写中）。
**证据**：`python/eval_sets/kb_retrieval.jsonl`（标注为 `handbook_chunk_*` 虚拟）；`eval/reports/kb_retrieval-2026-08-17.json`；`refresh_kb_retrieval_oracle.py`（采集真实 chunk_id 工具）。
**边界**：标注为手写 stub，**不是真实评测**；Phase 4 需用 `refresh_kb_retrieval_oracle.py` 重写。

### Q17：RAG 怎么避免新旧知识干扰？
**结论**：`delete_by_dataset(dataset_id)` + `replace_chunks` 以 dataset 为单位整体替换；重跑摄入即清理旧版本。
**证据**：`docs/v2.0.0/plan.md` §"增量更新与旧知识干扰规避"；`python/storage/mysql/document_repo.py`（`replace_chunks` 实现）。
**边界**：单文档删除可能误伤同 dataset 内其他 chunk（dataset 级别隔离）。

### Q18：Redis 缓存候选 course_id 还是完整对象？
**结论**：**只缓存 course_id**（候选 id 列表），完整对象从 MySQL 取——避免缓存与数据库不一致。
**证据**：`docs/v2.0.0/plan.md` 决策 4 修订 + AGENTS.md；`python/storage/redis/recall_cache_repo.py:105`（`Redis-backed cache for recall candidate course IDs`）。
**边界**：Redis 不可用时降级到 MySQL 全量扫描（`course_recall_agent.py` fallback）。

## 4. 报告 / 评价 反幻觉类（Q19-Q23）

### Q19：评价反幻觉怎么实现？
**结论**（路 3 实装）：5 层直接管线（不用 ReAct）：
1. 快照：拉学生成绩单（MySQL）
2. 雷达：5 维提案（3 维固定 + 2 维 LLM）
3. LLM 评语：按 comment_type 4 种驱动
4. 反幻觉核验：**评语中引用的数值必须来自 snapshot**（reference.assertion 拦截）
5. 落库：evaluation_records

**证据**：`docs/code-walkthrough.md` §3.2；`python/agent/evaluation/service.py`；`eval/reports/evaluation_comment_live-2026-08-17.json`（6/6 通过）。
**边界**：如果 LLM 生成的评语中引用了 snapshot 没有的数值，reference.assertion 拦截 → 评语降级或重生成。

### Q20：加权公式怎么定？
**结论**（决策 5 修订）：`weighted = 0.3 × display + 0.7 × exam + bonus`——日常分占 30%、考试分占 70%、bonus 是教师加分项。
**证据**：`python/tools/report/compute_weighted_grade.py`（路 3 实装）；`eval/reports/evaluation_comment_live-2026-08-17.json`（学生 3123003252 加权均分 **85.85**）。
**边界**：bonus 当前是简单加法；未来可能按权重叠加。

### Q21：4 种 comment_type 的差别？
**结论**：`semester_summary`（学期总结）/ `encouragement`（鼓励寄语）/ `improvement_advice`（改进建议）/ `recommendation`（学业推荐）—— 4 种 prompt 模板 + 4 种 LLM 行为。
**证据**：`python/tools/evaluation/generate_comment.py`（4 种 prompt）；`python/eval_sets/evaluation_comment_live.jsonl`（6 个 case 覆盖 4 种 + no_transcript_data）。
**边界**：4 种 comment_type 都用同一反幻觉核验；未来加第 5 种需同步改 prompt + 数据集 + 路由。

### Q22：report 怎么保证教师 Excel 字段映射？
**结论**：Phase 1 决策 5 修订——openpyxl 解析 + 列名归一化（"高数"/"高等数学"/"Math" → subject_id）；异常科目标 `unmapped_subject[]` 警告，**不**拒绝整批。
**证据**：`docs/v2.0.0/plan.md` 决策 5 修订；`python/agent/report/service.py`（`inspect_score_excels` → `merge_students`）；`eval/reports/report_math_live-2026-08-18.json`（2/2 真实样本 37 学生全成）。
**边界**：教师 Excel 列名差异大时归一化失败 → 警告但继续（不阻断整批）。

### Q23：SSE 中断后能续传吗？
**结论**（路 2）：能。后端 `EventBuffer` 用 Redis `INCR` 全局自增 + `LPUSH+LTRIM` 环形缓冲（max 100 条 + TTL 30min）；客户端 `Last-Event-ID` header 触发 `EventBuffer.replay_from()` 回放缺失事件。
**证据**：`docs/code-walkthrough.md` §6.1；`python/services/sse_event_buffer.py`（16 个单测）；`frontend/src/lib/sse.ts`（`consumeSSEWithRetry` 指数退避 500ms→1s→2s）。
**边界**：环形缓冲 100 条——长生成（>100 events）超出范围会丢老事件。

## 5. 前端 / SSE 类（Q24-Q28）

### Q24：为什么用 SSE 而不是 WebSocket？
**结论**（决策 21）：SSE 单向推送 + 自动重连 + HTTP 兼容；WebSocket 留给双向交互场景（后续评估）；当前业务是"AI 单向推 token 给前端"，SSE 更简单且生态成熟。
**证据**：`docs/v2.0.0/plan.md` 决策 21 选型表；`docs/architecture.md` §"主要 API"。
**边界**：WebSocket 适合"前端 + 后端实时双向"（如协作编辑），当前业务不需要。

### Q25：前端流式输出卡顿怎么优化？
**结论**（路 2 + 决策 4）：3 个优化点
1. `EventBuffer` LPUSH+LTRIM 环形（避免累积）
2. 客户端 `requestAnimationFrame` 节流 flush（O(N) → O(1) per token）
3. 取消按钮暴露（AbortController UI）—— 避免长生成时用户干等

**证据**：`docs/v2.0.0/plan.md`；`notes/2026-08-18-phase3-sse-resumability-and-cancellation.md`（路 2）；`StreamView.tsx`（`scheduleFlush` + `requestAnimationFrame`）；`tests/components/StreamView.spec.tsx`（11 个单测覆盖取消 + rAF）。
**边界**：rAF 在 jsdom 里不触发 → 单测用 `findByRole({ timeout: 3000 })` 等待。

### Q26：为什么抽 CourseFields 共享层？
**结论**（路 7）：CourseInlineCard + recommend/CourseCard 共享 ~80% 字段（teacher/credits/campus/time_slot + 7 tags），双份维护成本高 + a11y 行为漂移风险（路 6 已暴露）；抽 CourseFields 用 `variant: 'inline' | 'card'` 切换样式风格。
**证据**：`docs/v2.0.0/frontend-architecture.md`（路 7）；`components/CourseFields.tsx`；`tests/components/CourseFields.spec.tsx`（18 个单测）。
**边界**：CourseFields 不含外层 a11y（role/aria-label）+ 独有字段（序号 / 评分 Tooltip / match_reasons）—— 父组件负责。

### Q27：3 套错误反馈怎么统一？
**结论**（路 3）：3 套散落（`message.error` toast / `<Text type="danger">` inline / StreamView 红 panel）→ 2 套统一（`useNotify().toast.*` + `useNotify().inline.*`）。
**证据**：`docs/v2.0.0/plan.md` 决策 17 + 路 3 复盘；`lib/api/useNotify.ts` + `lib/api/useApi.ts`；`tests/lib/{safeCall,useNotify,useApi}.spec.tsx`（26 个单测）。
**边界**：antd `<App>` context 必须包住 layout（不包则 antd message 警告）；6 个 page + 1 个 login 全替换完成。

### Q28：docker host→container 转发为什么 502？
**结论**（路 5）：docker desktop 转发层 bug——`localhost` 偶发 502；`127.0.0.1` 强制 IPv4 解析能减少但不能根治。
**证据**：`notes/2026-08-18-phase3-live-eval-docker-rebuild.md`；`frontend/next.config.ts:3`（`API_PROXY_TARGET=http://127.0.0.1:8000`）；`docker-compose.yml`（frontend service profiles: ["frontend"] + `API_PROXY_TARGET=http://python-api:8000` 容器内直连）。
**边界**：dev proxy 502 是 Docker Desktop 转发问题，**不**在 Next.js / FastAPI 代码层面能根治；用 frontend 容器化绕开。

---

## 答题模式

每题用「结论 / 证据 / 真实边界」三段：
- **结论**：一句话答案（不超过 30 字）
- **证据**：1-2 个代码文件路径 + 行号 / 接口路径 / eval report / 复盘笔记
- **真实边界**：1 句"还差什么 / 不能讲什么"——这是拿 offer 的关键（面试官会立刻追问你的边界）

如果被追问"具体行号 / 具体值"——直接打开 `docs/code-walkthrough.md` 找证据链接。
