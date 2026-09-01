# Phase 4 文档多重评审记录与修正决议（2026-09-01）

> 关联文档：`plans/phase-4-master-design.md`（总设计 v1.1）、`plans/phase4-coding-plan.md`（编码计划 v1.1）
> 背景：按用户要求，对 Phase 4 总设计/编码计划并行派出 4 个评审 agent（后端 / 评测 / 前端契约 / pi 对齐）做可行性评审，本 note 记录评审发现、已核实代码事实与修正决议，保证「多重评审 → 优化改正」可追溯。

---

## 1. 评审矩阵与修正落点

| 评审 | 关键结论 | 级别 | 修正落点 |
|---|---|---|---|
| 后端（Meitner） | 写后同步放 chat.py 事后对比竞态/脆弱，须子类化 SummarizationMiddleware | P0 | 编码计划 A4/A6；总设计 §8 |
| 后端 | ToolRegistry `registry.call()` 在主 agent 路径是死代码（deepagents ToolNode 直调 StructuredTool.invoke）→ 钩子用 `AgentMiddleware.wrap_tool_call` | P0 | 编码计划 D1/D2；总设计 §8/§9 |
| 后端 | `chat_messages.usage_json` 从未写入 → A3「provider usage 优先」无数据源 | P0 | 编码计划 A0（新前置任务）；总设计 §8/§9 |
| 后端 | fallback 检测点在 `_acreate_summary` 返回 `"Error generating summary..."` 前缀（LLM 异常被 langchain 吞掉） | 修正 | 编码计划 A4 |
| 后端 | A5 单模板无法注入 `<previous-summary>`，需覆写 `_acreate_summary` 双模板 | 修正 | 编码计划 A5 |
| 后端 | D4 失败上限计数放工具 middleware（agent/main/agent.py 无主循环） | 修正 | 编码计划 D4 |
| 后端 | D6 agent_name 波及 repo 四方法 + injector/extractor/consolidation + SQL 迁移（守卫 + UNIQUE 重建 + 回填）+ test_chat_session_repo_sql.py | 修正 | 编码计划 D6；总设计 §9 |
| 后端 | D7 用 `LLMError(code)` + `TypedChatOpenAI(ChatOpenAI)` 子类 + chat.py `getattr(exc,"code",…)` | 修正 | 编码计划 D7；总设计 §8 |
| 后端 | D8 测试清单修正（`test_memory_injector.py` 不存在） | 修正 | 编码计划 D8 |
| 评测（Poincare） | `eval/runner.py:343` 仍 import 已删除 query_knowledge → `_live_kb` 必崩 | P0 | 编码计划 B3（前置）；总设计 §3.1 |
| 评测 | kb oracle 真问题是关键词子串匹配产生超大 expected 集（kb_04=51、kb_10=71），`|expected|>top_k=5` → recall 结构性不可过 ≥0.6 | P0 | 编码计划 B4 重定义；总设计 §3.2 |
| 评测 | LLM-as-judge 触发数据缺失：72/72 `judge.rubric` 空、mode 无 llm、contexts 仅 kb 集 → 触发矩阵（faithfulness=仅 kb；answer_relevancy=全集；rubric 降 P1） | P0 | 编码计划 B2；总设计 §3.2/§3.3 |
| 评测 | judge 成本控制（--judge-model/--judge-sample/--judge-cache + 预算公式） | 补充 | 编码计划 B2 |
| 评测 | NDCG 定义补 DCG@k 公式 + `_live_kb` 透出 rank/score | 补充 | 编码计划 G1；总设计 §3.2 |
| 评测 | monitor 阈值表/数据源/调度/告警去重；埋点缺失（chat/report/evaluation 无 record_agent_call）；/api/v1/metrics JSON 契约冻结 | 补充 | 编码计划 C1/C2/C3；总设计 §4 |
| 前端契约（Halley） | E4「think→act→observe」目标文件错位——StreamView.tsx 只消费 recommend 流（无 tool 事件）→ 落 chat 消费链 | P0 | 编码计划 E4；总设计 §6.2 |
| 前端契约 | `agent_tree` done 事件契约未定义 + zod strip 未知字段（实测丢弃）→ 契约写死 + types/sse.ts 显式声明 | P0 | 编码计划 E3；总设计 §6.2 |
| 前端契约 | tool end 事件附 result（observe 载体）；/metrics 前端链路走 res.text 不走信封 | 补充 | 编码计划 E4/C2；总设计 §6.2 |
| 前端契约 | E2 图谱 JSON：MindMap DSL 不可复用 → 新 nodes/edges 结构 + 新前端组件 | 补充 | 编码计划 E2；总设计 §5 |
| pi 对齐（Confucius） | 骨架选择正确、无过度移植；OTel 非 pi 来源需标注 | 确认 | 总设计 §8（标注来源） |
| pi 对齐 | §8 补遗漏：模板六节/M6 description 硬门槛/M7 disable-model-invocation/引用 ID 清单 details_json+`<referenced-*>`/成本记账 M8/isError 契约 M9 | 修正 | 总设计 §8 表格 |
| pi 对齐 | prometheus 优先级三处打架 → 统一 P1 且排在 P1-D 后 | 修正 | 总设计 §4.3/§8/§11；编码计划 1.1 |
| pi 对齐 | 上下文组装「读路径」缺失（A6/A7 双向） | 修正 | 编码计划 A6；总设计 §8 |
| pi 对齐 | P2 搁置项不能静默消失 → 加「取舍记录/记录在案」段 | 修正 | 总设计 §13；编码计划 G7 |
| pi 对齐 | `retainedTail`→`first_kept_seq` 取舍写明 | 修正 | 总设计 §8 |
| pi 对齐 | 编码纪律补 3 条（记忆点落 DB 不写 AGENTS.md / user_id 只走 ContextVar / /metrics 豁免 SSE） | 修正 | 编码计划 1.2 |

