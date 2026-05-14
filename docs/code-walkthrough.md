# 代码讲解指南

本文档按真实执行顺序讲解当前公选课推荐主链路，目标是让你能在面试中从入口、编排、Agent、数据层到导入脚本完整讲清楚。

推荐阅读顺序：

1. `python/main.py`
2. `python/config/settings.py`
3. `python/models/schemas.py`
4. `python/orchestrator/supervisor.py`
5. `python/orchestrator/graph.py`
6. `python/agents/base_agent.py`
7. `python/agents/student_profile_agent.py`
8. `python/agents/course_recall_agent.py`
9. `python/agents/course_rerank_agent.py`
10. `python/agents/course_feasibility_agent.py`
11. `python/agents/recommendation_reason_agent.py`
12. `python/repositories/course_repository.py`
13. `python/repositories/course_vector_repository.py`
14. `python/scripts/ingest_course_dataset.py`

## 1. `python/main.py`：FastAPI 入口

这个文件负责把系统能力暴露成 HTTP API。

关键对象：

| 对象 | 作用 |
|---|---|
| `settings` | 从 `.env` 和默认值读取配置 |
| `ab_engine` | 进程内 A/B 实验分组 |
| `metrics_collector` | 进程内 Agent 指标统计 |
| `supervisor` | 主推荐编排器 |
| `rec_graph` | LangGraph 展示版本 |
| `mysql_repo`、`redis_repo`、`course_vector_repo` | `/health` 依赖检查 |

启动时 `lifespan()` 做两件事：

1. `_assert_llm_config()` 检查 `ECOM_LLM_API_KEY`、`ECOM_LLM_BASE_URL`、`ECOM_LLM_MODEL` 是否配置。
2. `build_recommendation_graph()` 构建 LangGraph 状态图。

主要接口：

| 接口 | 调用链路 |
|---|---|
| `GET /health` | 检查 MySQL、Redis、Milvus |
| `POST /api/v1/recommend` | 调用 `supervisor.recommend(request)` |
| `POST /api/v1/recommend/graph` | 调用 `rec_graph.ainvoke(state)` |
| `GET /api/v1/experiments` | 返回 `ABTestEngine` 内存状态 |
| `GET /api/v1/metrics` | 返回 `MetricsCollector` 内存指标 |

面试怎么说：

> FastAPI 只做入口和观测，不把业务逻辑写在 Controller 里。真正的推荐流程交给 Supervisor，便于把 API 层、编排层和 Agent 层分开。

## 2. `python/config/settings.py`：配置中心

`Settings` 使用 `pydantic-settings`，统一读取 LLM、Redis、MySQL、Milvus、embedding、Agent 超时和实验配置。

需要注意两点：

- `model_config = {"env_file": ".env", "env_prefix": "ECOM_"}`，所以环境变量仍是 `ECOM_` 前缀。
- `course_milvus_collection` 默认是 `course_chunks`，与历史商品向量的 `milvus_collection=product_embeddings` 区分开。
- `course_recall_cache_*` 控制课程召回缓存 TTL、短锁 TTL 和等待重试次数。

面试怎么说：

> 虽然项目已经改成公选课场景，但我保留了历史 `ECOM_` 前缀，原因是避免破坏已有容器和 `.env`。这是兼容层，不是业务含义。

## 3. `python/models/schemas.py`：请求、响应与领域模型

当前公选课主链路主要用这些模型：

| 模型 | 用途 |
|---|---|
| `StudentProfile` | 学生选课画像，包含兴趣、校区、避开时间、考试、作业量、给分、小组作业等偏好 |
| `Course` | 课程领域模型，包含课程基础信息、容量、时间、限制条件和学习体验字段 |
| `RecommendationRequest` | 推荐请求 |
| `RecommendationResponse` | 推荐响应 |
| `AgentResult` | 所有 Agent 结果基类 |
| `StudentProfileResult` | 学生画像 Agent 输出 |
| `CourseRecallResult` | 课程召回 Agent 输出 |
| `CourseRerankResult` | 课程重排 Agent 输出 |
| `CourseFeasibilityResult` | 选课可行性 Agent 输出 |
| `RecommendationReasonResult` | 推荐理由 Agent 输出 |

`RecommendationResponse` 仍保留 `products`、`marketing_copies` 等字段，这是历史兼容；当前公选课接口主要看 `courses`、`recommendation_reasons`、`selection_warnings`、`agent_results` 和 `total_latency_ms`。

