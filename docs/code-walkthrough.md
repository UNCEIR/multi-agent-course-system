# 代码证据链讲解指南

<!-- markdownlint-disable MD024 -->

本文档按真实执行顺序组织代码讲解。目标不是背文件名，而是在面试中能说清：一个请求从哪里进来、状态如何流转、每段代码支撑哪个项目故事。

## 1. 推荐阅读路径

1. `python/main.py`
2. `python/config/settings.py`
3. `python/models/schemas.py`
4. `python/orchestrator/supervisor.py`
5. `python/orchestrator/react_tools.py`
6. `python/orchestrator/hard_constraint_filter.py`
7. `python/services/stream_token_markup_parser.py`
8. `python/agents/base_agent.py`
9. `python/agents/student_profile_agent.py`
10. `python/agents/course_recall_agent.py`
11. `python/repositories/course_recall_cache_repository.py`
12. `python/repositories/course_repository.py`
13. `python/repositories/course_vector_repository.py`
14. `python/agents/course_rerank_agent.py`
15. `python/agents/course_feasibility_agent.py`
16. `python/agents/recommendation_reason_agent.py`
17. `python/scripts/ingest_course_dataset.py`
18. `python/tests/`

## 2. 入口：`python/main.py`

### 代码承担的职责

`main.py` 是 API 边界，不承载核心推荐业务。它主要做：

- 初始化 `settings`、`ABTestEngine`、`MetricsCollector`、`SupervisorOrchestrator`。
- 暴露 `/health`、`/api/v1/recommend`、`/api/v1/recommend/stream` 等接口。
- 将 HTTP 请求转成 `RecommendationRequest` 后交给 Supervisor。
- 为流式推荐封装 `StreamingResponse` 和 SSE 事件。

### 支撑的面试故事

支撑"我没有把业务逻辑写在 Controller 里"。API 层只做接入、响应和健康检查，真正的推荐流程在编排层。

### 面试讲法

> FastAPI 入口保持很薄，同步推荐和流式推荐都交给同一个 Supervisor。这样我改 Agent 编排时不需要改 Controller，也方便后续替换成其他接入层。

### 可追问

- `/api/v1/recommend/stream` 和 `/api/v1/stream_recommend` 为什么都存在？
- `/health` 能证明什么，不能证明什么？
- 为什么 metrics 当前只能叫进程内指标？

## 3. 配置：`python/config/settings.py`

### 代码承担的职责

`Settings` 统一读取 LLM、Embedding、MySQL、Redis、Milvus、Agent 超时和缓存配置。当前要特别记住：

- 环境变量无前缀，字段名即变量名。
- Milvus 课程 collection 为 `course_chunks_real`。
- embedding 维度按配置为 1024。
- Redis 召回缓存有 TTL、短锁 TTL、等待重试等配置。

### 支撑的面试故事

支撑"历史兼容不是业务主线"。去 `ECOM_` 前缀是为了让变量名与项目语义一致，不再背负电商历史包袱。

### 面试讲法

> 我没有为了改名大范围动环境变量，因为这会扩大风险。业务主线通过模型、Agent 和数据流切换到公选课，配置前缀作为兼容层保留。

## 4. 领域模型：`python/models/schemas.py`

### 代码承担的职责

这里定义请求、响应、课程、学生画像和各 Agent 结果。当前主线重点看：

- `RecommendationRequest`
- `RecommendationResponse`
- `StudentProfile`
- `HardConstraints`
- `Course`
- `AgentResult` 及各子结果模型

### 支撑的面试故事

支撑"把自然语言需求转成后续 Agent 可消费的结构化状态"。例如学生说"周三晚上不要"，最后要能落到 `avoid_time_slots` 或硬约束字段，而不是只停留在原始 prompt。

### 可追问

- 为什么响应里还保留 `products`？
- 硬约束为什么放进画像模型？
- `AgentResult` 为什么统一记录成功、耗时和错误？

## 5. 编排核心：`python/orchestrator/supervisor.py`

### 代码承担的职责

这是项目最适合面试展开的文件。它把推荐拆成几段：

