# Milvus 语义召回与缓存链路问答复盘

## 背景与问题

- 本轮要解决的问题：澄清 `CourseRecallAgent` 中 Milvus 向量检索的完整代码路径，以及与 Redis 精确/语义缓存的关系；补充 `chunk_id` 格式、`index` 含义、`_semantic_course_ids` 职责等实现细节。
- 触发原因或用户诉求：阅读 `docs/supervisor-main-orchestration.md` 与 `course_recall_agent.py` 时，对「query → embedding → Milvus → course_id」及缓存层顺序存在疑问。
- 影响范围：仅文档/知识澄清，未修改业务代码、配置或测试。

## 总体架构方案

- 涉及模块：
  - `CourseRecallAgent`（召回编排、缓存探测、chunk→course 映射）
  - `CourseVectorRepository`（Milvus connect/search/upsert）
  - `EmbeddingClient` / `build_embedding_client()`（query/chunk 文本转向量）
  - `CourseRecallCacheRepository`（Redis 精确缓存 + 语义缓存桶）
  - `CourseRepository.fetch_courses_by_ids()`（Milvus 命中后回 MySQL 取课程事实）
- 数据流或调用链（完整召回路径，缓存均 miss 时）：

```text
CourseRecallAgent._execute()
  → exact cache miss
  → semantic cache miss（可选，见下）
  → lock / wait miss
  → MySQL 结构化召回 fetch_courses()
  → _semantic_course_ids(query, limit=num_items*5)
       → CourseVectorRepository.search()
            → embed_text(query)           # 1152 维向量
            → Collection.search(anns_field=embedding, COSINE)
            → [chunk_id, ...]
       → split(":")[0] 去重 → course_ids
  → fetch_courses_by_ids(semantic_ids)
  → _merge_dedup + _score_candidates
  → set_course_ids + index_semantic_cache（若拿到锁）
```

- 缓存决策顺序（**先于 Milvus**）：

| 顺序 | 机制 | 命中后 |
|------|------|--------|
| 1 | Redis 精确缓存 `recall:v1:{digest}` | 跳过 Milvus，`strategies: redis_recall_cache_hit` |
| 2 | Redis 语义缓存（同 `structured_signature` 桶内 embedding 余弦 ≥0.9） | 复用历史 cache_key 的 course_ids，跳过 Milvus，`redis_recall_cache_semantic_hit` |
| 3 | lock wait | 跳过 Milvus，`redis_recall_cache_wait_hit` |
| 4 | 完整召回 | 执行 Milvus + MySQL |

- 关键设计取舍：
  - Milvus 存 **chunk 级**向量（约 500 课 × 4 chunk = 2000 条），输出需映射为 **course 级**候选。
  - Milvus 不是事实源；完整 `Course` 对象始终来自 MySQL `course_records`。
  - 语义缓存缓存的是「历史相似 query 的 course_id 列表」，不是 Milvus 替代品。

## 细节实现

- 修改或分析的关键文件：
  - `python/repositories/course_vector_repository.py`
  - `python/services/embedding_client.py`
  - `python/agents/course_recall_agent.py`
  - `python/repositories/course_recall_cache_repository.py`
  - `python/scripts/ingest_course_dataset.py`
  - `python/config/settings.py`

- 核心逻辑：

### 1. Milvus 搜索入口

`CourseVectorRepository.search()` 是唯一封装层；底层调用 pymilvus `Collection.search()`：

```python
vector = self.embedding_client.embed_text(query)
results = self._collection.search(
    data=[vector],
    anns_field="embedding",
    param={"metric_type": "COSINE", "params": {}},
    limit=limit,
    output_fields=["chunk_id", "course_id", "chunk_type"],
)
return [hit.id for hit in results[0]]  # 仅返回主键 chunk_id
```

- Collection：`course_chunks_real`（`ECOM_COURSE_MILVUS_COLLECTION`）
- 索引：`embedding` 字段 AUTOINDEX + COSINE
- 维度：1152（`milvus_dimension` / `embedding_dimension` 对齐）
- **注意**：虽请求 `output_fields`，当前实现未读取 `hit.entity["course_id"]`，course_id 由上层从 `chunk_id` 前缀解析。

