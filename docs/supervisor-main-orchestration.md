# 流式推荐接口编排细节

本文只说明 `/api/v1/recommend/stream` 的工程链路：请求如何进入 SSE，数据怎样在 `SupervisorOrchestrator.stream_recommend()`、画像、召回、硬过滤、重排、可行性检查、流式理由生成之间转换，以及候选课程的召回依据和打分机制。

文档重点是链路内部的字段转换、召回依据、打分规则、过滤规则、事件输出和异常收口。

## 1. 总体数据流

流式推荐链路可以拆成 6 个处理层：

| 层级 | 代码位置 | 输入 | 输出 | 作用 |
| --- | --- | --- | --- | --- |
| HTTP/SSE 包装 | `python/main.py` | `RecommendationRequest` | `text/event-stream` | 把内部事件转成浏览器可消费的 SSE 帧 |
| Supervisor 编排 | `python/orchestrator/supervisor.py` | request、prompt、context | phase/text/done/error 事件 | 控制阶段顺序、并行关系、聚合结果 |
| 学生画像 | `python/agents/student_profile_agent.py` | user_id、prompt、context | `StudentProfile` | 抽取软偏好和硬约束 |
| 课程召回 | `python/agents/course_recall_agent.py` | profile 或原始 query | `list[Course]` | Redis/MySQL/Milvus/fallback 召回候选并打初分 |
| 过滤与排序 | `hard_constraint_filter.py`、`course_rerank_agent.py`、`course_feasibility_agent.py` | 候选课程、profile、context | `final_courses`、warnings | 删除硬冲突课程，排序并检查容量/时间风险 |
| 流式理由 | `recommendation_reason_agent.py`、`stream_token_markup_parser.py` | final_courses、warnings | `course_start/text/course_end` | 生成课程级 token 事件 |

核心原则是：**前置阶段只确定课程事实和候选集合，Phase 3 才开始输出自然语言 token**。这样不会出现前端已经展示了一门课程理由，但后端后续又把这门课过滤掉的情况。

## 2. 请求入口与 SSE 帧

流式接口入口在 `python/main.py`：

```text
POST /api/v1/recommend/stream
  -> recommend_stream(request)
  -> _recommend_stream_response(request)
  -> StreamingResponse(_sse_wrapper(supervisor.stream_recommend(request)))
```

`stream_recommend()` 自己不拼 HTTP 字符串，只不断产出内部事件：

```text
{"event": "phase", "data": {...}}
{"event": "text", "data": {...}}
{"event": "course_start", "data": {...}}
{"event": "done", "data": {...}}
```

`_sse_wrapper()` 把它转成标准 SSE：

```text
event: phase
data: {"phase":"start","request_id":"...","num_items":3}

event: text
data: {"type":"text","course_id":"GXK001","token":"这门课..."}
```

响应头设置为：

| Header | 值 | 作用 |
| --- | --- | --- |
| `Content-Type` | `text/event-stream` | 告诉客户端这是 SSE 流 |
| `Cache-Control` | `no-cache` | 避免中间层缓存流式响应 |
| `Connection` | `keep-alive` | 保持长连接 |
| `X-Accel-Buffering` | `no` | 避免代理缓冲导致前端迟迟收不到 token |

## 3. Supervisor 初始化

`SupervisorOrchestrator` 初始化时持有 6 个核心对象：

| 成员 | 职责 |
| --- | --- |
| `student_profile_agent` | 从自然语言中抽取兴趣、校区、时间、考试、作业量等偏好与硬约束 |
| `course_recall_agent` | 从 Redis、MySQL、Milvus 和 fallback 中拿候选课程，并做初始打分 |
| `hard_constraint_filter` | 纯内存硬过滤，违反硬约束的课程不进入重排 |
| `course_rerank_agent` | 对候选课程重新排序，失败时走规则排序 |
| `course_feasibility_agent` | 检查时间兜底冲突、容量风险、选课优先级建议 |
| `recommendation_reason_agent` | 对最终课程生成流式自然语言理由 |

这些对象在请求开始前已经创建好。单次请求只生成新的 `request_id`、`start`、`prompt`、`current_phase`、`collected_text` 和 `agent_results`。

## 4. 请求字段如何转成 prompt

流式链路首先从请求中取 prompt：

```text
request.prompt
  -> request.query
  -> request.context["query"]
  -> ""
```

也就是说：

- 如果前端传了 `prompt`，优先使用 `prompt`。
- 如果没有 `prompt`，使用 `query`。
- 如果两者都没有，再从 `context["query"]` 兜底。
- 最终会 `.strip()` 去掉首尾空白。

这个 prompt 后续有三种用途：

