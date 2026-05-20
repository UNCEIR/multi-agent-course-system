# 代码证据链讲解指南

<!-- markdownlint-disable MD024 -->

本文档按真实执行顺序组织代码讲解。目标不是背文件名，而是在面试中能说清：一个请求从哪里进来、状态如何流转、每段代码支撑哪个项目故事。

## 1. 推荐阅读路径

1. `python/main.py`
2. `python/config/settings.py`
3. `python/models/schemas.py`
4. `python/orchestrator/supervisor.py`
5. `python/orchestrator/hard_constraint_filter.py`
6. `python/agents/base_agent.py`
7. `python/agents/student_profile_agent.py`
8. `python/agents/course_recall_agent.py`
9. `python/repositories/course_recall_cache_repository.py`
10. `python/repositories/course_repository.py`
11. `python/repositories/course_vector_repository.py`
12. `python/agents/course_rerank_agent.py`
13. `python/agents/course_feasibility_agent.py`
14. `python/agents/recommendation_reason_agent.py`
15. `python/scripts/ingest_course_dataset.py`
16. `python/tests/`

## 2. 入口：`python/main.py`

### 代码承担的职责

`main.py` 是 API 边界，不承载核心推荐业务。它主要做：

- 初始化 `settings`、`ABTestEngine`、`MetricsCollector`、`SupervisorOrchestrator`。
- 暴露 `/health`、`/api/v1/recommend`、`/api/v1/recommend/stream` 等接口。
- 将 HTTP 请求转成 `RecommendationRequest` 后交给 Supervisor。
- 为流式推荐封装 `StreamingResponse` 和 SSE 事件。

### 支撑的面试故事

支撑“我没有把业务逻辑写在 Controller 里”。API 层只做接入、响应和健康检查，真正的推荐流程在编排层。

### 面试讲法

> FastAPI 入口保持很薄，同步推荐和流式推荐都交给同一个 Supervisor。这样我改 Agent 编排时不需要改 Controller，也方便后续替换成其他接入层。

### 可追问

- `/api/v1/recommend/stream` 和 `/api/v1/stream_recommend` 为什么都存在？
- `/health` 能证明什么，不能证明什么？
- 为什么 metrics 当前只能叫进程内指标？

## 3. 配置：`python/config/settings.py`

### 代码承担的职责

`Settings` 统一读取 LLM、Embedding、MySQL、Redis、Milvus、Agent 超时和缓存配置。当前要特别记住：

- 环境变量前缀仍是 `ECOM_`。
- Milvus 课程 collection 为 `course_chunks_real`。
- embedding 维度按配置为 1152。
- Redis 召回缓存有 TTL、短锁 TTL、等待重试等配置。

### 支撑的面试故事

支撑“历史兼容不是业务主线”。保留 `ECOM_` 是为了不破坏现有 `.env` 和容器配置，不是项目仍然属于电商场景。

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

支撑“把自然语言需求转成后续 Agent 可消费的结构化状态”。例如学生说“周三晚上不要”，最后要能落到 `avoid_time_slots` 或硬约束字段，而不是只停留在原始 prompt。

### 可追问

- 为什么响应里还保留 `products`？
- 硬约束为什么放进画像模型？
- `AgentResult` 为什么统一记录成功、耗时和错误？

## 5. 编排核心：`python/orchestrator/supervisor.py`

### 代码承担的职责

这是项目最适合面试展开的文件。它把推荐拆成几段：

1. 初始化请求、生成 `request_id`、实验分组。
2. Phase 1：`StudentProfileAgent` 与 `CourseRecallAgent` 并行。
3. 画像成功后：用结构化字段补充召回并合并去重。
4. Phase 1.5：`HardConstraintFilter` 过滤明确不符合条件的课程。
5. Phase 2：`CourseRerankAgent` 与 `CourseFeasibilityAgent` 并行。
6. 最终过滤、截断到 `num_items`。
7. Phase 3：`RecommendationReasonAgent` 生成解释。
8. 聚合 `agent_results`、`selection_warnings`、`total_latency_ms`。

### 支撑的面试故事

支撑三个故事：

- “为什么 Multi-Agent”：每段职责和失败边界不同。
- “为什么能并行”：只并行无依赖阶段，有依赖的串行等待。
- “为什么硬约束要独立”：过滤在重排前发生，防止 LLM 把违规课程带回来。

### 面试讲法

