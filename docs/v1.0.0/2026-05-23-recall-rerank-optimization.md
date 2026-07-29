# 召回-重排链路三项优化复盘

## 背景

基于 `2026-05-22-milvus-recall-flow-qna.md` 对 Milvus 语义召回全链路代码走查，识别出三个优化点并实施。

## 实际实施的优化（3 项）

### #1：消除冗余 embedding API 调用

**问题**：完整缓存未命中路径中，同一 `query` 文本被 embedding 最多 3 次：
- `_semantic_cached_courses()` — 语义缓存探测
- `_semantic_course_ids()` — Milvus 向量检索（通过 `search()` 内部调用）
- `_index_semantic_cache()` — 缓存索引写入

**方案**：在 `CourseRecallAgent._execute()` 入口统一调一次 `embed_text(query)`，将向量传递给三个消费者。方案 A（Agent 层局部变量缓存），不引入外部缓存层。

**改动文件**：
- `python/agents/course_recall_agent.py`：
  - `_execute()` 顶部新增 `query_embedding` 计算，异常时置 None 降级
  - `_semantic_cached_courses()` 新增 `query_embedding` 参数，移除内部 embedding 调用
  - `_index_semantic_cache()` 新增 `query_embedding` 参数，移除内部 embedding 调用
  - `_semantic_course_ids()` 新增 `query_embedding` 参数，透传给 `search()`

**效果**：缓存未命中时，embedding API 调用从 **3 次降为 1 次**。

---

### #2：`search()` 利用 `hit.entity` 返回结构化数据

**问题**：`CourseVectorRepository.search()` 请求了 `output_fields=["chunk_id", "course_id", "chunk_type"]`，但只返回 `hit.id`（即 chunk_id 主键）。上层 `_semantic_course_ids()` 通过 `chunk_id.split(":", 1)[0]` 手动解析 course_id，且 Milvus 返回的 COSINE 距离分数完全丢失。

**方案**（方案 B）：`search()` 改为返回 `list[dict]`，每个 dict 包含 `chunk_id`、`course_id`、`chunk_type`、`distance`。`course_id` 直接从 `hit.entity["course_id"]` 取值，无需字符串解析。`distance` 保留原始 COSINE 距离值，为 #3 铺路。

**改动文件**：
- `python/repositories/course_vector_repository.py`：
  - `search()` 新增 `query_vector` 可选参数（接收预计算向量）
  - 返回类型从 `list[str]` 改为 `list[dict[str, object]]`
  - 用 `hit.entity.get("course_id")` 替代 ID 前缀解析
- `python/agents/course_recall_agent.py`：
  - `_semantic_course_ids()` 改为返回 `tuple[list[str], list[float], str]`（含 distances）
  - 移除 `chunk_id.split(":", 1)[0]` 字符串切割逻辑
  - `_execute()` 中将 distance 转为 `max(0.0, 1.0 - distance)` 存到 `course.score`

---

### #3：召回/重排评分职责分离 + Milvus 距离融入排序

**问题**：Recall 的 `_score_candidates()` 和 Rerank 的 `_rule_based_rerank()` 存在评分逻辑重复（domain/category/campus/workload/exam 等 profile 匹配在两处做或部分做），Milvus 余弦相似度完全不参与排序。

**方案**：
- Recall 侧：`_score_candidates()` 移除所有 profile 匹配逻辑（domain/category/campus/workload/exam/grade_friendly），仅保留关键词匹配 + 热度。semantic 课程的 `course.score` 从 Milvus COSINE 相似度初始化（`max(0.0, 1.0 - distance)`）。
- Rerank 侧：新增 `_compute_score()` 统一评分方法。
  - 公式：`final = profile_score * (1.0 + milvus_sim * 0.5)`，即向量相似度为 **加权乘法放大器**
  - `profile_score` 汇总 domain/category/campus/workload/exam/grade_friendly/popularity/exam/workload 偏好
  - `milvus_sim` 取自 `course.score`（由 recall 写入的相似度值）
- LLM 重排路径：增加 top-40 预过滤——候选集先用 `_compute_score()` 排序，取前 40 门送入 LLM，提升 LLM 输入质量
- 规则重排路径：继续使用 `course.score` 作为基础分（现为 milvus_sim + 关键词匹配）

**改动文件**：
- `python/agents/course_recall_agent.py`：`_score_candidates()` 移除 profile 匹配
- `python/agents/course_rerank_agent.py`：新增 `_compute_score()`，`_llm_rerank()` 增加 top-40 预过滤
- `python/tests/test_course_recall_cache.py`：更新 mock 适配新的 `search()` 返回格式和 `embed_text` mock

---

## 讨论过但未实施的优化（4 项）

### ~~#4：`_merge_dedup` 交替穿插逻辑~~
**撤回原因**：合并后的顺序会被 `candidates.sort(key=score, reverse=True)` 完全覆盖，交替穿插不影响最终输出，#4 不是真问题。