| 用途 | 使用位置 | 说明 |
| --- | --- | --- |
| 画像输入 | `StudentProfileAgent.run()` | 抽取结构化画像和硬约束 |
| 宽召回 query | `CourseRecallAgent.run(student_profile=None)` | 不等画像，先基于原始文本召回 |
| 缓存 key / 语义召回 | `RecallCacheKeyBuilder`、Milvus search | 没有结构化条件时，prompt 会进入缓存 payload；有 query 时会走向量召回 |

请求一进入 `stream_recommend()`，会立即发出：

```text
event: phase
data: {"phase":"start","request_id":"...","num_items":request.num_items}
```

这时还没有课程，也没有画像，只表示后端已接管请求。

## 5. Phase 1：画像与宽召回并行

Phase 1 同时启动两件事：

```text
StudentProfileAgent.run(user_id, prompt, context)
CourseRecallAgent.run(student_profile=None, prompt, context, num_items=request.num_items * 2)
```

这里并行的原因是二者都只依赖原始请求：

- 画像需要 LLM 或启发式规则把自然语言转成 `StudentProfile`。
- 宽召回不等画像，先用原始 prompt/context 拿候选，降低用户等待时间。

### 5.1 画像输出的数据结构

画像 Agent 输出 `StudentProfile`，核心字段分两类：

| 类型 | 字段 | 后续用途 |
| --- | --- | --- |
| 软偏好 | `preferred_domains`、`preferred_categories`、`preferred_campus`、`difficulty_preference`、`workload_preference`、`grade_friendly_preference`、`exam_preference`、`group_work_preference` | 参与画像召回、召回打分、重排 prompt、软 warning |
| 硬约束 | `hard_constraints.campus`、`avoid_time_slots`、`categories`、`teacher`、`no_exam`、`no_group_work`、`max_difficulty`、`max_workload` | Phase 1.5 硬过滤，违反即删除 |

硬约束不是全部靠模型判断。代码里还有显式规则补强：

| 输入特征 | 转换结果 |
| --- | --- |
| prompt 中出现 `东校区/南校区/北校区/西校区/主校区` | 合并进 `hard_constraints.campus` |
| prompt 中出现 `自然科学/工程技术/人文/社会科学/心理` | 映射到课程分类并合并进 `hard_constraints.categories` |
| prompt 中出现 `不考试/不要考试/没有考试/没有期末/无考试/免考试` | `hard_constraints.no_exam = true` |
| context 中存在 `hard_campus` | 作为校区硬约束 |
| context 中存在 `hard_avoid_time_slots` | 作为避开时间硬约束 |

如果 LLM JSON 解析失败，画像 Agent 会走 `_heuristic_profile()`：

- 根据关键词把 `艺术/文学/历史/电影` 映射到 `人文艺术`。
- 根据 `环境/生态` 映射到 `自然环境`。
- 根据 `科技/工程` 映射到 `工程技术`。
- 根据 `创业` 映射到 `创新创业`。
- 根据 `心理` 映射到 `社会科学`。
- 根据 `体育` 映射到 `体育健康`。
- 识别校区、不考试、作业少、给分友好、小组作业偏好。

### 5.2 宽召回为什么传 `student_profile=None`

宽召回传 `student_profile=None`，意味着：

- 不使用画像里的 `preferred_domains/categories/campus`。
- 缓存 key 优先从 context 中能拿到的字段构建。
- 如果没有结构化字段，缓存 payload 会退化为 prompt 前 80 个字符。
- MySQL 结构化召回不会加 profile 过滤条件。
- 仍然可以根据短 query 做 LIKE 查询，或根据 query 走 Milvus 语义召回。

宽召回的目标不是最终精准，而是先拿到一批足够大的候选池。

## 6. 召回缓存 key 怎么生成

`RecallCacheKeyBuilder` 先构造 payload，再做 SHA-256：

```text
payload -> json.dumps(sort_keys=True) -> sha256 -> 前 24 位 -> recall:v1:<digest>
```

payload 字段如下：

| 字段 | 来源 |
| --- | --- |
| `domains` | `profile.preferred_domains` |
| `categories` | `profile.preferred_categories` |
| `campus` | 有 profile 时取 `profile.preferred_campus`，否则取 `context["campus"]` |
| `exam` | 有 profile 时取 `profile.exam_preference`，否则取 `context["exam_preference"]` |
| `workload` | 有 profile 时取 `profile.workload_preference`，否则取 `context["workload_preference"]` |
| `grade_friendly` | 有 profile 时取 `profile.grade_friendly_preference`，否则取 `context["grade_friendly_preference"]` |
| `group_work` | 有 profile 时取 `profile.group_work_preference`，否则取 `context["group_work_preference"]` |
| `grade` | `context["grade"]` |
| `major` | `context["major"]` |

如果这些结构化字段全为空，才加入：

```text
payload["prompt"] = normalized_prompt[:80]
```

这样设计的结果是：