1. 初始化请求、生成 `request_id`、实验分组。
2. **A/B 路由**：`experiment.get("group") == "react"` 时走 `_react_recommend()` —— ReAct 工具调用模式，最多 10 轮 LLM 工具调用循环。
3. Phase 1：`StudentProfileAgent` 与 `CourseRecallAgent` 并行。
4. 画像成功后：用结构化字段补充召回并合并去重。
5. Phase 1.5：`HardConstraintFilter` 过滤明确不符合条件的课程。
6. **Phase 1.75**：`_llm_semantic_filter()` LLM 语义初筛 —— 候选 >40 且画像存在时触发，让 LLM 从候选中挑选最相关的 40 门。调用失败返回空列表，保留原候选集继续后续流程，不中断。
7. Phase 2：`CourseRerankAgent` 与 `CourseFeasibilityAgent` 并行。
8. 最终过滤、截断到 `num_items`。
9. Phase 3：`RecommendationReasonAgent` 生成解释。
10. 聚合 `agent_results`、`selection_warnings`、`priority_advice`、`total_latency_ms`。

### 支撑的面试故事

支撑四个故事：

- "为什么 Multi-Agent"：每段职责和失败边界不同。
- "为什么能并行"：只并行无依赖阶段，有依赖的串行等待。
- "为什么硬约束要独立"：过滤在重排前发生，防止 LLM 把违规课程带回来。
- "为什么做双模式编排"：Pipeline 模式是确定性流水线，适合可预测请求；ReAct 模式让 LLM 根据运行时状态动态决策，适合需求模糊或异常场景。两种模式共用相同的 Agent 实现，区别只在调度策略。

### 面试讲法

> 我先画出 Agent 之间的依赖关系，再决定哪些能并行。画像和宽召回都能从原始请求开始，所以 Phase 1 并行；重排和可行性都依赖候选池，但互不依赖，所以 Phase 2 并行；推荐理由依赖最终课程，所以最后串行。在此基础上，我做了 Pipeline 和 ReAct 双模式编排——Pipeline 是固定流水线，确定性强、延迟可预测；ReAct 让 LLM 拿到 7 个工具自行决定调用顺序，应对异常情况（召回不足时可以回头放宽条件重试）。两种模式通过 A/B 实验分组切换，共用同一套 Agent。

### 可追问

- 如果画像失败，后面的链路还能走吗？
- 精召回和宽召回怎么合并？
- 为什么最终组装还要限制课程必须来自过滤后的允许集合？
- ReAct 和 Pipeline 什么时候用哪个？
- Phase 1.75 失败为什么不中断整个流程？

## 6. ReAct 工具编排：`python/orchestrator/react_tools.py`

### 代码承担的职责

该文件实现 ReAct 模式下 LLM 的工具调用基础设施，三层结构：

- **`REACT_TOOLS`**：7 个 OpenAI function calling 格式的工具定义 —— `extract_profile`、`search_courses`、`filter_hard_constraints`、`semantic_filter_courses`、`rerank_courses`、`check_feasibility`、`generate_reasons`。传给 `build_tool_calling_llm()` 做 `bind_tools`。
- **`ReactState`**：跨轮次可变状态容器，持有 `profile`、`courses`、`priority_advice`、`reasons`、`warnings` 以及各阶段完成标记（`hard_filtered`、`rerank_done` 等）。
- **`ReactToolExecutor`**：工具调度器，将 LLM 返回的 `tool_calls` 按 `name` 分发到 `_tool_xxx` 方法，每个方法内部调用对应的真实 Agent 并更新 `ReactState`。

关键设计：

- `filter_hard_constraints` 在 Supervisor 层有兜底——即使 LLM 跳过，`_react_recommend()` 结尾会强制补调。
- 每个工具方法异常时返回错误字符串而非抛异常，LLM 可据此决定是否重试。

### 支撑的面试故事

支撑"LLM 不只做生成，还做编排决策"。Pipeline 模式下编排是写死的代码，ReAct 模式下编排由 LLM 运行时决定。

### 面试讲法

> ReAct 模式下 LLM 拿到 7 个工具，根据学生需求的复杂度决定执行哪些步骤。正常请求走直线，和 Pipeline 一样；异常时（召回不足、全爆满）LLM 可以回头放宽条件重试。关键是硬约束过滤锁死不可跳过——即使 LLM 没调用这个工具，Supervisor 会在循环结束后强制补调。

### 可追问

