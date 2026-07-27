# Milvus 向量兜底机制保守增强

## 背景与问题

- 本轮要解决的问题：导入链路在 embedding 失败时可能出现 MySQL 已写入、Milvus 缺向量的半一致状态；补数脚本存在日志错误且默认全量 upsert；召回链路缺少对 Milvus 失败/空结果的显式策略标记。
- 触发原因或用户诉求：要求执行“Milvus 向量兜底机制保守增强”，并修复日志问题，不引入数据库结构变更。
- 影响范围：`python/scripts/backfill_milvus_vectors.py`、`python/agents/course_recall_agent.py`。

## 总体架构方案

- 涉及模块：
  - 导入与补数：`ingest_course_dataset.py`、`backfill_milvus_vectors.py`
  - 召回：`CourseRecallAgent`
  - 存储：MySQL `course_chunks`（事实源）+ Milvus `course_chunks_real`（可重建索引）
- 数据流或调用链：
  - 导入时先写 MySQL，再写 Milvus。
  - 召回时缓存优先，未命中走 MySQL 结构化召回，再尝试 Milvus 语义召回；Milvus 异常降级不阻断主流程。
  - 补数时基于 MySQL 与 Milvus 的 `chunk_id` 差异，仅回填缺失向量。
- 关键设计取舍：
  - 不新增 MySQL 状态表/字段，保持保守改动。
  - 不清空集合、不全量重算 embedding，优先最小化外部 API 调用。
  - 增强策略可观测性，便于线上定位“Milvus 失败”和“Milvus 命中为空”的差异。

## 细节实现

- 修改或分析的关键文件：
  - `python/scripts/backfill_milvus_vectors.py`
  - `python/agents/course_recall_agent.py`
- 核心逻辑：
  - `backfill_milvus_vectors.py`
    - 修复未定义 `logger` 的运行时错误（移除该调用，统一使用 `print` 输出）。
    - 新增 `load_mysql_chunks()` 读取 MySQL chunk 数据。
    - 新增 `load_milvus_chunk_ids()` 读取 Milvus 现有 `chunk_id` 集合（优先 `query_iterator`，失败回退 `query`）。
    - 引入 `missing_chunks = MySQL - Milvus` 差异计算，仅对缺失项调用 embedding 并 upsert。
    - 当缺失为 0 时直接 no-op 退出，避免不必要的 embedding 调用。
  - `course_recall_agent.py`
    - `_semantic_course_ids()` 返回 `(course_ids, semantic_status)`，状态为 `hit/empty/failed`。
    - `_execute()` 中按语义状态追加策略：
      - `milvus_vector_search_failed`
      - `milvus_course_chunks_empty`
      - `milvus_course_chunks`
    - 返回 `data` 中新增 `semantic_status` 字段；缓存命中路径和整体降级行为保持不变。
- 兼容性与风险控制：
  - 未修改数据库 schema。
  - 未改动缓存命中短路逻辑。
  - 回填仍保留指数退避重试，仅缩减处理范围为缺失集。

## Debug 结论

- 根因：
  - 补数脚本里存在 `logger.info(...)` 但未定义 `logger`，会导致脚本执行到该行即抛 `NameError`。
  - 补数脚本实际行为是全量 upsert，与“仅补缺失”目标不一致，导致外部 embedding 调用放大。
- 排查过程：
  - 对比读取 `backfill_milvus_vectors.py` 现有实现，确认日志调用和处理范围。
  - 对比 `CourseRecallAgent` 的语义召回分支，确认失败时仅日志告警且策略不可区分。
- 解决方式：
  - 修复脚本日志错误并重构为差异补数。
  - 在召回结果策略中显式标识 Milvus 失败或空结果。

## 测试与验证

- 已执行：
  - `python -m compileall "python/scripts/backfill_milvus_vectors.py" "python/agents/course_recall_agent.py"`：通过。
  - `python -m pytest python/tests/test_course_recall_cache.py python/tests/test_supervisor_pipeline.py -v`：未通过收集阶段。
  - `ReadLints` 检查两个修改文件：无 linter 错误。
- 结果：
  - 编译与静态检查通过。
  - pytest 收集失败原因为当前环境缺少 `redis` 依赖（`ModuleNotFoundError: No module named 'redis'`），未进入测试执行阶段。
- 未执行及原因：
  - 未执行真实 MySQL/Milvus/Embedding 的在线补数回归：本轮按保守增强进行代码级改造与离线校验，且当前本地测试环境依赖不完整。

## 经验与后续

- 本轮经验：
  - 对“可重建索引”场景，优先做差异补数比全量补数更稳，能显著减少外部 API 调用与失败面。
  - 召回链路的降级策略应可观测，便于区分“服务不可用”与“结果为空”。
- 后续建议：
  - 在可用环境补跑 `python/tests` 相关用例（先安装 `python/requirements.txt`）。
  - 在容器或联调环境实际运行 `backfill_milvus_vectors.py`，验证 `missing_chunks` 统计和回填效果。
  - 如后续需要更强可恢复性，再评估引入持久化向量状态字段（本轮未做）。