- 有明确结构化偏好时，缓存主要按结构化条件复用。
- 没有结构化偏好时，缓存按 prompt 文本复用。
- 列表字段会去空、去空白、排序，避免同一组条件顺序不同导致 cache key 不同。

同时还会生成 `structured_signature`：

```text
payload 去掉 prompt -> sha256 -> 前 16 位
```

它用于语义缓存桶：同一批结构化条件下，再比较 prompt embedding 的相似度。

## 7. 召回完整顺序

`CourseRecallAgent._execute()` 的召回顺序如下：

| 顺序 | 分支 | 命中后做什么 |
| --- | --- | --- |
| 1 | 精确 Redis cache | 读候选 `course_id`，回 MySQL 加载课程，跳过 Milvus |
| 2 | 语义 Redis cache | 在同一 `structured_signature` 桶里找 prompt embedding 近似的旧 key，命中后回 MySQL |
| 3 | Redis 短锁 | 防止多个相似请求同时击穿缓存 |
| 4 | 等待其他请求写缓存 | 未拿到锁时短暂轮询 cache |
| 5 | MySQL 结构化召回 | 按 domains/categories/campus/query_text 查 `course_records` |
| 6 | Milvus chunk 语义召回 | query 转 embedding，搜 `course_chunks_real`，chunk_id 映射 course_id 后回 MySQL |
| 7 | mock fallback | MySQL 和 Milvus 都无候选时返回内置示例课 |
| 8 | 合并、打分、排序、写缓存 | 只缓存排序后的 `course_id` |

Redis 缓存的是 `course_id` 列表，不缓存完整课程对象。命中缓存后仍然调用 `fetch_courses_by_ids()` 回 MySQL，是为了拿到最新容量、时间、考核等事实字段。

## 8. MySQL 结构化召回依据

MySQL 查询表是 `course_records`。召回时传入：

```text
limit = max(num_items * 8, 40)
domains = profile.preferred_domains if profile else None
categories = profile.preferred_categories if profile else None
campus = profile.preferred_campus if profile else None
query_text = _short_query(query)
```

`_short_query(query)` 有一个限制：

- query 为空：返回空。
- query 长度大于 12：返回空。
- 否则返回前 30 个字符。

也就是说，MySQL LIKE 只处理短关键词。长自然语言不会直接拿去 LIKE 全表字段，避免查询过宽和噪声过大。

MySQL 条件：

| 条件 | SQL 行为 |
| --- | --- |
| domains | `domain IN (...)` |
| categories | `course_category IN (...)` |
| campus | `campus IN (...)` |
| query_text | `course_name/teacher/course_category/domain/campus/time_slot/tags LIKE :query_text` |

排序：

```text
ORDER BY popularity_level DESC, current_enrolled DESC, course_id ASC
```

这里的 MySQL 排序不是最终推荐排序，只是结构化召回阶段的初始候选顺序：热门、当前选课人数高的课程会更靠前进入候选池。

## 9. Milvus 语义召回依据

只要 query 非空，召回 Agent 会调用：

```text
CourseVectorRepository.search(query=query, limit=num_items * 5)
```

处理流程：

1. 用 embedding client 把 query 转成向量。
2. 在 Milvus collection `course_chunks_real` 的 `embedding` 字段上搜索。
3. 输出字段包含 `chunk_id`、`course_id`、`chunk_type`。
4. `CourseVectorRepository.search()` 返回命中的 `chunk_id`。
5. `CourseRecallAgent._semantic_course_ids()` 从 `chunk_id` 中取 `:` 前面的部分作为 `course_id`。
6. 对 `course_id` 去重，保持命中顺序。
7. 调用 `fetch_courses_by_ids()` 回 MySQL 拿完整课程事实。

Milvus 存的是课程 chunk 向量，不直接作为最终事实源。最终展示用的 `Course` 仍然来自 MySQL。

课程导入时每门课会拆成多个 chunk，例如基础信息、上课容量、学习画像、受众标签等。语义召回命中 chunk，只说明 query 和某段课程文本相似；能否进入最终结果，还要经过打分、硬过滤、重排和可行性检查。

## 10. 语义缓存怎么判断相似

语义缓存不是直接拿任意历史请求复用，而是在同一个 `structured_signature` 桶内比较 query embedding。

写入时保存：

```text
recall:<version>:<digest>              -> ["course_id_1", "course_id_2", ...]
recall:<version>:<digest>:semantic     -> {"cache_key", "structured_signature", "prompt", "embedding"}
recall:semantic:v1:<structured_signature> -> set(cache_key...)
```

读取时：

1. 用当前 query 生成 embedding。
2. 找到同一 `structured_signature` 下的候选 cache key。
3. 跳过当前精确 cache key。
4. 逐个读取历史 embedding。
5. 计算余弦相似度：

```text
cosine = dot(vec_a, vec_b) / (norm(vec_a) * norm(vec_b))
```

