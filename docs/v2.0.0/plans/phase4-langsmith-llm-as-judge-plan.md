# Phase 4 收尾：LangSmith 原生 LLM-as-Judge 评测实施计划（2026-09-06）

> 本文档是「用 LangSmith 内置系统完成 phase4 剩下的 LLM-as-Judge」的详细计划。
> 输入来源：4 个并行 subagent 分析（评测基建现状 / 12 功能点盘点 / LangSmith 官方文档 / phase4 设计考古）+ 本日仓库实测。
> 相关既有文档：`docs/v2.0.0/plans/phase-4-master-design.md`（§3 设计域 A）、`docs/v2.0.0/plans/phase4-coding-plan.md`（§三 P0-B、G2）、`docs/v2.0.0/eval-system.md`（总登记，新增评测需在此登记）、`python/eval_sets/README.md`（规范 v2）。

## 0. 背景与要解决的问题（为什么）

phase4 原设计把 LLM-as-judge 做成了「本地 judge.py 三执行器 + runner --judge + 结果回写 LangSmith Dataset」（LangSmith 只做存储/展示，不打分）。考古确认：`judge.py`、`runner --judge`、NDCG/F1、G2 回写脚本**代码已写好但从未真实运行**（78 case 的 judge.rubric 全空、judge.mode 无 llm、23 份报告全部 judge=false）。

本次需求升级为：**用 LangSmith 原生系统完成 phase4 剩下的 LLM-as-Judge**——每个功能点在 LangSmith 建 dataset（输入 + 预设输出，每功能点 10 条）→ 真调 LLM/真实链路拿实际输出 → 用评估器打分（评估器可用 LangSmith 内置 LLM + 自定义 system prompt）。RAG 与特定场景编排的评估标准不同，须分开设计。

设计原则（沿用仓库既有约束）：
- **双轨并存，不推翻旧流程**：本地 JSONL→runner 断言式是离线、mock 化、可回归的默认路径（tests 禁止真调 LLM 的约定不能破）；新增 LangSmith 原生轨作为「真实 LLM 评测」路径，显式开关才跑。
- **JSONL 仍是唯一事实源**：每功能点 10 条 case 仍以 `python/eval_sets/` 下 jsonl 维护；导入 LangSmith 只是发布副本。
- **LLM 统一走 `build_chat_openai` + `LLMTaskName`**（含 judge/evaluator 的 LLM 调用），不直接 new ChatOpenAI。
- **成本硬约束**：真实评测默认关；显式 `--live` 类开关 + 采样 + 并发上限 + 缓存。

## 1. 版本红线（2026-09-06 官方口径，已核实）

| 项 | 结论 |
|---|---|
| langsmith SDK | 环境已装 **0.10.16**（requirements 写 `langsmith>=0.1.0`，建议收紧） |
| 主执行 API | `from langsmith import evaluate` / `client.aevaluate` + 自定义 evaluator（返回 `{key, score, comment}` 或 bool） |
| 内置 evaluator | 经典 `LangChainStringEvaluator`/`StringEvaluator`/`LLMEvaluator` 已 deprecated（≥0.5.0），官方迁移到 **openevals**（`create_llm_as_judge`、`exact_match` 等）+ **agentevals**（`create_trajectory_llm_as_judge`）。openevals **未安装**，安装需显式批准 |
| 旧 API 勿用 | `run_on_dataset`、`@test`/`@unit`、`llm.predict` |
| pytest 集成 | `langsmith[pytest]` 的 `@pytest.mark.langsmith` + `LANGSMITH_TEST_CACHE` 缓存（CI 省钱）；dry-run：`LANGSMITH_TEST_TRACKING=false` |
| 成本控制 | `num_repetitions=1`（默认）、`max_concurrency=4`、`--judge-sample`、HTTP 请求磁盘缓存 |

## 2. 架构决策（durable，各阶段复用）