面试怎么说：

> 我没有在改造时强行删除历史字段，因为这会扩大改动面。当前主接口通过新增课程模型和课程结果字段完成场景切换，历史字段作为兼容字段保留。

## 4. `python/orchestrator/supervisor.py`：主编排器

这是最核心的文件。`SupervisorOrchestrator` 初始化 5 个 Agent：

- `StudentProfileAgent`
- `CourseRecallAgent`
- `CourseRerankAgent`
- `CourseFeasibilityAgent`
- `RecommendationReasonAgent`

`recommend()` 的关键流程：

### 4.1 请求初始化

生成 `request_id`，记录开始时间，从 `prompt/query/context["query"]` 中取出实际 prompt，并做实验分组：

```text
request_id = uuid
prompt = _request_prompt(request)
experiment = ab_engine.assign(request.user_id)
```

### 4.2 Phase 1：画像与宽召回并行

`asyncio.gather()` 同时运行：

- 学生画像 Agent：抽取结构化偏好
- 课程召回 Agent：先基于原始 prompt 做宽召回

为什么能并行：

- 课程召回可以先用 prompt 和 context 查 MySQL/Milvus，不必等待画像。
- 画像结果回来后，如果有强约束，再补一次召回。

### 4.3 画像约束补充召回

如果 `student_profile` 存在，就再次调用 `course_recall_agent.run()`，传入画像。这样能利用 `preferred_domains`、`preferred_categories`、`preferred_campus` 等结构化字段补候选。

之后 `_merge_courses()` 按 `course_id` 去重。

### 4.4 Phase 2：重排与可行性并行

`asyncio.gather()` 同时运行：

- `CourseRerankAgent`：决定候选课程优先级
- `CourseFeasibilityAgent`：判断硬冲突和风险提醒

两者都依赖候选课程，但互不依赖，所以可以并行。

### 4.5 最终过滤与推荐理由

根据 `available_ids` 过滤不可选课程，再截断到 `num_items`。最后调用 `RecommendationReasonAgent` 生成解释。

面试怎么说：

> 我先把 Agent 之间的依赖关系画出来，能并行的放进 `asyncio.gather()`，有依赖的串行等待。这样链路耗时更接近最长阶段，而不是所有 Agent 耗时相加。

## 5. `python/orchestrator/graph.py`：LangGraph 展示链路

这个文件用 `StateGraph` 表达同样的业务流程。

状态对象 `PipelineState` 保存：

- 请求信息：`request_id`、`user_id`、`scene`、`num_items`、`prompt`、`context`
- 中间结果：`student_profile`、`raw_courses`、`ranked_courses`、`available_ids`
- 最终结果：`final_courses`、`recommendation_reasons`、`selection_warnings`
- 观测信息：`agent_results`、`total_latency_ms`

节点顺序：

```text
init
  -> parallel_phase1
  -> parallel_phase2
  -> filter
  -> recommendation_reason
  -> aggregate
  -> END
```

和 Supervisor 的区别：

- Supervisor 是主推荐实现，逻辑更直接。
- LangGraph 版本更适合展示“状态图编排”的能力。
- 当前 Graph 版本没有 Supervisor 中“画像成功后补一次 refined recall”的细节，所以对外讲主链路时应以 Supervisor 为准。

面试怎么说：

> 我保留了两种编排表达。生产主链路用普通 Python Supervisor，便于控制细节；LangGraph 版本用于展示状态图和节点式编排思路。

## 6. `python/agents/base_agent.py`：Agent 基类

`BaseAgent` 封装横切能力：

- `run()`：统一入口，记录耗时和成功/失败日志
- `_run_with_retries()`：使用 `tenacity.retry` 做指数退避重试
- `_fallback()`：异常时返回失败的 `AgentResult`
- `error_rate`：根据调用次数和错误次数计算错误率

子类只需要实现 `_execute()`。

面试怎么说：

> 我用模板方法思路设计 Agent 基类。具体 Agent 只关心业务逻辑，重试、耗时、异常 fallback 这些通用能力放在基类，避免每个 Agent 重复写一遍。

## 7. `python/agents/student_profile_agent.py`：学生画像 Agent

职责：把自然语言 prompt 和 context 转成 `StudentProfile`。