1. 取最高分。
2. 只有最高分达到 `course_recall_cache_semantic_threshold` 才复用。

这样可以避免“校区/考试/作业量条件不同，但 prompt 语义相似”时误用缓存。

## 11. 候选合并与初始打分机制

MySQL 和 Milvus 都返回课程后，会先合并去重：

```text
_merge_dedup([semantic_courses, db_candidates])
```

合并方式不是简单拼接，而是按 index 轮询多个结果集：

```text
semantic[0], mysql[0], semantic[1], mysql[1], ...
```

如果课程 ID 已出现，则跳过。这样能避免某一路召回结果完全压住另一条路。

### 11.1 召回初始分公式

`_score_candidates()` 给每门候选课计算 `course.score`：

| 加分项 | 分值 |
| --- | --- |
| query term 出现在课程文本中 | 每个 term `+1.5` |
| `popularity_level >= 3` | `+0.8` |

5/23 迭代移除的加分项（已移至 Rerank `_compute_score()`）：

- ~~domain 匹配 +4.0~~
- ~~category 匹配 +3.0~~
- ~~campus 匹配 +2.0~~
- ~~workload/exam/grade_friendly 偏好~~

语义召回的课程（来自 Milvus）初始分从 COSINE 距离初始化：

```text
course.score = max(0.0, 1.0 - distance)
```

设计说明：

- 召回阶段只负责广度，不做精细画像匹配
- 画像匹配全部移到 Rerank 的 `_compute_score()` 中，避免两阶段评分逻辑重复
- Milvus 的 COSINE 距离现在真正参与排序，而不是像之前一样被丢弃

query term 的切分规则：

```text
re.split(r"\s+|，|,|。", query)
```

匹配文本由以下字段拼接：

```text
course_name + teacher + domain + course_category + description + suitable_for + tags
```

打完分后按 `course.score DESC` 排序，并返回：

```text
courses[: num_items * 3]
```

注意：Supervisor 传给召回的是 `request.num_items * 2`，召回 Agent 内部返回 `num_items * 3`，所以最终候选上限大约是：

```text
request.num_items * 6
```

这个较大的候选池是为了给后面的硬过滤、重排、可行性检查留空间。

## 12. 画像后二次召回（画像召回）

Phase 1 并行结束后，Supervisor 拿到：

```text
student_profile = profile_result.profile
raw_courses = recall_result.courses
```

如果 `student_profile` 存在，会再调用一次召回：

```text
CourseRecallAgent.run(
  student_profile=student_profile,
  prompt=prompt,
  context=context,
  num_items=request.num_items * 2
)
```

这次召回和宽召回的区别：

| 项目 | 宽召回 | 画像召回 |
| --- | --- | --- |
| `student_profile` | `None` | 真实画像 |
| cache payload | context 或 prompt | 画像偏好字段 |
| MySQL filters | 基本不带 profile 条件 | 带 domains/categories/campus |
| 初始打分 | query term + popularity | 额外加入领域、分类、校区、作业、考试、给分偏好 |

两次召回结果通过 `_merge_courses()` 合并：

```text
wide_recall_courses + refined_recall_courses
按 course_id 去重，保留第一次出现的对象
```

同时写入调试字段：

| 字段 | 含义 |
| --- | --- |
| `wide_recall_strategies` | 宽召回命中的策略，如 cache、MySQL、Milvus |
| `refined_recall_strategies` | 画像召回命中的策略（字段名 `refined_*` 未改） |
| `refined_candidate_count` | 合并后的候选数量 |

然后流式接口发出：

```text
event: phase
data: {"phase":"phase1_complete","profile_extracted":true/false,"wide_recall_count":N}
```

## 13. Phase 1.5 硬约束过滤

触发条件：

```text
student_profile 存在
并且 has_active_constraints(student_profile.hard_constraints) 为 true
```

`has_active_constraints()` 会检查：

```text
campus / avoid_time_slots / categories / teacher / no_exam /
no_group_work / max_difficulty / max_workload
```

过滤规则：

| 硬约束 | 过滤条件 |
| --- | --- |
| 校区 | `course.campus not in hc.campus` |
| 分类/领域 | `hc.categories` 与 `course.course_category` 或 `course.domain` 模糊不匹配 |
| 教师 | `hc.teacher not in course.teacher` |
| 不考试 | `hc.no_exam and course.has_exam == 1` |
| 不小组 | `hc.no_group_work and course.group_work_required == 1` |
| 避开时间 | 任一 `avoid` 是 `course.time_slot` 的子串 |
| 难度上限 | 低=0，中=1，高=2，课程难度大于上限 |
| 作业量上限 | 少/低=0，中=1，多/高=2，课程作业量大于上限 |

分类/领域模糊匹配会去掉“类”字后互相包含，例如“工程技术”和“自然科学与工程技术类”可以匹配。

返回三类数据：