### 2. embed_text

- 接口：`EmbeddingClient.embed_text(text: str) -> list[float]`
- 生产默认 `dashscope_multimodal`：DashScope 原生 API，`tongyi-embedding-vision-plus-2026-03-06`，非 OpenAI 兼容 `/embeddings`。
- Milvus 检索路径：`search()` 内对 **query** 调一次 `embed_text`。
- 语义缓存路径：精确 cache miss 后可能再调 1 次 `embed_text` 做 Redis 桶内相似度匹配；完整 miss 路径最多 3 次 embedding（语义探测 + Milvus + 索引写入）。

### 3. _semantic_course_ids

```python
chunk_ids = self.vector_repo.search(query=query, limit=limit)
for chunk_id in chunk_ids:
    course_id = str(chunk_id).split(":", 1)[0]
    if course_id and course_id not in course_ids:
        course_ids.append(course_id)
return course_ids, "hit" | "empty" | "failed"
```

- 返回三元状态：`hit`（有有效 course_id）、`empty`（无命中或解析为空）、`failed`（search 异常，可降级继续 MySQL 结构化召回）。
- `limit = num_items * 5` 限制的是 **chunk 数**，去重后 course 数通常更少。

### 4. chunk_id 与 index

导入时（`ingest_course_dataset.py`）：

```python
for index, (chunk_type, fields) in enumerate(chunk_specs):
    chunk_id = f"{row['course_id']}:{index}:{chunk_type}"
```

| index | chunk_type |
|-------|------------|
| 0 | basic |
| 1 | schedule_capacity |
| 2 | learning_profile |
| 3 | audience_tags |

- `index` 依据 **`chunk_specs` 列表的 enumerate 顺序**，全库固定 0～3，与 Milvus 相似度排名无关。
- MySQL `course_chunks.chunk_index` 与 `chunk_id` 中间段一致。

- 兼容性与风险控制：
  - Milvus/embedding 失败不阻断整条召回（`failed` 降级）。
  - Redis 缓存命中时 `milvus_skipped=True`，15 分钟内相同 structured key 不会触发 embedding/Milvus。

## Debug 结论

- 根因：本轮无 bug 修复，属架构/代码阅读类问答。
- 排查过程：对照 `supervisor-main-orchestration.md`、`course_vector_repository.py`、`course_recall_agent.py`、`embedding_client.py`、`course_recall_cache_repository.py`、`ingest_course_dataset.py` 交叉验证。
- 解决方式：通过文档化澄清以下易混点：
  1. 「精确 cache miss → 直接 Milvus」表述不完整，中间还有语义缓存与 wait 路径。
  2. `output_fields` 含 `course_id`/`chunk_type`，但 `search()` 只返回 `hit.id`（chunk_id）。
  3. `chunk_id` 中 `index` 是导入时的固定分块序号，不是检索排名。

## 测试与验证

- 已执行：代码只读对照（Read/Grep），未运行 pytest、Docker、curl 或真实 embedding/Milvus 调用。
- 结果：结论与当前仓库源码一致。
- 未执行及原因：本轮为 Ask 模式下的知识澄清 session，无代码变更，无需运行时验证。

## 经验与后续

- 本轮经验：
  - 讲解召回链路时应按 **缓存层 → MySQL 结构化 → Milvus chunk → MySQL  hydrate → merge/score** 顺序，避免跳过语义缓存。
  - `chunk_id` 三段式 `{course_id}:{index}:{chunk_type}` 中，`index` 与 `chunk_type` 在导入逻辑里一一对应，检索阶段只用 `course_id` 前缀。
  - 一次完整 cache miss 可能对同一 query 多次调用 `embed_text`，面试/排障时可作为 latency 关注点。
- 后续建议：
  - 若优化 embedding 调用次数，可考虑在 Agent 层缓存单次 `embed_text(query)` 结果供语义缓存探测与 Milvus search 复用。
  - 若需利用 Milvus 距离打分，可从 `hit.distance` 或 `hit.entity` 读取，当前 `_score_candidates` 未使用 Milvus 相似度分数。
