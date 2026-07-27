# 2026-05-16 用户检索端到端链路说明（prompt → 推荐理由）与 Embedding 设计

## 规则来源与 todo 摘要

- 已读取规则文件：`E:/Agent/multi-agent-course-system/.cursor/rules/write-notes-for-project.mdc`。
- 已读取：`tasks/todo.md`。当前文件中最近一轮完成项多与「CSV 字段/容器导入/MySQL DDL/Milvus 清理」等相关；**本节对话未新增 todo 勾选项**，工作内容为**归档与解释** Supervisor 与各 Agent 的检索推荐流水线，并**补充归档 Embedding 实现说明**。
- **测试**：本节仅整理文档说明，未运行 `pytest` 或端到端接口验证。

---

## 本轮要解决什么

1. **检索编排**：用户在检索（推荐）请求中，如何从 `prompt` 经学生画像 Agent、课程召回 Agent、课程重排与选课可行性 Agent，再到推荐理由 Agent，最终得到选课名单与每条理由。
2. **Embedding**：项目中向量如何生成、写入 Milvus、在召回中如何被调用；与 LLM 协议差异、导入顺序与缓存关系。

下面正文与代码路径一致，主要文件：`python/orchestrator/supervisor.py`、`python/agents/*.py`、`python/services/embedding_client.py`、`python/repositories/course_vector_repository.py`、`python/scripts/ingest_course_dataset.py`。

---

## 正文：端到端链路（示例：想上与数学有关的课程）

### 总览：三阶段流水线

```
用户 prompt = "想上跟数学有关的课程"
        │
        ▼
┌──────────── Phase 1（并行）────────────┐
│  StudentProfileAgent  ∥  CourseRecallAgent(profile=None, 宽召回)
│                           │
│  画像产出后 ─────► CourseRecallAgent(profile=画像, 精召回)
└────────────────────────────────────────┘
        │
        ▼
┌──────────── Phase 2（并行）────────────┐
│  CourseRerankAgent  ∥  CourseFeasibilityAgent
└────────────────────────────────────────┘
        │
        ▼
┌──────────── Phase 3（串行）────────────┐
│  RecommendationReasonAgent
└────────────────────────────────────────┘
```

这个编排在 `supervisor.py` 的 `recommend()` 里实现。

### Phase 1A：StudentProfileAgent — 自然语言转结构化画像

`student_profile_agent.py` 用 LLM（temperature=0.2）把 prompt 解析成 `StudentProfile` 对象。

对 "想上与数学有关的课程"，SYSTEM_PROMPT 让 LLM 输出大概这样的 JSON：

```json
{
  "interests": ["数学"],
  "preferred_domains": ["自然环境", "工程技术"],
  "preferred_categories": ["自然科学与工程技术类"],
  "difficulty_preference": "不限",
  "workload_preference": "不限",
  "grade_friendly_preference": "不限",
  "exam_preference": "不限",
  "real_time_tags": {"画像摘要": "学生对数学相关公选课感兴趣"}
}
```

LLM 失败时有兜底——`_heuristic_profile()` 用关键词字典匹配（注意：当前字典里没有"数学"这个 key，因此这种情况会得到空画像，依赖 LLM 输出）。

### Phase 1B：CourseRecallAgent — 两轮召回

#### 第一轮：宽召回（profile=None）

由于这时画像还没出来，Supervisor 并行触发了一次"无画像召回"。`course_recall_agent.py` 中 `_execute()` 的流程：

**1. Redis 缓存 key 构建**

`RecallCacheKeyBuilder.build()` 根据 prompt 文本（无 profile 结构化字段）生成 key。

**2. 缓存命中检查**

缓存命中则直接返回，**完全不调 embedding API**（默认 TTL 内同一 prompt）。

**3. 缓存未命中：双路召回并行**

- **(a) MySQL 结构化召回**：`fetch_courses` + `query_text=self._short_query(query)`；
- **(b) Milvus 语义召回**：`_semantic_course_ids` → `vector_repo.search(query)` → `embedding` → Milvus COSINE，`chunk_id` 解出 `course_id`。

Milvus 会同时命中多种类型的 chunk（例如 `learning_profile`、`audience_tags`、`basic` 中含「数学」或相关描述）。

**4. 合并去重 + 评分**

`_merge_dedup` 后 `_score_candidates`：宽召回阶段 `profile` 为 `None` 时主要靠 query 词命中加分与热度等规则。