输入示例：

```text
想选不考试、作业少、给分友好的艺术类公选课，东校区优先，周三晚上不要有课
```

期望输出字段：

- `interests`
- `preferred_domains`
- `preferred_categories`
- `preferred_campus`
- `preferred_time_slots`
- `avoid_time_slots`
- `difficulty_preference`
- `workload_preference`
- `grade_friendly_preference`
- `exam_preference`
- `group_work_preference`
- `constraints`

关键逻辑：

1. 用系统 prompt 约束 LLM 只输出 JSON。
2. `_parse_json()` 兼容 LLM 返回 Markdown 代码块。
3. JSON 解析失败时 `_heuristic_profile()` 用关键词兜底，例如“艺术”映射到“人文艺术”，“不考试”映射到 `exam_preference=不考试`。
4. `_list()` 把字符串或列表统一转为 `list[str]`。

面试怎么说：

> 画像 Agent 的价值不是简单总结文本，而是把学生的模糊表达转成后续 Agent 能消费的结构化字段。比如“周三晚上不要有课”会进入避开时段，“不想小组作业”会进入小组作业偏好。

## 8. `python/agents/course_recall_agent.py`：课程召回 Agent

职责：从课程数据集中找出候选课程。

召回来源：

| 来源 | 代码 | 适合解决 |
|---|---|---|
| Redis 召回缓存 | `CourseRecallCacheRepository.get_course_ids()` | 多个同学反复询问相似选课需求 |
| MySQL 结构化召回 | `course_repo.fetch_courses()` | 领域、分类、校区、短关键词 |
| Milvus 语义召回 | `vector_repo.search()` + `fetch_courses_by_ids()` | 长 prompt、兴趣、学习体验偏好 |
| mock 兜底 | `_fallback_courses()` | 数据库不可用或无候选时演示链路 |

关键步骤：

1. 根据画像字段和 context 生成召回缓存 key。
2. 先查 Redis 是否已有候选 `course_id` 列表；命中后回 MySQL 拿最新课程。
3. 未命中时尝试 Redis 短锁，避免同一类热门请求同时打到 MySQL/Milvus。
4. 根据画像字段调用 MySQL 查询，先取较大的候选池。
5. 如果有 query，调用 Milvus 搜索 chunk。
6. 从 `chunk_id` 中解析 `course_id`，再回 MySQL 查完整课程。
7. `_merge_dedup()` 交错合并语义召回和结构化召回，按课程 ID 去重。
8. `_score_candidates()` 根据 query 命中、领域、分类、校区、作业量、考试、给分和热度加分。
9. 将候选 `course_id` 列表写回 Redis，后续相似画像可复用。

注意一个细节：`_short_query()` 对长 query 返回空字符串，避免把完整自然语言 prompt 直接塞进 MySQL LIKE。长语义交给 Milvus，短词才走 MySQL 模糊匹配。

面试怎么说：

> 召回不是只靠向量库。向量库适合理解“轻松、给分友好”这类语义，MySQL 更适合校区、分类、容量等精确字段。两者合并后再统一打分，兼顾语义相关性和结构化约束。

## 8.1 `python/repositories/course_recall_cache_repository.py`：召回缓存

这个文件负责把“相似选课画像 -> 候选 course_id 列表”放到 Redis。

核心类：

| 类 | 作用 |
|---|---|
| `RecallCacheKeyBuilder` | 将领域、分类、校区、考试、作业量、给分、小组作业、年级、专业等字段归一化后生成 key |
| `CourseRecallCacheRepository` | 封装 Redis get/set 和 `SET NX EX` 短锁 |

缓存只存 `course_id`，不存完整课程对象。原因是热门课程的容量、已选人数和限制条件可能变化，命中缓存后仍要回 MySQL 获取最新课程状态。

面试怎么说：

> Redis 在这里不是替代 MySQL，而是缓存召回阶段的候选集索引。它减少重复 Milvus 检索和宽召回，但最终课程事实仍以 MySQL 为准。

测试覆盖：

- `python/tests/test_course_recall_cache.py` 验证缓存命中时通过 `CourseRecallAgent.run()` 返回课程，并跳过 Milvus 检索。
- 同一文件验证缓存未命中后会写入候选 `course_id` 列表。
- 同一文件验证 Redis 不可用时仍回退 MySQL + Milvus 原召回链路。
- `python/tests/test_supervisor_pipeline.py` 验证 Supervisor 主链路可以使用缓存召回候选并继续完成重排、可行性检查和推荐理由聚合。