| 返回值 | 内容 |
| --- | --- |
| `passing` | 通过所有硬约束的课程，保留原顺序 |
| `filtered_out` | 被过滤课程及 violations |
| `warnings` | 过滤为空或少于阈值时的提示 |

稀疏 warning 规则：

- 如果有过滤发生且 `passing` 为空：`hard_constraint_no_match`，level=`high`。
- 如果有过滤发生且 `len(passing) < 3`：`hard_constraint_sparse`，level=`medium`。

触发后流式接口发出：

```text
event: phase
data: {
  "phase":"phase15_complete",
  "hard_filtered_count": len(filtered_out),
  "remaining_after_filter": len(passing)
}
```

如果没有任何硬约束，Phase 1.5 不执行，也不会发 `phase15_complete`。

## 13.5 Phase 1.75 LLM 语义初筛

触发条件：

```text
student_profile 存在
且 len(raw_courses) > 40
```

如果不满足，Phase 1.75 不执行，候选直接进入 Phase 2。

`supervisor._llm_semantic_filter(courses, profile, target_count=40)` 的处理：

1. 拼课程摘要（每门课一行）：`course_id | name | domain | category | campus | description[:80] | tags[:5] | difficulty | has_exam | popularity`
2. 拼学生画像摘要：interests, domains, campus, exam/difficulty/workload preference, grade
3. 调 LLM（temperature=0, max_tokens=2048）
4. 要求返回 course_id 的 JSON 数组
5. 解析成功 → 筛出对应 Course 对象
6. 解析失败 → 返回空列表

失败时的处理：

- 返回空列表
- `raw_courses` 保持不变
- RerankAgent 的 `_compute_score` 规则预筛作为兜底
- 不会中断流水线

流式事件：Phase 1.75 完成后不单独发事件，候选缩减后直接进入 Phase 2 事件。

面试讲法：

> Phase 1.75 让 LLM 看每门课的一行摘要和学生画像，从 ~150 门中挑出真正语义相关的 40 门。规则只能匹配字段，LLM 能理解"这门 Python 课实际教爬虫，跟学生说的数据分析不对口"。失败时保留原候选，不会比不做更差。

## 14. Phase 2 重排与可行性检查

Phase 2 并行执行：

```text
CourseRerankAgent.run(student_profile, candidates=raw_courses, num_items=request.num_items)
CourseFeasibilityAgent.run(student_profile, courses=raw_courses, context=context)
```

它们可以并行，因为都只依赖 Phase 1.5 后的候选池，互不依赖。

### 14.1 重排输入如何裁剪

如果有画像，重排 Agent 会给模型的候选课程只取前 40 门：

```text
candidates[:40]
```

每门课传入字段：

```text
id, name, teacher, domain, category, campus, time_slot,
popularity_level, difficulty, workload, grade_friendly,
has_exam, group_work_required, assessment, tags
```

模型只能输出候选课程 ID 的 JSON 数组。输出解析失败时，走规则排序。

### 14.2 规则排序公式

`_compute_score(course, profile)` 是重排阶段的统一评分方法（LLM 和规则路径都用它做预筛）。

| 条件 | profile_score 加减 |
| --- | --- |
| `course.domain in profile.preferred_domains` | `+4.0` |
| `course.course_category in profile.preferred_categories` | `+3.0` |
| `course.campus == profile.preferred_campus` | `+2.0` |
| `profile.workload_preference` 且 `workload in ("低","少")` | `+1.5` |
| `profile.exam_preference == "不考试"` 且 `has_exam == 0` | `+1.5` |
| `profile.grade_friendly_preference` 且 `grade_friendly in ("高","中")` | `+1.2` |
| `popularity_level >= 4` | `-0.4` |
| `profile.grade in ("大一","大二")` 且 `popularity_level >= 4` | 额外 `-2.0` |

最终分公式：

```text
milvus_sim = course.score  # 由召回阶段写入的 COSINE 相似度
final = profile_score * (1.0 + milvus_sim * 0.5)
```

即 Milvus 相似度作为**加权乘法放大器**：向量命中的课程，profile 分会被放大最多 50%。

LLM 重排前预过滤：

- 候选先用 `_compute_score()` 排序
- 取前 40 门送入 LLM
- 提升 LLM 输入质量，避免 40 门中混入低相关课程

`_rule_based_rerank()` 直接使用 `_compute_score()` 产出的分数倒序取 `num_items` 个 course_id。

如果模型或规则排序输出不足，重排 Agent 会按原候选顺序补齐；最后再做领域多样性：

- 每个 `domain` 最多先放 3 门。
- 如果这样不够 `num_items`，再从剩余课程里补。

### 14.3 Supervisor 再做允许集合校验

Supervisor 不完全信任重排输出，会再做一次过滤：

```text
allowed_course_ids = {course.course_id for course in raw_courses}
ranked_courses = [course for course in ranked_courses if course.course_id in allowed_course_ids]
```