- 7 个工具怎么保证执行顺序？—— System prompt 规定了顺序约束，但 LLM 可以根据运行时状态灵活调整（如重复调用 `search_courses`），硬约束工具通过代码兜底保证不被跳过。
- 硬约束工具怎么"锁死"？—— `_react_recommend()` 循环结束后检查 `executor.state.hard_filtered`，为 `False` 时自动补调 `_tool_filter_hard_constraints()`。
- ReAct 模式的 token 成本？—— 每轮 LLM 调用都要传完整 messages 历史（含所有 ToolMessage），10 轮上限下 token 消耗约为 Pipeline 模式的 3-5 倍。

## 7. 流式 Token 解析：`python/services/stream_token_markup_parser.py`

### 代码承担的职责

`StreamTokenMarkupParser` 把 LLM 逐 token 输出的文本流解析为结构化事件流：

- **双状态机**：`idle`（直通文本）和 `buffering`（遇到 `[` 后暂存，等待判断是否为 marker）。
- **marker 正则** `[COURSE:id:name]`：匹配后触发 `course_start` 事件（含 `course_id`、`course_name`、`index`），前一门课自动触发 `course_end`。
- **输出三种事件**：`text`（附带当前 `course_id` 归属）、`course_start`、`course_end`。
- **MAX_BUFFER=256** 防止异常输出（如 LLM 输出未闭合的 `[`）导致无限缓存，超限时 flush buffer 为普通文本。

### 支撑的面试故事

支撑"流式输出不只是拆字符，还要结构化归属到课程"。前端需要知道哪段文字属于哪门课，才能做到按课程卡片展示推荐理由。

### 面试讲法

> LLM 流式输出时 token 是逐个到达的，一个 marker 可能跨多个 token。我用双状态机处理：idle 状态直接转发文本，遇到 `[` 切到 buffering 状态暂存，直到 `]` 闭合后正则匹配。匹配成功就发出 `course_start` 事件，失败就把 buffer 当普通文本 flush。MAX_BUFFER=256 防止异常情况下内存膨胀。

### 可追问

- marker 格式为什么这样设计？—— `[COURSE:id:name]` 格式简单、不会和正常文本冲突，且 LLM 容易遵循。
- buffer 超限怎么处理？—— 直接调 `_flush_buffer()` 把已缓存内容作为 `text` 事件输出，回到 `idle` 状态。
- 如果 marker 跨了两个 chunk 怎么办？—— 状态机在 chunk 之间保持 `_buffer` 和 `_state`，下一个 chunk 继续从 buffering 状态处理。

## 8. 硬约束：`python/orchestrator/hard_constraint_filter.py`

### 代码承担的职责

`HardConstraintFilter` 做确定性过滤。它处理校区、避开时间、课程类别、老师、不考试、作业量/难度上限等约束，并输出：

- 通过过滤的课程。
- 被过滤课程及原因。
- 候选不足 warning。

### 支撑的面试故事

支撑"硬约束不能只是排序分数"。用户明确说"只要西校区"，不符合校区的课程就不应该进入重排。

### 面试讲法

> 我把硬约束从 LLM 排序里拿出来，是因为分数只能影响顺序，不能保证违规课程不出现。过滤器先做确定性裁剪，LLM 只在合规候选里排序。

### 可追问

- 哪些字段是天然硬约束？
- 哪些字段需要"只要/必须"等强意图才升级？
- 过滤后不足时为什么只 warning，不自动放宽？

## 9. Agent 基类：`python/agents/base_agent.py`

### 代码承担的职责

`BaseAgent` 把横切能力放在统一入口：

- 记录调用次数、错误次数、耗时。
- 使用 `tenacity` 做指数退避重试。
- 异常时调用 `_fallback()` 返回失败结果。
- 子类只实现 `_execute()`。

### 支撑的面试故事

支撑"每个 Agent 可以单独失败、单独观察"。这不是简单拆文件，而是让运行时保障在基类里统一。

### 面试讲法

> 我用模板方法思路做 Agent 基类。子类只关心业务逻辑，重试、耗时和 fallback 放在基类里，避免每个 Agent 重复写一遍。

## 10. 学生画像：`python/agents/student_profile_agent.py`

### 代码承担的职责

把 prompt 和 context 转成结构化画像：

- 兴趣、领域、类别、校区、时间偏好。
- 考试、作业量、给分、小组作业偏好。
- 硬约束字段。
- LLM 解析失败时的启发式兜底。