## 9. `python/agents/course_rerank_agent.py`：课程重排 Agent

职责：把候选课程按学生画像重新排序。

LLM 重排的约束：

- 只允许输出候选课程中存在的课程 ID。
- 输出必须是 JSON array。
- 排序要考虑兴趣、校区、时间、考核、学习负担、容量和领域多样性。
- 对爆满课程不直接剔除，但降低稳定性分数。

关键逻辑：

1. 如果没有候选课程，直接返回空列表。
2. 如果有画像，调用 `_llm_rerank()`。
3. 如果无画像或 LLM 输出解析失败，调用 `_rule_based_rerank()`。
4. `_ensure_domain_diversity()` 限制同一领域最多连续占太多结果，避免推荐列表过于单一。
5. 如果 LLM 返回课程数不足，会用原候选列表补齐。

面试怎么说：

> 我没有让 LLM 自由生成课程，而是把候选课程摘要传进去，并要求它只输出课程 ID。这样 LLM 只做排序决策，不负责创造数据，可以降低幻觉。

## 10. `python/agents/course_feasibility_agent.py`：选课可行性 Agent

职责：检查课程是否真的适合加入推荐结果。

硬冲突逻辑 `_hard_conflicts()`：

- `avoid_time_slots` 命中课程 `time_slot`
- 学生年级不满足 `grade_limit`
- 学生专业不满足 `major_limit`
- 缺少 `prerequisite` 要求

风险提醒 `_warnings()`：

- `capacity_full`：已选人数达到或超过容量
- `capacity_tight`：容量使用率达到 85%
- `exam_mismatch`：学生偏好不考试，但课程有考试
- `group_work_mismatch`：学生不想小组作业，但课程要求小组作业

优先级建议 `_priority_advice()`：

- 爆满或满员：冲刺优先级高，同时准备替代课
- 容量偏紧：建议排在前序志愿
- 容量可控：可作为稳妥备选

面试怎么说：

> 我把“不可选”和“有风险”分开处理。时间冲突、专业限制这类是硬过滤；爆满课程不一定删除，因为热门课可能很匹配学生兴趣，所以我保留它但给高风险提醒。

## 11. `python/agents/recommendation_reason_agent.py`：推荐理由 Agent

职责：把最终课程和风险提醒转成学生能理解的建议。

输入给 LLM 的信息：

- 学生画像
- 最终课程列表
- `selection_warnings`

输出格式：

```json
[
  {"course_id": "GXK2026003", "reason": "推荐理由"}
]
```

关键约束：

- 每门课一条理由
- 只能使用输入字段，不能编造数据
- 课程爆满、容量紧张、考核不匹配时要提示风险
- 每条 40-80 字

fallback 逻辑：

如果 LLM 输出解析失败，`_fallback_reasons()` 会用课程名、领域、时间、考核方式和 warning 信息拼出基础理由。

面试怎么说：

> 推荐理由不是装饰，它是让推荐结果可解释的关键。学生不只想知道推荐哪门课，还想知道为什么适合、有什么风险、要不要优先抢。

## 12. `python/repositories/course_repository.py`：MySQL 课程仓库

这个文件负责课程结构化数据。

核心方法：

| 方法 | 作用 |
|---|---|
| `ensure_schema()` | 创建 `course_records` 和 `course_chunks` |
| `upsert_course()` | 写入或更新课程主记录 |
| `replace_course_chunks()` | 替换某门课的 chunk 文本 |
| `fetch_courses()` | 按领域、分类、校区、短查询文本召回课程 |
| `fetch_courses_by_ids()` | 按 Milvus 召回的课程 ID 回表 |
| `_row_to_course()` | 合并 SQL 字段和 `raw_json`，构造 `Course` |

值得讲的细节：

- `raw_json` 保存完整 CSV 行，所以即使 `course_records` 主字段较少，也能回填更多课程属性。
- `fetch_courses_by_ids()` 会保持输入 ID 顺序，避免 Milvus 的相关性排序丢失。
- `tags` 同时兼容列表和字符串，读取时统一拆成 `list[str]`。

面试怎么说：