这一步防止模型输出了不在候选池里的课程 ID。

## 15. 可行性检查与 warnings

可行性 Agent 对 Phase 1.5 后的候选池逐门检查：

1. `_hard_conflicts()`：兜底检查避开时间。
2. `_warnings()`：生成容量和软偏好 warning。
3. `_priority_advice()`：生成抢课优先级建议。

### 15.1 兜底硬冲突

Phase 1.5 已经处理主要硬约束。可行性这里只保留时间冲突二次保险：

```text
avoid_time_slots = context["avoid_time_slots"] + profile.avoid_time_slots
如果 avoid 是 course.time_slot 子串 -> filtered
```

被过滤的课程进入 `filtered_courses`，不会进入 `available_courses`。

### 15.2 容量 warning

| 条件 | warning |
| --- | --- |
| `capacity > 0 and current_enrolled >= capacity` | `capacity_full`，level=`high` |
| `capacity > 0 and current_enrolled / capacity >= 0.85` | `capacity_tight`，level=`medium` |

容量 warning 不会把课程从 `available_courses` 删除，只是提醒前端和理由生成阶段：这门课需要优先抢或准备替代课。

### 15.3 软偏好 warning

| 条件 | warning |
| --- | --- |
| `profile.exam_preference == "不考试"` 且 `course.has_exam == 1` | `exam_soft_mismatch` |
| `profile.group_work_preference == "不小组"` 且 `course.group_work_required == 1` | `group_work_soft_mismatch` |

这些是低优先级提醒，不是硬过滤。真正的“不考试硬约束”已经在 Phase 1.5 用 `hard_constraints.no_exam` 处理。

### 15.4 抢课优先级建议

| 条件 | 建议 |
| --- | --- |
| `popularity_level >= 4` 或已满 | 冲刺优先级高，建议优先抢并准备替代课 |
| 容量比例 `>= 0.85` | 容量偏紧，建议排在前序志愿 |
| 其他 | 容量相对可控，可作为稳妥备选 |

### 15.5 LLM 个性化抢课建议

当 `final_courses` 数量 <= 12 时，FeasibilityAgent 会调 LLM 生成个性化建议：

```text
_llm_priority_advice(courses[:12], profile)
max_tokens=4096, temperature=0.3
```

LLM 会考虑：

- 课程容量和当前选课比例
- 学生年级（大四 > 大三 > 大二 = 大一 的优先权）
- 课程热度等级
- 可能的替代课程

返回 `dict[course_id, PriorityAdvice(advice, priority)]`：

- `advice`：个性化建议文本（如"你是大二，这门课大三大四优先选，建议准备替代课"）
- `priority`：high/medium/low

超过 12 门或 LLM 失败时，走规则 batch：

- popularity >= 4 或已满 → high，"冲刺优先级高"
- 容量比例 >= 0.85 → medium，"排在前序志愿"
- 其他 → low，"稳妥备选"

`_parse_advice_json` 返回空 dict 时**不抛异常**，静默回退规则。排查时搜 `llm_advice_failed` 或 `llm_advice_parse_empty` 日志。

数据流：`FeasibilityAgent.priority_advice → Supervisor → RecommendationResponse.priority_advice → SSE done 事件 → 前端渲染`。

## 16. final_courses 怎么形成

Phase 2 完成后，Supervisor 有：

```text
ranked_courses        # 重排后的课程顺序
available_ids         # 可行性检查认为可选的课程 ID
warnings              # Phase 1.5 + 可行性 warning
```

最终课程计算：

```text
final_courses = [
  course for course in ranked_courses
  if course.course_id in available_ids
]
final_courses = final_courses[: request.num_items]
```

如果数量不足，追加 `requested_count_shortage` warning。这个 warning 记录：

| 字段 | 含义 |
| --- | --- |
| `requested_count` | 用户请求数量 |
| `final_count` | 最终返回数量 |
| `ranked_count` | 重排后课程数量 |
| `available_count` | 可行性通过数量 |
| `candidate_count` | Phase 2 输入候选数量 |

随后发出：

```text
event: phase
data: {
  "phase":"phase2_complete",
  "ranked_count": len(ranked_courses),
  "available_count": len(available_ids),
  "warning_count": len(warnings),
  "final_count": len(final_courses)
}
```

## 17. Phase 3 流式理由生成

Phase 3 只接收最终课程：

```text
RecommendationReasonAgent.astream_reasons(
  profile=student_profile,
  courses=final_courses,
  warnings=warnings
)
```

如果 `final_courses` 为空，`astream_reasons()` 直接结束，不输出课程理由 token。

### 17.1 课程 payload

传给理由生成的每门课程字段：

```text
course_id, course_name, teacher, domain, campus, time_slot,
difficulty, workload, grade_friendly, has_exam, assessment,
popularity_level, rush_advice, tags
```