### 支撑的面试故事

支撑"把模糊表达变成后续可用状态"。例如"不想考试"不是一句说明，而是影响召回、过滤和理由生成的字段。

### 面试讲法

> 画像 Agent 的价值不是总结文本，而是把学生的自然语言拆成后续 Agent 能消费的字段。这样召回、过滤和理由生成不用反复理解大段 prompt。

## 11. 课程召回：`python/agents/course_recall_agent.py`

### 代码承担的职责

召回 Agent 汇总多个来源：

- Redis 候选缓存（精确 + 语义两级）。
- MySQL 结构化查询。
- Milvus 语义召回。
- mock 兜底。

关键逻辑：

1. **`query_embedding` 统一计算**：`_execute()` 入口统一调一次 `embed_text(query)` 得到 `query_embedding`，后续传递给语义缓存探测（`_semantic_cached_courses`）、Milvus 向量检索（`_semantic_course_ids`）、缓存索引写入（`_index_semantic_cache`）三个消费者，从原来 3 次 embedding API 调用降为 1 次。
2. 基于画像和 context 构建缓存上下文，查 Redis 精确或语义缓存。
3. 命中后回 MySQL 拿完整课程。
4. 未命中时走 MySQL + Milvus。
5. 合并去重并评分。
6. 写回 Redis 候选 `course_id`。

`search()` 返回格式为 `list[dict]`（含 `chunk_id`、`course_id`、`chunk_type`、`distance`），`course_id` 直接从 `hit.entity["course_id"]` 取值，不再做字符串解析。

`_score_candidates()` 只保留 query 关键词匹配（+1.5）和热度加分（+0.8），semantic 课程的 score 从 Milvus COSINE 相似度初始化（`1.0 - distance`）。接受 `profile` 参数但不使用——召回负责广度，精排评分由 RerankAgent 负责。

### 支撑的面试故事

支撑"MySQL、Milvus、Redis 的分工"和"embedding 调用优化"。Redis 减少重复召回，Milvus 处理语义，MySQL 保证事实。embedding 统一计算避免同一个 query 重复调外部 API。

### 面试讲法

> 召回不是只靠向量库。向量库适合"轻松、给分友好"这类语义，MySQL 适合校区、分类、容量这种精确字段。Redis 缓存的是候选 ID，命中后还是回 MySQL。embedding 在入口统一算一次，三个消费者共用同一个向量，避免了重复的 API 开销。

### 可追问

- `_short_query()` 为什么不把长 prompt 直接丢给 MySQL LIKE？
- Milvus 失败时结果怎么降级？
- 语义缓存命中时怎么确认跳过了 embedding？
- embedding 怎么从 3 次降到 1 次？—— `_execute()` 入口算一次 `query_embedding`，通过参数传给 `_semantic_cached_courses(query_embedding=...)`、`_semantic_course_ids(query_embedding=...)`、`_index_semantic_cache(query_embedding=...)`。
- 为什么召回不做 profile 匹配？—— 召回阶段的目标是广度（尽量不漏），profile 精细匹配放在 RerankAgent 做，职责分离。

## 12. Redis 缓存：`python/repositories/course_recall_cache_repository.py`

### 代码承担的职责

这个仓储封装缓存 key 构建、候选 ID 读写、短锁和语义缓存索引。

### 支撑的面试故事

支撑"缓存候选 ID，不缓存课程事实"。它解决的是相似需求重复召回成本，不是替代数据库。

### 面试讲法

> 我把 Redis 设计在召回层，不放在最终展示层。它缓存的是候选集索引，命中后回 MySQL，所以容量、限制条件这些字段仍然以 MySQL 为准。

## 13. MySQL 仓储：`python/repositories/course_repository.py`

### 代码承担的职责

`CourseRepository` 负责：

- 创建和维护 `course_records`、`course_chunks`。
- 写入课程主记录和 chunk 文本。
- 按领域、分类、校区、短 query 召回。
- 按 Milvus 返回的 `course_id` 回表。
- 将 SQL 行和 `raw_json` 合并成 `Course`。

### 支撑的面试故事

支撑"推荐结果可追溯"。最终展示和规则判断都回到 MySQL，不只依赖向量库片段。

### 可追问

- 为什么保留 `raw_json`？
- `fetch_courses_by_ids()` 为什么要尽量保持输入 ID 顺序？
- MySQL DDL 兼容问题如何处理过？