**5. 写回 Redis，返回 Top `num_items * 3`。**

#### 画像出来后的第二轮：精召回

若 `student_profile` 存在，再跑一次带画像的召回，并将两轮结果 `_merge_courses` 合并。精召回对应的 cache_key 包含结构化画像字段；`_score_candidates` 会对 domain/category/campus、作业量/考试等偏好加权。

两轮合并后候选课规模常为数十门量级。

### Phase 2A：CourseRerankAgent — LLM 重排

有画像时走 LLM（`_llm_rerank`），输入画像摘要与前若干门候选课的卡片字段；要求考虑爆满热度、多样性、只允许输出候选中存在的 ID。解析失败则用 `_rule_based_rerank`。最后 `_ensure_domain_diversity` 限制同一 `domain` 过多挤占结果。

### Phase 2B：CourseFeasibilityAgent — 选课可行性检查（并行）

与 Rerank **并行**；输入为**召回合并后的候选全集**：

- `_hard_conflicts`：上课时间命中避开时段则剔除；
- `_warnings`：容量满/紧、「不考试」与 `has_exam`、不小组偏好与 `group_work_required` 等软提示；
- `_priority_advice`：抢课/志愿优先级话术。

产出 `available_courses` ID 列表与 `selection_warnings`。

#### Phase 2 汇合

- `ranked_courses` 来自 Rerank；
- `final_courses` = 按 Rerank 顺序过滤到 `available_courses` 内，再 `[:request.num_items]`。

**关键点**：**顺序由 Rerank 决定**，**能否保留由可行性白名单决定**。

### Phase 3：RecommendationReasonAgent — 生成推荐理由

串行：`final_courses` + `warnings` + `student_profile` 交给 LLM，按模板输出每门课的 JSON 理由；解析失败则用 `_fallback_reasons`。

### 最终返回给前端

`RecommendationResponse`：`courses`、`recommendation_reasons`、`selection_warnings`、`experiment_group`、`agent_results`、`total_latency_ms`。

### 「想上与数学有关的课程」时序回顾

| 时刻 | 操作 | 关键产出 |
|---|---|---|
| t=0 | Supervisor 接收 prompt | 用户需求文本 |
| t=0~T1 | **并行**：画像 + 宽召回 | profile、首批候选 |
| t=T1~T2 | 精召回合并 | merged 候选池 |
| t=T2~T3 | **并行**：重排 + 可行性 | ranked、available_ids、warnings |
| t=T3 | 交集截取 | final_courses |
| t=T3~T4 | **串行**：理由 Agent | reasons |
| t=T4 | 返回 RecommendationResponse | 名单 + 理由 + 告警 |

### 设计上值得注意的若干点

1. 召回两轮 + Redis 缓存，减少重复 embedding 调用。
2. Rerank 与 Feasibility 职责分离、可并行。
3. 领域多样性在 Rerank 后处理中强制约束。
4. 多个 Agent 均有规则/兜底路径。
---

## Embedding：整体设计

三层结构：**客户端抽象 → 向量仓库（Milvus）→ 业务（导入脚本 / CourseRecallAgent）**。

- **LLM 与 Embedding 不是同一套协议**（与 `AGENTS.md` 一致）：LLM 走 OpenAI 兼容 `/compatible-mode/v1`；Embedding 走 **DashScope 原生** `api/v1`，请求体为 `input.contents[].text`，响应从 `output.embeddings[].embedding` 取向量；**不要**把 embedding 切到 OpenAI 兼容的 `/embeddings`，否则会报模型不支持。

### 客户端：`python/services/embedding_client.py`

- **抽象**：`EmbeddingClient`，`embed_text` / 默认 `embed_texts` 逐条调用。
- **`LocalDeterministicEmbeddingClient`**：本地与稳定测试用，对文本做 SHA-256 维哈希到固定维度向量并归一化，**不调外部 API**。
- **`DashScopeMultimodalEmbeddingClient`**：生产用，按 `batch_size` 分批 `_embed_batch`。
  - 请求 JSON 形态示例：`model`、`input.contents` 为 `[{"text": "..."}]`、`parameters.dimension` 与配置维度一致（默认 `1152`）。
  - 响应：取 `output.embeddings`，按 `index` 排序后拼成向量列表，并校验条数与维度。
  - 端点由 `_build_endpoint(base_url)` 拼接为 `.../api/v1/services/embeddings/multimodal-embedding/multimodal-embedding`（若 `base_url` 已含完整 path 则沿用）。
