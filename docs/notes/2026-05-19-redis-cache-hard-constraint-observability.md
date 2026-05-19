# Redis 缓存与硬约束排查改进（2026-05-19）

## 背景与问题

- 本轮目标：落实“Redis 缓存与硬约束排查改进计划”，解决以下痛点：
  - Docker 里看不到 MySQL 查询日志，难以判断是否走库；
  - 语义相近 prompt 复用缓存不稳定；
  - 硬约束（如西校区、自然科学类）在多条推荐场景下可能失效；
  - 最终推荐条数小于请求数量时，缺乏明确告警。

## 总体架构方案

- 缓存策略：
  - 保留 `recall:v1:<hash>` 的候选 `course_id` 缓存；
  - 增加“结构化签名 + 语义近邻”缓存索引，命中后跳过 Milvus/embedding 召回；
  - 命中后仍回 MySQL `fetch_courses_by_ids`，保证课程事实字段实时。
- 可观测策略：
  - 在 `CourseRecallAgent` / `CourseRepository` / `Supervisor` 打结构化日志；
  - 增补 `agent_results.course_recall.data` 的命中类型、key 后缀、相似度、宽召回/精召回策略。
- 约束与结果稳定性：
  - 对硬约束增加 prompt 确定性兜底提取；
  - 强化分类匹配（模糊匹配“自然科学类”与“自然科学与工程技术类”）；
  - 在 Supervisor 末端增加不足条数 warning，并阻断重排阶段将 Phase1.5 已过滤课程重新混入。

## 细节实现

- 关键文件：
  - `python/repositories/course_recall_cache_repository.py`
  - `python/agents/course_recall_agent.py`
  - `python/repositories/course_repository.py`
  - `python/orchestrator/supervisor.py`
  - `python/agents/student_profile_agent.py`
  - `python/orchestrator/hard_constraint_filter.py`
  - `python/config/settings.py`
  - `python/tests/test_course_recall_cache.py`
  - `python/tests/test_supervisor_pipeline.py`
  - `python/tests/test_hard_constraint_prompt_fallback.py`

- 主要改动：
  - 新增 `RecallCacheContext` 与结构化签名能力；
  - 新增 Redis 语义索引读写方法：
    - `index_semantic_cache()`
    - `find_semantic_cache_key()`
  - `CourseRecallAgent` 新增：
    - 精确命中 / 语义命中 / 等待命中 / 未命中的分支日志；
    - `cache_match_type`、`cache_similarity`、`milvus_skipped` 等返回字段；
    - 语义缓存命中路径 `redis_recall_cache_semantic_hit`；
  - `CourseRepository` 增加 MySQL 查询边界日志（入参数量、行数、耗时）；
  - `Supervisor` 增加：
    - `hard_constraints`、过滤前后课程分布日志；
    - 宽召回/精召回策略并入响应数据；
    - `requested_count_shortage` warning；
    - 仅允许 `raw_courses` 内课程进入最终结果，避免硬约束后被重排结果“混回”。
  - `StudentProfileAgent` 增加 prompt 兜底硬约束提取（校区/类别/no_exam）；
  - `HardConstraintFilter` 增加分类模糊匹配方法 `_fuzzy_text_match()`。

## Debug 结论

- 根因定位：
  - MySQL“无日志”主要是应用侧缺少 Repository 查询日志，不是“没查库”；
  - “西校区 + 自然科学类”出现 0 结果的直接原因是类别文本口径不一致；
  - “同义 prompt 结果不稳”与缓存层级、画像抽取波动、LLM 阶段非确定性共同相关；
  - 之前存在潜在风险：Phase1.5 过滤后若下游 Agent 返回越界课程，可能被最终组装带回。
- 解决方式：
  - 应用层结构化日志补全；
  - 缓存语义索引引入；
  - 硬约束兜底 + 模糊匹配；
  - 最终组装阶段加允许集合约束；
  - 不足条数明确 warning。

## 测试与验证

- 已执行单测：
  - `.\.venv\Scripts\python -m pytest python/tests/test_course_recall_cache.py python/tests/test_supervisor_pipeline.py python/tests/test_stream_recommend.py python/tests/test_hard_constraint_prompt_fallback.py -v`
  - 结果：`14 passed`。

- 已执行端到端验证（Docker）：
  - `docker compose -f docker-compose.python.yml --profile python up -d --build`
  - 调用 `/api/v1/recommend` 复测两组场景：
    1. 硬约束样例：`我要去西校区上课，而且我只要上自然科学类的课`
       - 最终课程均为西校区 + 自然科学与工程技术类；
       - 当结果少于请求数量时返回 `requested_count_shortage` warning。
    2. 语义相近样例（不同措辞）：
       - 响应中出现 `cache_match_type=semantic` 与 `redis_recall_cache_semantic_hit`；
       - 命中时 `milvus_skipped=true`，验证短召回生效。

- 观察到的外部风险：
  - embedding 偶发 SSL EOF（外部服务波动），语义命中路径可在一定程度上降低召回阶段外部依赖频率。

## 经验与后续

- 本轮经验：
  - 仅看容器日志不足以判断调用链，必须在仓储边界打结构化日志；
  - “硬约束文本”与“课程分类枚举”必须做口径映射；
  - 召回缓存与最终结果稳定性是两个层面，需要分别观测与治理。

- 后续建议：
  - 给语义缓存增加命中统计指标（命中率、平均相似度、节省耗时）；
  - 将重排与理由阶段引入可控随机性（seed/低温）进一步提高重复请求一致性；
  - 增加“课程与理由按 `course_id` 对齐校验”，避免展示层错配。