---

## 2. 已核实代码事实（修正依据）

| # | 事实 | 证据 |
|---|---|---|
| 1 | `eval/runner.py:343` import 已删除的 `query_knowledge`，`:348` 调 `query_knowledge.ainvoke` → `_live_kb` 必崩 | runner.py L343/L348 |
| 2 | kb_retrieval.jsonl 已重写为 `handbook_2025_<hash>:N`（commit a4f1549），expected 巨大（kb_01=29、kb_03=15、kb_04=51、kb_10=71） | eval_sets/kb_retrieval.jsonl |
| 3 | `judge.rubric` 72/72 空、`judge.mode` 无 llm、`reference.contexts` 仅 kb 集有 | 6 集全量扫描 |
| 4 | `persist_turn` 未传 usage → `chat_messages.usage_json` 从未写入；repo `append_message` 已有 `usage_json=None` 形参空挂 | persistence.py L34-61；chat_session_repo.py L60 |
| 5 | `registry.call()` 仅测试/直连用（deepagents ToolNode 直调 StructuredTool.invoke） | tools/registry.py L82 |
| 6 | SummarizationMiddleware 用于 factory.py L80/L88；`_acreate_summary`/`_summarization_event`/`awrap_model_call` 在 deepagents/middleware/summarization.py（L646/L197/**L1458**；注：L2102 属 `SummarizationToolMiddleware`（compact-tool nudge），与摘要生成无关，v1.2 修正行号） | 本地 deepagents 包 |
| 7 | `record_agent_call` 仅 api/recommend.py:69 调用，chat/report/evaluation 无埋点 | 全仓扫描 |
| 8 | `chat.py:287` 错误码用 `type(exc).__name__.upper()`，无结构化 code | api/chat.py L285-290 |
| 9 | `StreamView.tsx` 只消费 `recommendStreamWithRetry`（L129），无 tool 事件；chat 页消费 chatStream（text/tool/done/error） | 前端源码 |
| 10 | `chat_memory_entries` UNIQUE `uq_memory_dedup (user_id, kind, content_hash)`；repo 方法 upsert/list/delete/replace_memory_entries | sql/init-db.sql；chat_session_repo.py L219-288 |
| 11 | `test_memory_injector.py` 不存在；`test_tool_registry_consistency.py`/`test_llm_client_defaults.py`/`test_chat_session_repo_sql.py` 存在 | tests/ 目录 |
| 12 | `agent/main/agent.py` 只是 factory 包装，无主循环 | agent/main/agent.py |

---

## 3. 修正后一致性检查

- [x] 编码计划 1.1 依赖图：P1-C 明确排在 P1-D 后（不再与 P0-B 并行直连）
- [x] 总设计 §11 落地顺序：可观测步骤移到工具/记忆之后
- [x] 编码计划 A0~A9 / B1~B5 / D1~D8 / E1~E5 / C1~C4 / G1~G7 任务编号自洽，测试文件均与仓库实际对齐
- [x] FastGPT 相关项未进入任何工作流
- [x] 三份 pi notes 移植项全部登记（含新增遗漏项），OTel 标注非 pi 来源
- [x] 搁置项（rubric authoring / OTel / 调优自动联动 / judge 历史看板 / 恢复演示 / 引用 ID 清单）登记在 §13

---

## 4. 复评（第 2 轮）结果与决议（v1.2）

> 按初评修正后，再派 2 个复评 agent（后端/评测方向 Schrodinger、前端契约方向 Singer）对 v1.1 做收敛确认。结论：**后端 13 项核查 12 项完全落地、1 项部分（A0 流式路径）；前端 5 项 3 项完全落地、2 项部分（E3/C2 契约体）**。以下为复评新发现问题及修正决议（已落入 v1.2 文档）。

| # | 复评发现 | 级别 | 修正决议（v1.2 落点） |
|---|---|---|---|
| R1 | A0 流式路径 usage_json 仍写不进：`/api/v1/chat/stream` 的 `persist_turn(assistant_msgs=[{...}])` 传纯 dict 无 usage | P1 | 编码计划 A0：`persist_turn` 增 `usage_metadata` 参数，chat.py 把聚合 usage dict 显式传入（非流式传 AIMessage.usage_metadata） |
| R2 | `/api/v1/metrics`「契约冻结」只有声明、无契约体 schema | P1 | 编码计划 C2 + 总设计 §4.2：写死冻结 JSON schema（agents/business/generated_at + 统一信封） |
| R3 | 「前端 /metrics 走 res.text 不走信封」未入主文档且落点引用错位（写 §6.2，应为 §4） | P1 | 编码计划 C2 + 总设计 §4.2：`getPrometheusText()` 走 `fetch().text()`、`getMetrics()` 走冻结 JSON |
| R4 | `types/sse.ts` L9/L200 注释「zod 默认放行未知键」与 zod 默认 strip 相悖（agent_tree 丢字段根源） | P1 | 编码计划 E3 + 总设计 §6.2：显式声明 agent_tree 字段 + 修正注释 |
| R5 | agent_tree 契约缺字段级类型/可空性；数据来源「已有」有误读风险（chat.py 现无 run 树采集） | P2 | 编码计划 E3 + 总设计 §6.2：字段级契约 + `astream_events` 捕获 parent/child run_id 组装 |
| R6 | tool end result 未定义提取路径与摘要化/脱敏 | P2 | 编码计划 E4 + 总设计 §6.2：`on_tool_end` `data.output` 提取 + 长度上限/敏感字段截断 |
| R7 | chat 页仍走无重试 `chatStream`，与仓库 *WithRetry 约定不符 | P2 | 编码计划 E4 + 总设计 §6.2：切 `chatStreamWithRetry` |
| R8 | E2 文件落点矛盾（mindmap_generator 候选）、relation 值域/引用完整性未定义、E5 缺 CourseGraph 测试 | P2 | 编码计划 E2/E5 + 总设计 §5：新建 `course_graph.py`、relation 枚举、id 唯一 + 引用校验、`CourseGraph.spec.tsx` |
| R9 | A4 fallback「捕获异常」一路在 deepagents 实际不可达（异常被吞成前缀字符串） | P2 | 编码计划 A4：主检测点 = `super()` 返回值前缀检测 |
| R10 | factory.py `SummarizationToolMiddleware(summarization)` 第二项需同步传子类实例 | P2 | 编码计划 A4：替换装配时第二项同步 |
| R11 | A5 旧 `prompts/summarization.txt` 去向未明；B4 refresh 脚本是改造非新建；A6 续轮注入挂载点未指明 | P2 | 编码计划 A5/B4/A6：旧模板废弃与读取路径改向、标注改造既有脚本、chat.py messages 组装点为唯一入口 |

**复评后状态**：v1.2 已按上表全部落入两份文档；P0 级无遗留，P1 级（R1-R4）已修，P2 级（R5-R11）已修。可进入编码。

---

## 5. 待办（后续）

- 可选：派 1~2 个复评 agent 对 v1.1 做收敛确认（重点：middleware 子类方案与前端 chat 链契约）
- 进入编码后，P0-A 完成即回填本 note 验证状态；如复评发现新 P0 级问题，以「修正决议」追加记录