- **新增目录**：`python/eval/langsmith_eval/`（包，内含 `__init__.py`、`datasets.py`、`targets.py`、`evaluators/`、`cli.py`），与现有 `python/eval/runner.py` 平级并存。
- **Dataset 命名**：`phase4_<feature>`（不复用 `phase2-<name>`，避免与旧「导入/回写」轨混淆）。features 见 §4。
- **Dataset 三分量（LangSmith 原生形态）**：`inputs` = 真实请求（含 case_id）；`outputs` = 预设输出/reference（**不传给 target，只注入 evaluator 的 reference_outputs**）；`metadata` = mode/difficulty/user_id。不再沿用旧脚本把 expected/assertions/judge 塞 outputs、reference 单列的形态（该形态只服务旧回写轨，保留不动）。
- **target 函数形态**：`target(inputs: dict) -> outputs: dict`；outputs 统一结构 `{"answer": str|null, "structured": {...}, "tool_calls": [{"name","args"}], "events": [...]}`（结构化字段 + 工具轨迹都给 evaluator，RAG 型给 `structured.retrieved`）。target 优先**进程内直调**（复用 runner live 执行器逻辑，如 query_handbook.ainvoke）；主 agent/SSE 复杂链路用 httpx 打本地 API（127.0.0.1:8000），保证测的是真实链路。
- **evaluator 分三层**（与功能点类型映射见 §5）：
  - D 确定性：把 `runner.run_assertions` 系纯函数包装成 evaluator，消费 outputs.structured/tool_calls（离线可回归、mock 友好）；
  - J LLM-as-judge：优先**包装现有 `eval/judge.py` 三执行器**（faithfulness/answer_relevancy/rubric，契约已被 test_eval_judge.py 锁定，EVAL_JUDGE run name 复用）；对照实现用 openevals `create_llm_as_judge(model=build_chat_openai(...), system_prompt=...)`；
  - M 人工/视觉抽检：image/report 渲染类各留 2-3 条 holdout，不进自动通过率。
- **运行入口**：`cd python && python eval/langsmith_eval/cli.py --feature <f> [--live] [--sample N] [--dry-run]`；`--dry-run` 走 mock target（不烧 LLM）；真调 LLM 需要 `--live` + LANGSMITH_API_KEY/LLM key 就绪。
- **tracing 激活**：CLI 入口先调 `python/ai/tracing.py::configure_langsmith_tracing()`（现有 runner 进程未激活，是本轨必须补齐的最小前置）。
- **报告**：experiment 结果 `to_pandas()` → 落 `python/eval/reports/langsmith/<feature>-<date>.json`（含逐 case score/comment + 聚合 pass rate + run_id 回链）；并在 `docs/v2.0.0/eval-system.md` §2/§7 登记。

## 3. 功能点与数据集（每功能点精选 10 条：输入 + 预设输出）

按 Locke 盘点收敛为 8 个核心功能点 × 10 = 80 examples（image/web_search/ppt/documents 等列入扩展队列，首版不做以免过重）。case 来源：现有 eval_sets 精选改写（≥10 的集挑代表性 10 条）+ 空白功能点新写（recommend/memory/sse）。难度分布 4 easy / 4 medium / 2 hard，反例约占 20%。

| # | feature | 类型 | dataset 名 | 10 条场景要点 | 来源 |
|---|---|---|---|---|---|
| F1 | chat_intent 意图路由/委派 | 编排 | phase4_chat_intent | 制度问答→query_handbook、成绩→query_transcript、推荐→recommend_courses、实时→web_search、报告/评语委派 dispatch→task 双事件、图片生成/识别、双意图保序、泛闲聊不调工具反例 | 现有 chat_intent 24 条精选（**先修 5 条过期**） |
| F2 | recommend 课程推荐 | 编排 | phase4_recommend | 冷启动、校区/不考试硬约束、num_items、多约束组合、pipeline/react 一致性、语义缓存命中、稀疏 warning、理由可溯源、时间冲突反例、编造课程反例 | 新写（现有 0 覆盖） |
| F3 | report 批量报告 | 编排 | phase4_report | 单科全 A、多科合并、缺科留空、等级多样性、冲突处置、年级分类兜底、fill 反幻觉、done 契约、PDF 下载闭环、坏文件不整批崩 | 现有 report_math 10+live2 精选改写 |
| F4 | evaluation 评语 | 编排+反幻觉 | phase4_evaluation | 合法引用、幻觉数字反例、rule 兜底、无数据、雷达 5 维、4 类型×口吻、维度贴合、寄语质量 rubric、极少课程边界、经历幻觉反例 | 现有 evaluation_comment 12+live6 精选改写 |
| F5 | kb RAG（手册/成绩单） | RAG | phase4_kb_rag | 手册 recall×3、混合 query、引用完整性、本人分区正例、他人分区隔离反例、检索空不编造、faithfulness、answer_relevancy、混合双查 | 现有 kb_retrieval 10 精选（B4 oracle 收敛后） |
| F6 | memory 提取+压缩 | 生成+状态 | phase4_memory | 改口 supersede、偏好提取、攒批、无信号不触发、隔离幂等、首轮六节结构、增量双模板、fallback 截断、落库注入、防抖 | 新写（现有 0 覆盖，行为由单测锁定） |
| F7 | SSE 流式协议 | 协议 | phase4_sse | 单调 id、chat 事件序、Last-Event-ID 续传、重连去重、recommend/report/evaluation 各流序、结构化 error、取消不 panic、Redis 降级 | 新写 |
| F8 | image_generate 两段式 | 外部编排 | phase4_image_generate | 单图/组图、图生图、宽高比、scale 对照、审核拒因、no-fake、转存契约、图文一致 judge、存储失败反例 | 现有 image_generate 5 扩充 |