## 14. Milvus 仓储：`python/repositories/course_vector_repository.py`

### 代码承担的职责

`CourseVectorRepository` 负责：

- 连接 Milvus。
- 创建 `course_chunks_real` collection 和索引。
- 对 chunk 文本生成 embedding。
- 写入和检索向量。
- 给 `/health` 提供 `ping()`。

`search()` 方法接受可选的 `query_vector` 参数——有预计算向量时直接用，否则内部调 `embed_text()`。返回 `list[dict]`，每个 dict 含 `chunk_id`、`course_id`、`chunk_type`、`distance`，`course_id` 通过 `hit.entity.get("course_id")` 直接获取。

### 支撑的面试故事

支撑"课程按语义粒度拆 chunk"。这让"不要考试、作业少"更容易命中学习体验，而不是被课程名、地点等字段稀释。

### 面试讲法

> Milvus 在这里不是事实库，它只负责帮我找到相关 chunk。命中后还是通过 `course_id` 回 MySQL，这样召回相关性和课程事实各自有边界。

## 15. 重排：`python/agents/course_rerank_agent.py`

### 代码承担的职责

重排 Agent 在候选课程内排序：

- **`_compute_score()` 规则预打分**：汇总多维偏好匹配 —— domain(+4.0) / category(+3.0) / campus(+2.0) / workload(+1.5) / exam(+1.5) / grade_friendly(+1.2) / popularity(+0.8) / no_exam(+0.5) / low_workload(+0.5)，爆满课 -0.4，低年级（大一/大二）选爆满课额外 -2.0。最终公式：`final = profile_score * (1.0 + milvus_sim * 0.5)`，用乘法融合 Milvus 相似度分。
- **Top-40 预过滤**：LLM 重排前先用 `_compute_score()` 排序取前 40 门送给 LLM，避免超长上下文。
- LLM 只能输出候选课程 ID 的 JSON array。
- 解析失败时走规则排序。
- 结果不足时用原候选补齐。
- 控制领域多样性，避免列表过于单一。

### 支撑的面试故事

支撑"LLM 只做候选内决策"和"规则分 + 语义分混合排序"。规则预打分解决结构化偏好匹配，LLM 处理规则难以表达的语义判断。

### 面试讲法

> 我先用规则打分做 Top-40 预过滤，再把这 40 门课送给 LLM 做语义精排。规则分覆盖领域、校区、考核偏好等结构化信号，用乘法和 Milvus 相似度融合——乘法确保规则分为 0 时（完全不匹配），即使 Milvus 语义相似度高也不会排到前面。LLM 在 40 门内做最终排序，输入规模可控。

### 可追问

- 为什么用乘法而不是加法融合 Milvus 分？—— 加法下规则分 0 但 Milvus 分高的课程会排到前面，不符合预期。乘法保证结构化偏好完全不匹配时，语义分无法"救"回来。
- 为什么预过滤取 40 而不是更多？—— LLM context window 和 token 成本的平衡，40 门课的 JSON 描述约 4000-5000 token。
- 领域多样性怎么保证？—— `_ensure_domain_diversity()` 限制单一 domain 最多 3 门课。

## 16. 可行性：`python/agents/course_feasibility_agent.py`

### 代码承担的职责

可行性 Agent 输出容量和软风险提醒：

- 满员或容量紧张。
- 考试偏好不匹配。
- 小组作业偏好不匹配。
- 抢课优先级建议。

硬约束主过滤已前移到 `HardConstraintFilter`，这里更偏风险解释。

**`_llm_priority_advice()` 方法**：最多取前 12 门课送给 LLM（`max_tokens=4096`），基于容量比率、popularity、年级优先权等生成个性化抢课建议（含 `priority` 和 `advice` 字段）。超过 12 门的走 `_rule_priority_advice_batch()` 规则 fallback。

**规则 fallback 与静默回退**：`_parse_advice_json()` 解析 LLM 输出失败时返回空 dict，不抛异常，静默回退到纯规则路径。排查时需搜 `llm_advice_parse_empty` 或 `llm_advice_failed` 日志。

**`priority_advice` 数据流**：`FeasibilityAgent` 生成 → `Supervisor` 在 `RecommendationResponse` 中透传 → API 响应 `priority_advice` 字段 → 前端按课程卡片渲染抢课建议。