> 我先画出 Agent 之间的依赖关系，再决定哪些能并行。画像和宽召回都能从原始请求开始，所以 Phase 1 并行；重排和可行性都依赖候选池，但互不依赖，所以 Phase 2 并行；推荐理由依赖最终课程，所以最后串行。

### 可追问

- 如果画像失败，后面的链路还能走吗？
- 精召回和宽召回怎么合并？
- 为什么最终组装还要限制课程必须来自过滤后的允许集合？

## 6. 硬约束：`python/orchestrator/hard_constraint_filter.py`

### 代码承担的职责

`HardConstraintFilter` 做确定性过滤。它处理校区、避开时间、课程类别、老师、不考试、作业量/难度上限等约束，并输出：

- 通过过滤的课程。
- 被过滤课程及原因。
- 候选不足 warning。

### 支撑的面试故事

支撑“硬约束不能只是排序分数”。用户明确说“只要西校区”，不符合校区的课程就不应该进入重排。

### 面试讲法

> 我把硬约束从 LLM 排序里拿出来，是因为分数只能影响顺序，不能保证违规课程不出现。过滤器先做确定性裁剪，LLM 只在合规候选里排序。

### 可追问

- 哪些字段是天然硬约束？
- 哪些字段需要“只要/必须”等强意图才升级？
- 过滤后不足时为什么只 warning，不自动放宽？

## 7. Agent 基类：`python/agents/base_agent.py`

### 代码承担的职责

`BaseAgent` 把横切能力放在统一入口：

- 记录调用次数、错误次数、耗时。
- 使用 `tenacity` 做指数退避重试。
- 异常时调用 `_fallback()` 返回失败结果。
- 子类只实现 `_execute()`。

### 支撑的面试故事

支撑“每个 Agent 可以单独失败、单独观察”。这不是简单拆文件，而是让运行时保障在基类里统一。

### 面试讲法

> 我用模板方法思路做 Agent 基类。子类只关心业务逻辑，重试、耗时和 fallback 放在基类里，避免每个 Agent 重复写一遍。

## 8. 学生画像：`python/agents/student_profile_agent.py`

### 代码承担的职责

把 prompt 和 context 转成结构化画像：

- 兴趣、领域、类别、校区、时间偏好。
- 考试、作业量、给分、小组作业偏好。
- 硬约束字段。
- LLM 解析失败时的启发式兜底。

### 支撑的面试故事

支撑“把模糊表达变成后续可用状态”。例如“不想考试”不是一句说明，而是影响召回、过滤和理由生成的字段。

### 面试讲法

> 画像 Agent 的价值不是总结文本，而是把学生的自然语言拆成后续 Agent 能消费的字段。这样召回、过滤和理由生成不用反复理解大段 prompt。

## 9. 课程召回：`python/agents/course_recall_agent.py`

### 代码承担的职责

召回 Agent 汇总多个来源：

- Redis 候选缓存。
- MySQL 结构化查询。
- Milvus 语义召回。
- mock 兜底。

关键逻辑：

1. 基于画像和 context 构建缓存上下文。
2. 查 Redis 精确或语义缓存。
3. 命中后回 MySQL 拿完整课程。
4. 未命中时走 MySQL + Milvus。
5. 合并去重并评分。
6. 写回 Redis 候选 `course_id`。

### 支撑的面试故事

支撑“MySQL、Milvus、Redis 的分工”。Redis 减少重复召回，Milvus 处理语义，MySQL 保证事实。

### 面试讲法

> 召回不是只靠向量库。向量库适合“轻松、给分友好”这类语义，MySQL 适合校区、分类、容量这种精确字段。Redis 缓存的是候选 ID，命中后还是回 MySQL。

### 可追问

- `_short_query()` 为什么不把长 prompt 直接丢给 MySQL LIKE？
- Milvus 失败时结果怎么降级？
- 语义缓存命中时怎么确认跳过了 embedding？

## 10. Redis 缓存：`python/repositories/course_recall_cache_repository.py`

### 代码承担的职责

这个仓储封装缓存 key 构建、候选 ID 读写、短锁和语义缓存索引。

### 支撑的面试故事

支撑“缓存候选 ID，不缓存课程事实”。它解决的是相似需求重复召回成本，不是替代数据库。

### 面试讲法

> 我把 Redis 设计在召回层，不放在最终展示层。它缓存的是候选集索引，命中后回 MySQL，所以容量、限制条件这些字段仍然以 MySQL 为准。

## 11. MySQL 仓储：`python/repositories/course_repository.py`

### 代码承担的职责

`CourseRepository` 负责：