> 扩展队列（后续）：web_search（引用/降级）、image_recognize（真实图）、documents 摄入、会话管理。

## 4. 评估器组合（RAG vs 编排 vs 生成，标准不同）

| 类型 | 功能点 | D 确定性 | J LLM-as-judge（judge.py 包装 / openevals 对照） | judge system prompt 要点 |
|---|---|---|---|---|
| RAG 型 | F5 | recall@k/NDCG/F1 + 引用存在性正则（source_doc_name/page_number）+ 隔离断言 | faithfulness（仅检索片段可支撑）+ answer_relevancy | 「仅依据检索片段作答；必须标注来源文档与页码；检索为空明确说明；不得编造页码/内容；个人数据仅本人可查」 |
| 编排型 | F1/F2/F3/F7/F8 | 工具链精确命中、事件序/单调 id、硬约束 100% 满足、结构/数值/错误码、done 必达 | tool-choice（是否该调/顺序/委派参数完整）+ 失败兜底是否静默（rubric） | 逐 agent 纪律：main 先查路由表（prompt.py）；report 数值交确定性工具不心算、异常不静默（specs.py）；recommend 硬约束先满足（specs.py）；image done 前不得声称已生成 |
| 生成质量型 | F4/F6 | 数字∈数据白名单（verify_numbers）、结构字段合法、落库可读、fallback 状态 | rubric（贴合类型、具体不空泛）+ factuality（judge.py rubric 执行器） | 「输出须可由输入事实支撑；看不清/未检索到→拒答或低置信，不编造；风格/口吻匹配类型」 |

rubric authoring：为 F4/F6/F2 的生成质量 case 补 `judge.rubric` 文本 + `judge.mode="llm"`（现在 78 case 全空，是 rubric 执行器与 openevals system_prompt 的共同前置）。

## 5. 阶段与任务（tracer bullet：每阶段端到端可验证）

### Phase 0：数据卫生与依赖（前置，半天）
- [ ] 0.1 迁移 `python/eval_sets/chat_intent.jsonl` 5 条过期工具链（行 8/9/10/20/24）：
  - intent_08 奖学金申请条件 → `query_handbook`
  - intent_09 转专业流程 → `query_handbook`
  - intent_10 高数成绩 → `query_transcript`
  - intent_20 先看选的课再推荐 → `[query_transcript, recommend_courses]`（保序）
  - intent_24 写论文+查奖学金 → `[writing_assistant, query_handbook]`
  验收：`python -m pytest tests/test_eval_runner.py tests/test_eval_runner_dispatch.py -q` 绿；`python eval/runner.py --set chat_intent`（smoke）绿。
- [ ] 0.2 依赖：`pip install -U openevals`（需网络批准）并把 requirements.txt 从 `langsmith>=0.1.0` 收紧为实测下限（如 `langsmith>=0.10.0`）；openevals 装入 requirements（可选依赖注释「Phase4 LangSmith LLM-as-judge」）。若安装被拒，J 层先只用 judge.py 包装路径（openevals 仅为对照）。
- [ ] 0.3 建立 `python/eval/langsmith_eval/` 包骨架 + `__init__.py` 空导出 + 在 `python/ai/llm_task_name.py` 确认 `EVAL_JUDGE` 已存在（存在则复用，不新增枚举）。