### 支撑的面试故事

支撑"爆满不一定删除"和"LLM + 规则混合生成建议"。真实选课里热门课可能仍值得冲，但系统要透明提醒风险并给出可操作的优先级建议。

### 面试讲法

> 可行性 Agent 不只做过滤，还为每门课生成抢课建议。前 12 门送 LLM 生成个性化分析（引用真实数据），超出的走规则。LLM 解析失败时静默回退到规则路径，不中断主流程。这个 `priority_advice` 一路透传到前端，学生能看到"容量可控，可作保底"还是"爆满，需要冲刺"。

### 可追问

- 为什么限制 12 门？—— `max_tokens=4096`，12 门课的输入 + 输出恰好在 token 限制内，再多会导致 JSON 截断。
- LLM 建议解析失败怎么发现？—— 搜日志 `llm_advice_parse_empty`（解析返回空）或 `llm_advice_failed`（调用异常）。
- 规则 fallback 的建议质量如何？—— 只能给出通用模板（"冲刺优先级高"/"容量可控"），缺少引用真实数据的分析。

## 17. 推荐理由：`python/agents/recommendation_reason_agent.py`

### 代码承担的职责

把最终课程和风险转成学生能理解的理由：

- 每门课一条理由。
- 只能使用输入字段，不编造课程事实。
- 课程爆满、容量紧张、考核不匹配时要提示风险。
- LLM 失败时用字段拼接 fallback 理由。

### 支撑的面试故事

支撑"推荐结果可解释"。学生不仅要知道推荐哪门课，还要知道为什么适合、有什么风险。

## 18. 导入脚本：`python/scripts/ingest_course_dataset.py`

### 代码承担的职责

把课程 CSV 变成可召回数据：

1. 读取 `public_elective_courses.csv`。
2. 确保 MySQL schema。
3. 写入 `course_records`。
4. 构建四类 chunk。
5. 写入 `course_chunks`。
6. 生成 embedding 并写入 Milvus。
7. 输出导入结果。

### 支撑的面试故事

支撑"项目不是只写 prompt，而是有数据闭环"。从 CSV 到 MySQL/Milvus，再到推荐接口，可以完整演示。

### 可追问

- 为什么先用 `--limit 20` 或 `--limit 50` 验证？
- 外部 embedding API 抖动时怎么处理？
- 如何验证 MySQL chunk 和 Milvus 实体一致？

## 19. 测试证据

当前测试：39 passed，覆盖 8 个测试文件。

| 测试文件 | 覆盖范围 |
| --- | --- |
| `test_supervisor_pipeline.py` | Supervisor 主链路聚合、缓存候选和 Phase 流转 |
| `test_course_recall_cache.py` | Redis 命中、未命中、不可用回退、语义缓存 |
| `test_hard_constraint_prompt_fallback.py` | 硬约束 prompt 兜底、类别模糊匹配 |
| `test_stream_recommend.py` | SSE 事件序列、流式阶段行为、超时处理 |
| `test_stream_token_markup_parser.py` | marker 解析、跨 chunk 状态、buffer 超限 |
| `test_base_agent.py` | 基类重试、fallback、耗时记录 |
| `test_ab_test.py` | A/B 实验分组分配 |
| `test_llm_integration_smoke.py` | LLM 集成冒烟测试 |

其他验证证据：

| 证据 | 支撑结论 |
| --- | --- |
| Docker `/health` | MySQL、Redis、Milvus 依赖可连通 |
| Docker `/api/v1/recommend` | 同步推荐链路可达 |
| Docker `/api/v1/stream_recommend` | 流式推荐链路可达 |

注意：这些证明工程链路能跑，不等价于真实业务指标提升。

## 20. 面试自查

- 能不能从 `main.py` 讲到 `SupervisorOrchestrator`？
- 能不能解释为什么 Phase 1.5 放在重排前？
- 能不能说明 Redis、MySQL、Milvus 各自边界？
- 能不能讲清 Pipeline 和 ReAct 双模式编排的设计意图？
- 能不能解释 embedding 从 3 次降到 1 次的优化？
- 能不能描述流式 Token 解析的状态机原理？
- 能不能给出至少一个测试文件或 Docker 验证结果？
- 能不能承认当前限制：时间冲突轻量、A/B 进程内、真实业务指标待补充？