> MySQL 在这个项目里不是简单存储，而是保证推荐结果可追溯。Milvus 只负责找相关 chunk，最终展示和规则判断都要回到 MySQL 的完整课程记录。

## 13. `python/repositories/course_vector_repository.py`：Milvus 课程向量仓库

这个文件负责课程 chunk embedding 的写入和检索。

核心方法：

| 方法 | 作用 |
|---|---|
| `connect()` | 连接 Milvus，如果 collection 不存在则创建 schema 和索引 |
| `upsert_chunks()` | 对 chunk content 生成 embedding 并写入 Milvus |
| `search()` | 将 query 向量化后检索相似 chunk |
| `ping()` | 供 `/health` 检查 |

Milvus collection 字段：

- `chunk_id`
- `course_id`
- `chunk_type`
- `embedding`

注意：`search()` 返回的是 `hit.id`，也就是主键 `chunk_id`。召回 Agent 再通过 `chunk_id.split(":", 1)[0]` 取 `course_id`。

面试怎么说：

> 我没有把整门课当成一个向量，而是把课程按基础信息、时间容量、学习体验、适合人群拆 chunk。这样用户说“不要考试、作业少”时，更容易命中学习体验 chunk。

## 14. `python/scripts/ingest_course_dataset.py`：课程数据导入脚本

这个脚本把 CSV 变成 MySQL 和 Milvus 可用的数据。

执行方式：

```bash
cd python
python scripts/ingest_course_dataset.py --limit 20
python scripts/ingest_course_dataset.py
```

主要流程：

1. `_read_rows()` 读取 `course_dataset_tools/output/public_elective_courses.csv`。
2. `CourseRepository.ensure_schema()` 确保表存在。
3. 对每一行执行 `upsert_course()` 写主表。
4. `_build_chunks()` 构建四类 chunk。
5. `replace_course_chunks()` 更新 MySQL chunk 文本。
6. `CourseVectorRepository.upsert_chunks()` 写入 Milvus。
7. 最后打印 JSON 格式导入结果。

四类 chunk：

| 类型 | 字段 |
|---|---|
| `basic` | 课程名称、原始课程名、教师、学分、课程类型、课程分类、方向 |
| `schedule_capacity` | 校区、上课时间、地点、限选人数、已选人数、选课比例、热度、抢课建议 |
| `learning_profile` | 课程简介、考核方式、难度、作业量、给分友好度、考勤要求、是否考试、是否小组作业 |
| `audience_tags` | 年级限制、专业限制、先修要求、适合人群、标签、历年平均选课比例 |

面试怎么说：

> 这个导入脚本是项目闭环的关键。它不是把 CSV 直接喂给向量库，而是同时保留结构化主表和语义 chunk，这样后续既能做精确过滤，又能做自然语言召回。

## 15. 一条请求如何走完整链路

以这个 prompt 为例：

```text
想选不考试、作业少、给分友好的艺术类公选课，东校区优先，周三晚上不要有课
```

执行过程：

1. `main.py` 接收请求，调用 `SupervisorOrchestrator.recommend()`。
2. Supervisor 生成 `request_id` 并做实验分组。
3. `StudentProfileAgent` 抽取 `exam_preference=不考试`、`workload_preference=少`、`grade_friendly_preference=高`、`preferred_campus=东校区`、`avoid_time_slots=周三...`。
4. `CourseRecallAgent` 先用 prompt 做 MySQL/Milvus 宽召回。
5. 如果画像存在，再用领域、分类、校区等字段补充召回。
6. `CourseRerankAgent` 在候选课程中排序。
7. `CourseFeasibilityAgent` 过滤时间冲突、年级/专业/先修不满足的课程，并输出容量风险。
8. Supervisor 根据 `available_ids` 得到最终课程。
9. `RecommendationReasonAgent` 生成每门课的解释。
10. API 返回课程、推荐理由、风险提醒、Agent 结果和总耗时。

## 16. 面试自查

- 能否说明为什么不是一个大 prompt 直接推荐？
- 能否讲清 MySQL 和 Milvus 的分工？
- 能否解释为什么课程要拆成四类 chunk？
- 能否说出 Phase 1 和 Phase 2 为什么能并行？
- 能否说明 LLM 幻觉是如何被限制的？
- 能否指出当前项目的真实边界，例如 Redis 已用于召回候选缓存，但还不是学生实时画像来源？