### Phase 1：端到端骨架（tracer bullet，选 F5 kb_rag 打通全链）
目标：一个功能点完整跑通「dataset → target 真调 → D/J evaluator → experiment 报告」，其余功能点照此复制。
- [ ] 1.1 `python/eval/langsmith_eval/datasets.py`：`publish(feature, cases)` —— 用 `Client` 建 `phase4_<feature>` dataset（has_dataset 防重），`create_examples(inputs=[{...请求, "case_id"}], outputs=[{...reference/预设输出}], metadata=[{mode,difficulty}])`；jsonl 源放 `python/eval_sets/phase4_<feature>.jsonl`（新规范：inputs/outputs 双层，字段契约在 eval_sets/README.md 补一节「Phase4 LangSmith 原生形态」）。
  验收（dry，不真调）：`python eval/langsmith_eval/cli.py --feature kb_rag --publish-only` 后 LangSmith 出现 `phase4_kb_rag` 且 example=10。
- [ ] 1.2 `python/eval/langsmith_eval/targets.py`：`kb_rag_target(inputs)` 进程内 `query_handbook.ainvoke({"query", "top_k": 5})` → 返回 `{"answer": 拼接命中文本, "structured": {"retrieved": matches(含 source_doc_name/page_number/rank/score)}, "tool_calls": [], "events": []}`；同时提供 `mock_targets.py`（dry-run 用，从 outputs 反推合法输出）。
- [ ] 1.3 `python/eval/langsmith_eval/evaluators/`：先落两个通用 evaluator 供全功能点复用：
  - `deterministic_evaluator`：包装 `eval/runner.py` 的断言纯函数（`run_assertions/_assert_one`），消费 `outputs.structured`；返回 `{"key": "deterministic", "score": 0/1, "comment": 失败点}`。
  - `judge_evaluator`：包装 `eval/judge.py` 的 `faithfulness/answer_relevancy`；返回 `{"key": metric, "score": 0~1, "comment": detail}`；内部走 `build_chat_openai(task_name=EVAL_JUDGE)`。
  验收：`python -m pytest tests/test_langsmith_eval_evaluators.py -q` 绿（mock LLM：patch build_chat_openai，参照 test_eval_judge.py 模式；**测试不真调 LLM**）。
- [ ] 1.4 `python/eval/langsmith_eval/cli.py`：入口先 `configure_langsmith_tracing()`；参数 `--feature/--publish-only/--live/--sample/--max-concurrency(默认4)/--dry-run`；`--dry-run` 用 mock target + 不开 J；`--live` 用 `aevaluate(data=phase4_<feature> 的 examples 或本地 jsonl, target=targets.<feature>, evaluators=[deterministic, judge...], num_repetitions=1, max_concurrency=4)`；结果 `results.to_pandas()` 落 `python/eval/reports/langsmith/<feature>-<date>.json`（附 run_id）。
  验收：`python eval/langsmith_eval/cli.py --feature kb_rag --dry-run` 落盘报告且含 10 行逐 case score；`--live`（真调，需 key）后 experiment 出现在 LangSmith 且报告含 run_id。
- [ ] 1.5 文档登记：`docs/v2.0.0/eval-system.md` 加「LangSmith 原生轨（Phase 4）」小节 + Registry 行；commit。

### Phase 2：全功能点数据与评估器（主体工作量）
- [ ] 2.1 编写 `python/eval_sets/phase4_<feature>.jsonl` × 8（每功能点 10 条，§3 场景表），F5 需先做 B4 kb oracle 收敛（expected 超集 kb_04=51/kb_10=71 收敛到 |expected| ≤ top_k，改 `python/scripts/refresh_kb_retrieval_oracle.py` 后重生成，否则 recall 结构性不过）。
- [ ] 2.2 为生成质量 case 补 rubric：F2 理由质量、F4 寄语质量、F6 摘要保真 的 case 写 `judge.rubric` 文本 + `judge.mode="llm"`（现 78 case 全空）。
- [ ] 2.3 `targets.py` 补齐 F1-F4/F6-F8 target（F1 chat 走 httpx 打本地 `/api/v1/chat/stream` 消费 SSE，复用 `eval/runner.py::_parse_chat_stream_events` 组装 outputs；F2 走 `/api/v1/recommend/stream` 或进程内 recommend_courses；F3/F4 走本地 API SSE；F6 memory 进程内 extractor/summarization_sync 触发；F7 SSE 用 EventBuffer 进程内单测驱动；F8 进程内 image_generate 两段式 + mock jimeng）。
- [ ] 2.4 `evaluators/` 补齐：F2 硬约束 evaluator、F1 tool-choice rubric evaluator、F4/F6 factuality+rubric evaluator、F5 faithfulness（复用 judge.py）、F7 事件序断言 evaluator；每功能点 evaluator 单测（mock LLM）绿。
- [ ] 2.5 每功能点 `--dry-run` 全绿 + 全量 `publish`。