它不再接收召回过程中的 MySQL/Milvus 命中细节，也不接收被硬过滤掉的课程。Phase 3 的职责只是解释最终课程为什么被推荐，以及自然融入 warnings。

### 17.2 marker 协议

流式 prompt 要求模型输出：

```text
总起语，不带 marker

[COURSE:GXK001:电影艺术赏析] 课程理由...

[COURSE:GXK002:Python程序设计] 课程理由...
```

marker 正则：

```text
^\[COURSE:([a-zA-Z0-9_-]+):(.+?)\]$
```

也就是：

- 第一段是 `course_id`。
- 第二段是 `course_name`。
- 整个 marker 必须从 `[` 到 `]` 完整匹配。

### 17.3 Parser 状态机

`StreamTokenMarkupParser` 有两个状态：

| 状态 | 含义 |
| --- | --- |
| `idle` | 正常透传文本，遇到 `[` 才进入 buffering |
| `buffering` | 正在收集可能是 marker 的内容 |

处理规则：

1. `idle` 状态下，普通文本直接输出 `text`。
2. 遇到 `[`，开始把字符放进 `_buffer`。
3. 直到遇到 `]`，尝试用 `MARKER_PATTERN` 匹配。
4. 匹配成功：
   - 如果已有当前课程，先发 `course_end`。
   - `course_index += 1`。
   - 更新 `_current_course_id`。
   - 发 `course_start`，包含 `course_id`、`course_name`、`index`。
5. 匹配失败：
   - 把 buffer 当普通 `text` 输出。
6. token 流结束：
   - 如果还在 buffering，先 flush 成 text。
   - 如果有当前课程，发最后一个 `course_end`。

`MAX_BUFFER = 256`，如果 marker 缓冲超过 256 字符还没闭合，会 flush 成普通文本，避免异常输出导致 parser 无限缓存。

## 18. Phase 3 超时和 token 收集

Supervisor 在进入 Phase 3 时记录：

```text
phase3_stream_start = time.perf_counter()
```

每收到一个 chunk 都检查：

```text
elapsed = time.perf_counter() - phase3_stream_start
if elapsed > settings.stream_timeout_seconds:
  yield error STREAM_TIMEOUT
  return
```

这个超时只约束 Phase 3 token 流。Phase 1/1.5/2 的耗时不会挤占流式理由生成预算。

Supervisor 还会收集 `text`：

```text
course_id = chunk.get("course_id") or "__prelude__"
collected_text[course_id] += chunk["token"]
```

含义：

- 总起语没有课程 ID，归到 `__prelude__`。
- 课程 marker 之后的文本归到对应 `course_id`。
- 最终 `done` 事件只把非 `__prelude__` 的内容转成 `recommendation_reasons`。

## 19. 流式事件序列

完整成功路径通常是：

| 顺序 | event | data 关键字段 |
| --- | --- | --- |
| 1 | `phase` | `phase=start`、`request_id`、`num_items` |
| 2 | `phase` | `phase=phase1_complete`、`profile_extracted`、`wide_recall_count` |
| 3 | `phase` | `phase=phase15_complete`、`hard_filtered_count`、`remaining_after_filter` |
| 4 | `phase` | `phase=phase2_complete`、`ranked_count`、`available_count`、`warning_count`、`final_count` |
| 5 | `phase` | `phase=phase3_start` |
| 6 | `text` | 总起语 token，`course_id=null` |
| 7 | `course_start` | `course_id`、`course_name`、`index` |
| 8 | `text` | 当前课程理由 token |
| 9 | `course_end` | 当前课程 `course_id` |
| 10 | `phase` | `phase=phase3_complete` |
| 11 | `done` | 最终课程、理由、warnings、agent_results、耗时 |

如果没有硬约束，顺序 3 不出现。如果 Phase 1.75 执行（profile 存在且候选 >40），候选会在顺序 3 和 4 之间被缩减至 ~40 门，但不会产生额外的流式事件——缩减结果体现在顺序 4 的 `ranked_count` 中。

如果 Phase 3 超时：

```text
event: error
data: {
  "code": "STREAM_TIMEOUT",
  "message": "流式超时 (...)",
  "phase": "phase3",
  "agent": "recommendation_reason",
  "request_id": "..."
}
```

如果其他未捕获异常：

```text
event: error
data: {
  "code": type(exc).__name__.upper(),
  "message": str(exc),
  "phase": current_phase,
  "request_id": "..."
}
```

## 20. done 事件结构

`done` 是流式链路的最终快照：