- 创建和维护 `course_records`、`course_chunks`。
- 写入课程主记录和 chunk 文本。
- 按领域、分类、校区、短 query 召回。
- 按 Milvus 返回的 `course_id` 回表。
- 将 SQL 行和 `raw_json` 合并成 `Course`。

### 支撑的面试故事

支撑“推荐结果可追溯”。最终展示和规则判断都回到 MySQL，不只依赖向量库片段。

### 可追问

- 为什么保留 `raw_json`？
- `fetch_courses_by_ids()` 为什么要尽量保持输入 ID 顺序？
- MySQL DDL 兼容问题如何处理过？

## 12. Milvus 仓储：`python/repositories/course_vector_repository.py`

### 代码承担的职责

`CourseVectorRepository` 负责：

- 连接 Milvus。
- 创建 `course_chunks_real` collection 和索引。
- 对 chunk 文本生成 embedding。
- 写入和检索向量。
- 给 `/health` 提供 `ping()`。

### 支撑的面试故事

支撑“课程按语义粒度拆 chunk”。这让“不要考试、作业少”更容易命中学习体验，而不是被课程名、地点等字段稀释。

### 面试讲法

> Milvus 在这里不是事实库，它只负责帮我找到相关 chunk。命中后还是通过 `course_id` 回 MySQL，这样召回相关性和课程事实各自有边界。

## 13. 重排：`python/agents/course_rerank_agent.py`

### 代码承担的职责

重排 Agent 在候选课程内排序：

- LLM 只能输出候选课程 ID 的 JSON array。
- 解析失败时走规则排序。
- 结果不足时用原候选补齐。
- 控制领域多样性，避免列表过于单一。

### 支撑的面试故事

支撑“LLM 只做候选内决策”。它不创造课程，只判断候选课程的相对优先级。

## 14. 可行性：`python/agents/course_feasibility_agent.py`

### 代码承担的职责

可行性 Agent 输出容量和软风险提醒：

- 满员或容量紧张。
- 考试偏好不匹配。
- 小组作业偏好不匹配。
- 抢课优先级建议。

硬约束主过滤已前移到 `HardConstraintFilter`，这里更偏风险解释。

### 支撑的面试故事

支撑“爆满不一定删除”。真实选课里热门课可能仍值得冲，但系统要透明提醒风险。

## 15. 推荐理由：`python/agents/recommendation_reason_agent.py`

### 代码承担的职责

把最终课程和风险转成学生能理解的理由：

- 每门课一条理由。
- 只能使用输入字段，不编造课程事实。
- 课程爆满、容量紧张、考核不匹配时要提示风险。
- LLM 失败时用字段拼接 fallback 理由。

### 支撑的面试故事

支撑“推荐结果可解释”。学生不仅要知道推荐哪门课，还要知道为什么适合、有什么风险。

## 16. 导入脚本：`python/scripts/ingest_course_dataset.py`

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

支撑“项目不是只写 prompt，而是有数据闭环”。从 CSV 到 MySQL/Milvus，再到推荐接口，可以完整演示。

### 可追问

- 为什么先用 `--limit 20` 或 `--limit 50` 验证？
- 外部 embedding API 抖动时怎么处理？
- 如何验证 MySQL chunk 和 Milvus 实体一致？

## 17. 测试证据

可以优先讲这些测试和验证：

| 证据 | 支撑结论 |
| --- | --- |
| `python/tests/test_course_recall_cache.py` | Redis 命中、未命中、不可用回退 |
| `python/tests/test_supervisor_pipeline.py` | Supervisor 主链路聚合和缓存候选可用 |
| `python/tests/test_hard_constraint_prompt_fallback.py` | 硬约束 prompt 兜底 |
| `python/tests/test_stream_recommend.py` | SSE 事件序列和流式阶段行为 |
| Docker `/health` | MySQL、Redis、Milvus 依赖可连通 |
| Docker `/api/v1/recommend` | 同步推荐链路可达 |
| Docker `/api/v1/stream_recommend` | 流式推荐链路可达 |

注意：这些证明工程链路能跑，不等价于真实业务指标提升。

## 18. 面试自查

- 能不能从 `main.py` 讲到 `SupervisorOrchestrator`？
- 能不能解释为什么 Phase 1.5 放在重排前？
- 能不能说明 Redis、MySQL、Milvus 各自边界？
- 能不能给出至少一个测试文件或 Docker 验证结果？
- 能不能承认当前限制：时间冲突轻量、A/B 进程内、真实业务指标待补充？