### Phase 3：真实评测执行与收尾（需配额，显式批准后跑）
- [ ] 3.1 逐功能点 `--live --sample 10`（可先 sample 3 验证成本，再全量 10），落 `eval/reports/langsmith/*.json`；记录成本（token/耗时）。
- [ ] 3.2 结果分析：RAG 看 faithfulness/answer_relevancy 均分；编排看确定性通过率 + tool-choice；生成看 rubric 均分；hallucination 反例必须被 D/J 双拦（对照 8 条记忆里的「幻觉拦截」叙事）。
- [ ] 3.3 把每功能点 pass rate / 均分登记到 `docs/v2.0.0/eval-system.md` §7 实测记录 + 更新 `docs/v2.0.0/notes/` 一篇 phase4-langsmith-llm-judge 复盘（含失败 case 归因）。
- [ ] 3.4 commit 全量（judge.py 等暂存区代码一并提交——考古发现 HEAD 仍是 b6f2e9b，评测代码从未提交）。

### Phase 4：可选增强（按配额/时间取舍）
- [ ] 4.1 openevals 对照 evaluator（`create_llm_as_judge(model=build_chat_openai(...), system_prompt=...)`）与 judge.py 包装双跑一致性对比。
- [ ] 4.2 pytest 集成：`langsmith[pytest]` + `@pytest.mark.langsmith` 把每功能点 10 case 纳入 CI 可跑（默认 `LANGSMITH_TEST_TRACKING=false` dry-run，CI 开缓存）。
- [ ] 4.3 前端 monitor 页 judge 历史展示（原 P2，登记搁置项）。

## 6. 验收口径（完成判定）

1. `python/eval_sets/phase4_*.jsonl` 8 个文件各 10 case（输入+预设输出），eval_sets/README.md 有「Phase4 原生形态」契约。
2. `python eval/langsmith_eval/cli.py --feature <任一> --dry-run` 对 8 个功能点全部可跑且报告落盘（不烧 LLM）。
3. 至少 kb_rag 一个功能点 `--live` 跑通：LangSmith 出现 experiment + 逐 case run 带 feedback（D/J 双分），本地报告含 run_id 回链。
4. 每个功能点 D/J evaluator 有 mock 单测（tests/test_langsmith_eval_evaluators.py 等），`python -m pytest tests/ -m "not slow" -q` 全绿（默认 mock，不真调 LLM）。
5. chat_intent 5 条过期 case 已迁移且 smoke/live 口径归一；kb oracle |expected| ≤ top_k。
6. `docs/v2.0.0/eval-system.md` 完成登记；judge.py 等暂存区代码已提交。
7. 生成质量型功能点（F2/F4/F6）有 rubric authoring 产物且 `judge.mode="llm"` 非空。

## 7. 风险与对策

| 风险 | 对策 |
|---|---|
| openevals/agentevals 安装或 API 与文档不符 | J 层主路径用 judge.py 包装（契约已测），openevals 仅对照；先小步验证再铺开 |
| 真调 LLM 双份花费（target + judge） | `--live` 显式 + sample + max_concurrency=4 + `LANGSMITH_TEST_CACHE`；monitor 配额告警联动 |
| live 输出失真（kb answer 退化为 hits 摘要） | target 返回结构化 retrieved 全文给 evaluator，不用 runner 的 detail 摘要 |
| LangSmith 不可达 | publish/evaluate 全部 try-except 告警不阻塞（沿用 import 脚本约定）；dry-run 不依赖 LangSmith |
| 破坏既有测试契约（judge 输出形状/触发矩阵） | 新轨独立包，不改 judge.py/runner.py 现有行为；单测锁定 evaluator 输出 |
| chat_intent 旧工具链污染 dataset | Phase 0.1 先迁移再 publish |

## 8. 执行方式

按 writing-plans 惯例，本计划落盘后二选一：
1. **Subagent-Driven（推荐）**：按 Phase 0→3 每阶段派 fresh subagent 执行 + 两阶段 review；
2. **Inline Execution**：本会话内按阶段执行，每阶段 checkpoint 复核。
（用户在 goal 里已要求「开多个 subagent 分析」，本计划已由 4 个 subagent 完成分析；执行阶段是否继续 subagent 由用户确认。）