- **工厂**：`build_embedding_client()` 读 `get_settings()`：`ECOM_EMBEDDING_PROVIDER` 为 `local` → 本地确定性客户端；为 `dashscope_multimodal` → DashScope；`verify_ssl` 使用 `ECOM_HTTPX_VERIFY_SSL`（MaaS 自定义域名证书 SAN 不匹配时需关校验，与 LLM 侧一致）。

相关环境变量前缀为 **`ECOM_`**，见 `python/config/settings.py`（如 `embedding_model`、`embedding_dimension`、`embedding_batch_size` 等）。

### 向量仓库：`python/repositories/course_vector_repository.py`

- **连接**：`milvus_uri` 或 host/port/user/password；collection 名为 `settings.course_milvus_collection`（默认 `course_chunks_real`）。
- **Schema**：`chunk_id`（VARCHAR 主键）、`course_id`、`chunk_type`、`embedding`（`FLOAT_VECTOR`，维度 `milvus_dimension`，默认与 embedding 一致 **1152**）；索引 metric 默认 **COSINE**，`AUTOINDEX`。
- **写入** `upsert_chunks(chunks)`：取每条的 `content`，`embedding_client.embed_texts(contents)` 得到向量矩阵，再 `upsert` 四列主键/元数据/向量并 `flush`。
- **检索** `search(query, limit)`：对查询语句 `embed_text(query)` 得到查询向量，`collection.search` 返回命中行的主键；当前实现返回 **Milvus 命中的 `chunk_id` 列表**（即 `hit.id`），由上层 `CourseRecallAgent._semantic_course_ids` 用 `chunk_id.split(":", 1)[0]` 还原 **course_id**。

### 导入时的文本切分：`python/scripts/ingest_course_dataset.py`

每门课拆成 **4 类 chunk**（每类一条可嵌入文本），便于不同查询意图命中不同侧面：

| chunk_type | 含义（概括） |
|---|---|
| `basic` | 课程名、教师、学分、类型、分类、方向等 |
| `schedule_capacity` | 校区、时间、地点、容量、选课比例、热度、抢课建议等 |
| `learning_profile` | 简介、考核、难度、作业量、给分、是否考试、小组等 |
| `audience_tags` | 适合人群、标签、历年平均选课比例等 |

`chunk_id` 形如 `{course_id}:{index}:{chunk_type}`。`content` 由 `_render_chunk` 把 CSV 字段渲染成带中文标签的多行文本。

**导入顺序（先 MySQL，后向量库）**：对 CSV 每一行依次 `upsert_course` → `replace_course_chunks`（MySQL）→ `vector_repo.upsert_chunks`（Milvus + embedding）。**无跨库事务**：若 embedding 失败，可能出现「MySQL 已有记录、Milvus 无向量」的半一致状态，需依赖重试或 `scripts/backfill_milvus_vectors.py` 等补数手段（见项目既有说明）。

### 在线召回中与 Embedding 的关系

- **语义路径**：`CourseRecallAgent` 在有 `query` 时调用 `_semantic_course_ids` → `CourseVectorRepository.search`，**每次搜索会对用户 query 调一次 `embed_text`**（除非向量检索在更外层被跳过或失败仅打 log）。
- **Redis 召回缓存**：命中缓存时策略为 `redis_recall_cache_hit` / `redis_recall_cache_wait_hit`，**整条召回短路，不经过 Milvus/embedding**；因此相同画像+prompt 在 TTL 内反复测可能看不到 embedding 调用。

### 数据流小结

```
【离线】CSV → _build_chunks → embed_texts → Milvus.upsert（并行已写 MySQL）

【在线】user query → embed_text(query) → Milvus.search(COSINE) → chunk_ids → course_ids → 与 MySQL 结构化结果合并
```

---

## 经验与后续

- 讲解与代码对齐时务必引用 `RecallCacheKeyBuilder`、Milvus chunk 前缀解析 `chunk_id.split(":", 1)[0]` 等细节实现位置。
- Embedding 侧务必区分 DashScope 原生与 OpenAI 兼容协议；排查「搜不到语义结果」时同时检查 Milvus 是否已有向量、`ECOM_HTTPX_VERIFY_SSL`、以及是否因 Redis 缓存未走 embedding。
- 若需在笔记外落地改进：可考虑在 `_heuristic_profile` 中为「数学」等常见兴趣补充关键词映射，以降低 LLM 不可用时的退化程度（本节未改代码）。