| 字段 | 生成方式 |
| --- | --- |
| `request_id` | Supervisor 在请求开始生成 |
| `user_id` | 原请求字段 |
| `courses` | `final_courses` 做 `model_dump()` |
| `recommendation_reasons` | 从 `collected_text` 按 course_id 拼回 |
| `selection_warnings` | Phase 1.5 warning + feasibility warning + shortage warning |
| `experiment_group` | `ABTestEngine.assign(user_id)` |
| `agent_results` | 已完成 Agent 的 `model_dump()` |
| `total_latency_ms` | 从请求进入 `stream_recommend()` 到 done 的耗时 |

`done` 不是重新跑一次推荐，而是把前面阶段已经形成的数据收口。

## 21. 一次请求中的数据形态变化

下面按顺序看数据如何变形：

| 阶段 | 变量 | 形态 |
| --- | --- | --- |
| 入口 | `request` | `RecommendationRequest(user_id, num_items, prompt/query/context)` |
| prompt 提取 | `prompt` | 字符串 |
| Phase 1 画像 | `profile_result.profile` | `StudentProfile` |
| Phase 1 宽召回 | `recall_result.courses` | `list[Course]`，带 `score` |
| 画像召回 | `refined_result.courses` | `list[Course]`，用 profile 加强召回和打分 |
| 合并 | `raw_courses` | 去重后的候选课程列表 |
| Phase 1.5 | `raw_courses` | 删除违反硬约束的课程 |
| Phase 2 重排 | `ranked_courses` | 按推荐优先级排序后的课程 |
| Phase 2 可行性 | `available_ids` | 可选课程 ID 集合 |
| 交集 | `final_courses` | `ranked_courses ∩ available_ids` 后截断 |
| Phase 3 | `chunk` | `course_start/text/course_end` |
| 收集 | `collected_text` | `{course_id: "理由文本"}` |
| 结束 | `done.data` | 给前端固化展示的最终结构 |

## 22. 关键策略汇总

| 问题 | 当前策略 |
| --- | --- |
| 画像慢 | 宽召回不等画像，先并行拿候选 |
| 画像不准 | 有启发式兜底，且硬约束有 prompt/context 规则补强 |
| 召回缓存脏 | Redis 只存 ID，命中后回 MySQL 加载最新课程 |
| 相似请求重复召回 | 精确 cache + 同结构化签名下的语义 cache |
| 缓存击穿 | cache miss 后尝试短锁，拿不到锁就短暂等待已有请求写缓存 |
| 长 prompt LIKE 噪声大 | MySQL LIKE 只接受短 query |
| 语义召回只命中 chunk | chunk_id 映射 course_id，再回 MySQL 拿课程事实 |
| 召回结果来源不均衡 | semantic 和 MySQL 按 index 交错合并 |
| 初始排序依据不透明 | `_score_candidates()` 明确加分项并写入 `course.score` |
| 硬约束被排序覆盖 | Phase 1.5 在重排前确定性删除违规课程 |
| 模型输出不存在课程 | Supervisor 用 `allowed_course_ids` 再过滤 |
| 容量满但仍匹配 | 不直接删除，输出 high warning 和抢课建议 |
| 前端要实时反馈 | 前置阶段发 phase，Phase 3 发 token，最后 done 收口 |
| token 无法归属课程 | marker + parser 转成 course_start/text/course_end |

## 23. ReAct 编排分支

触发条件：

```text
ABTestEngine.assign(user_id) == "react"
```

当前 `ab_test.py` 仅注册 `control` 和 `treatment_llm`，**`react` 未注册**。需要在 `services/ab_test.py:48` 添加 `react` group 才能通过 A/B 触发。

`_react_recommend()` 的执行：

1. 用 `build_tool_calling_llm(REACT_TOOLS)` 创建工具调用 LLM
2. System prompt 定义工具链顺序约束
3. 最多 10 轮：
   - LLM 返回 tool_calls
   - ReactToolExecutor 分发到对应 Agent 方法
   - 结果作为 observation 回传 LLM
   - LLM 决定下一步
4. 循环结束后检测：如果 `ReactState.hard_filtered == False`，强制补调 `filter_hard_constraints`

7 个工具：

| 工具 | 是否可跳过 | 说明 |
| --- | --- | --- |
| extract_profile | 是 | 提取学生结构画像 |
| search_courses | 是 | 召回，strategy=wide/refined |
| filter_hard_constraints | 否（锁死） | 硬约束过滤，循环结束时自动补调 |
| semantic_filter_courses | 是 | LLM 语义初筛 |
| rerank_courses | 是 | 重排序 |
| check_feasibility | 是 | 可行性检查 |
| generate_reasons | 是 | 生成推荐理由 |

ReAct vs Pipeline 的关系：

- 正常请求：ReAct 走直线（画像→召回→过滤→排序→可行性→理由），等价于 Pipeline
- 异常分支：召回不足时 LLM 可决定 wide 再搜一轮；硬过滤后不够时放宽条件；全爆满时寻找替代
- Token 增量：正常路径 +0（与 Pipeline 相同），异常路径 +1-2 轮（200-500 token/轮）