### ~~#5：`smembers` 全量加载 Set 成员~~
**跳过原因**：当前语义缓存采用采样策略（仅比较前 12 个候选），OT(n) 瓶颈不在 `smembers` 的 2MB 网络传输，而在每个成员的 embedding GET + 余弦比较。只有改为"遍历全桶找全局最优"时才会成为问题。当前不改为遍历全桶，故不改。
- 备选方案已记录：若未来桶膨胀，可用 `sscan` 分页或 `SRANDMEMBER` 随机采样替代。

### ~~#6：语义缓存先 embed 再查桶~~
**跳过原因**：#1 实施后自动消失——embedding 不再由语义缓存探测单独触发，而是 `_execute()` 入口统一计算，语义缓存探测只是三个消费者之一。

### ~~#7：`limit = num_items * 5` 纯结构化请求无语义召回~~
**确认无问题**：正常前端聊天框打字时 `query` 不可能为空。仅 curl/Postman 刻意不填 prompt 时会出现，非业务路径。

---

## Redis Stack 向量索引方案评估（未采纳）

**提议**：将语义缓存桶从 `Set + String` 双 key 改为 Redis Stack `FT.INDEX` 向量搜索，合并两个 key，相似度比较在 Redis C 侧完成。

**否决理由**：
- **双向量存储分裂**：Milvus 和 Redis Stack 各自维护独立的 ANN 索引，产生两套 schema 管理、监控、debug 链路
- **ROI 不对等**：`sscan` 分页改 5 行代码可解决核心问题，引入 Redis Stack 解决的是"桶膨胀时的全量读取"——而当前采样语义下桶膨胀不是实际瓶颈
- 备选记录：若未来确实需要服务端向量搜索，可用 `redis/redis-stack-server:7.4.0` 替代 `redis:7-alpine`

---

## 实施记录

- 日期：2026-05-23
- 改动范围：3 个业务文件 + 1 个测试文件
- 测试结果：`39 passed, 0 failed`（not slow）

---

## 语义缓存误命中修复 + 日志重构

**背景**：上线后发现缓存命中时推荐结果与用户意图不匹配。排查确认根因不在精确缓存碰撞，而在**语义缓存对句式相同、关键词不同的 query 误命中**。

### #4：语义缓存误命中修复

**问题场景**：

```
请求A（写缓存）: prompt="我喜欢跨文化交际"  → 全量召回 → 缓存30门跨文化课
请求B（命中）:   prompt="我对跨文化交际非常热爱" → 语义缓存 cosine=0.9602 > 0.9 → 命中A的缓存 ✅（主题相关）

请求C: prompt="我对计算机感兴趣" → 语义缓存在"none"桶中比对 → 
        cosine("我对计算机感兴趣", "我对心理学感兴趣") = ~0.94 > 0.9 → 命中心理学缓存 ❌
```

根因：1024 维向量对"我对 X 感兴趣"这种句式模板的区分度不足。整句 8 个字中 7 个字相同，关键词只差一个字，余弦相似度轻松过 0.9。

**修复**：

| 改动 | 位置 | 作用 |
|------|------|------|
| 语义阈值 0.9 → 0.95 | `config/settings.py:41` | 宁可减少命中率，不给错误结果 |
| `_build_payload()` 始终纳 prompt | `repositories/course_recall_cache_repository.py:77-78` | 删除 `if not any(payload.values())` 条件，即使 profile 有结构化字段，prompt 也参与 cache key |

**效果**：
- 相同 prompt → 精确缓存命中 ✅
- 句式相似但关键词不同的 query → 语义缓存 cosine 大概率 < 0.95 → miss → 走全量召回 ✅

---

### #5：Agent 日志重构

**问题**：5 个 agent（feasibility / rerank / recommendation_reason / student_profile / recall）日志极度臃肿，大量回显完整 Course 对象、profile 对象、LLM response 对象、settings 对象到控制台，难以快速定位关键信号。

**改动原则**：
- 删除所有 `settings=settings`、`course=course`、`profile=profile`、`response=response` 等完整对象回显
- `_execute` 结束日志改为 count 摘要
- 每门课遍历的日志（capacity_full/capacity_tight/exam_soft_mismatch/group_work_soft_mismatch）全部删除
- LLM 调用失败保留 error/warning 日志但精简为事件名，不 dump response
- profile 解析成功只记 domain/campus/hard_constraint 摘要
- 保留所有 info 级关键节点日志（cache_hit/miss、milvus_query、query_embedded 等），确保能定位：
  - 是否走了 Milvus 语义召回
  - 缓存命中是 exact 还是 semantic
  - LLM 调用是否失败
  - embedding/Milvus 是否失败

**改动文件**：
- `python/agents/course_feasibility_agent.py` — 删除 10 行日志
- `python/agents/recommendation_reason_agent.py` — 删除 7 行日志
- `python/agents/student_profile_agent.py` — 删除 8 行日志
- `python/agents/course_recall_agent.py` — 删除 1 行日志
- `python/agents/course_rerank_agent.py` — 删除 6 行日志

---

## 实施记录

- 日期：2026-05-23
- 改动范围：2 个基础设施文件 + 5 个 agent 文件
- 测试结果：`39 passed, 0 failed`（not slow）
