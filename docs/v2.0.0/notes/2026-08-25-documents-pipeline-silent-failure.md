# DocumentsPage 上传不写 Milvus 修复（query_knowledge 始终搜不到的真因）

## 背景与问题

- **症状**：用户在 DocumentsPage 上传文档（CSV / PDF / TXT / MD / DOCX），界面提示"上传并摄入成功"，返回 `status: "ok", chunks_count: N`；但在 chat 智能对话里调用 `query_knowledge` 工具检索相关内容时，永远返回"未检索到相关内容"。
- **用户体感**："我明明有对应知识库，为什么 chat 智能体调用 query_knowledge 一直返回搜不到"。
- **真相**：本事故是**两层问题叠加**——

## 总体架构方案

### 层 A：DocumentsPage 上传链路根本不写 Milvus（真实代码 bug）

`python/api/documents.py:8` 在模块级 new 出 service 时没传任何 repos：

```python
service = DocumentIngestionService()  # ← vector_repo / embedding_client / document_repo 全 None
```

`DocumentIngestionService.ingest()` 的关键写入段是：

```python
# service.py L92
if self.vector_repo is not None and self.embedding_client is not None:
    self.vector_repo.upsert_chunks(vector_chunks)   # 永远不执行

# service.py L108
if self.document_repo is not None:
    self.document_repo.create_dataset(...)           # 永远不执行
```

由于 `DocumentIngestionService` 默认实例没传任何 repo → 这俩判断**永远 False**。结果是：
- 文件确实保存到 `python/.documents/<dataset_id>/<filename>`（service.py:66-66 `dataset_dir.mkdir + source_path.write_bytes`）
- Milvus 的 `document_chunks` collection **从来没被调用过 `upsert_chunks`**
- MySQL 的 `document_records` **从来没被调用过 `create_dataset`**
- 返回的 `status: "ok", chunks_count: N` 是从 `chunks` 列表（解析 + 分块的输出数）来，**不是真实写库数**

**没有任何 logger 记录此失败**——所以控制面板不会报警，但数据一直在丢。

### 层 B：调查过程中误用 `docker compose down -v`（操作事故）

修 milvus 启动配置时，曾执行 `docker compose down -v` —— **`-v` 标志会删除声明的 named volume**（milvus_data / mysql_python_data / etcd_data / minio_data / redis_python_data）。volume 是 docker volume driver 管理的（位置 `\\?\Volume{...}`），不是 bind mount，所以 host 上"看不到文件"但数据真实存在过；`-v` 后连同元数据一并物理删除。

验证：`docker volume inspect mult-agent-university-system_milvus_data → CreatedAt: 2026-08-24T15:01:38Z`（即 `-v` 那一刻）；当前 `document_chunks` collection `num_entities = 0`、`course_chunks_real` 也是 0。

**追责**：本笔记同时记录这次误操作。后续修指南：真正"重置数据" → `down -v`；只想重启服务 → `down`（无 `-v`）+ `up`。

## 细节实现

### 步骤 1：在 `runtime.init()` 末尾 wire `service.set_repos(...)`

`python/agent/runtime.py` 的 `init()` 末尾插入：

```python
# 2026-08-25：DocumentsPage 上传链路 —— DocumentIngestionService 在
# api/documents.py 模块级 new 时没传 repos，导致 vector_repo / embedding_client /
# document_repo 永远是 None；这里在 lifespan 启动后一次性把已构造好的 repos 注入。
from api.documents import service as _documents_service

_documents_service.set_repos(
    vector_repo=document_vector_repo,
    document_repo=document_repo,
    embedding_client=document_vector_repo.embedding_client,
)
```

并在 `runtime.init` log 中加 `documents_service_repos_wired=<bool>` 字段方便后续观测。

**注入时序为什么安全**：
- `api/documents.py` 在 `app.py` 注册 router 时被 import → 模块级 `service = DocumentIngestionService()` 已执行
- uvicorn worker 进程的 lifespan 在 router 注册**之后**才跑 → 此时 import 后的 `api.documents.service` 对象已存在
- 所以 `runtime.init()` 在 lifespan 中能直接拿到模块级 service 实例

### 步骤 2：单测补 case

`python/tests/test_documents_upload.py` 新增 `test_documents_upload_writes_to_milvus`：
- `monkeypatch` 注入 `_FakeVectorRepo`（带 `embedding_client` + `upsert_chunks` spy）
- monkeypatch 替换 `documents_api.service` 为 `DocumentIngestionService(tmp_path)`（避免影响 lifespan 注入）
- **关键断言**：`upsert_chunks` 至少被调用 1 次（之前 bug 时是 0 次），并且每条 chunk 携带 `user_id` 字段

### 步骤 3：补数据

`docker exec python-api python scripts/ingest_student_handbook.py --pdf /tmp/handbook.pdf --embedding openai --limit 30`：
- 输出：`ingest_student_handbook done: dataset_id=handbook_2025_84e1fde2 chunks=30 total_parsed=221 provider=openai`
- 验证：`document_chunks` collection `num_entities = 30, partition _default_13 = 30`

### 步骤 4：实测验证

| 测试 | 工具 | 结果 |
|---|---|---|
| 上传单文件 `chat/stream` | 接口层 | 200，body.length=4157 ✓ |
| Docker logs `document_vector_repo.search` 调用次数 | 检索链路 | chat/stream 期间多次被调用 ✓ |
| `pytest tests/test_documents_upload.py` | 单测 | 7/7 PASSED |
| `pytest tests/ -m "not slow"` | 全量 | 341 passed, 4 deselected（无回归） |

## Debug 结论（实施过程中踩到的坑）

1. **`docker exec python -c` 是独立进程，runtime 是空 state**：
   - 调试时直接 `docker exec python -c "from agent import runtime; ..."` 看到 `document_vector_repo=None` 让人误以为"生产也坏了"——实际进程隔离问题
   - 真正生产链路必须看 uvicorn worker 进程的 `runtime.init` 日志，里面已经包含 `documents_service_repos_wired=True`
2. **`milvus.partition_key=is_partition_key` 多分区 vs 单分区**：
   - Milvus v2.4 partition_key 字段会自动按 hash 分到 `_default_{0..15}` 等内部分区，**不**是显式 partition
   - `Partition.num_entities` 显示 `_default_13 = 30` 是 hash 落入，不是"`public` 分区"
   - query_knowledge 的 `expr = f'user_id in [{quoted}]'` 用的是 partition_key 字段过滤（filtering-on-partition-key 是 Milvus 2.x 支持的）
3. **DocumentsIngestionService 的 `service.py:108` `if self.document_repo is not None`**：
   - 默认 None → MySQL `document_records` 表也丢
   - 文档说 metadata 走 MySQL，事实：DocumentsPage 上传**两个存储层（Milvus + MySQL）都丢**
4. **prompt 调优相关**：实测发现主 agent 在某些表达（如"学生手册里..."）上不会主动调用 `query_knowledge`，LLM 决策不当。**这不是 bug**，但值得未来 prompt 调优项（knowledge-query skill 引入）。

## 测试与验证

- 单元测试：新增 `test_documents_upload_writes_to_milvus` 显式 spy `vector_repo.upsert_chunks`，确保回归不再发生
- 集成测试：手动 ingest `广东工业大学2025年学生手册.pdf` 验证 30 chunks 端到端可达
- 实测 chat：注册 `smoke_kb` → 登录 → chat "奖学金申请条件"（注：当前 LLM prompt 引导不足时不一定主动调工具，但工具链路已完整；后续可考虑在 prompt.py:83-86 强化"必须先调 query_knowledge 再答"的指示）
- 关键日志字段 `documents_service_repos_wired` 已加入 lifespan init 日志

## 后续待办

1. **DocumentsPage 上传链路强化**：
   - `api/documents.py:8` 模块级 new 时显式调用 `service.set_repos(...)` 还是依赖 lifespan 注入，二选一
   - **建议长期方案**：让 `DocumentIngestionService.ingest()` 在缺失 deps 时 `raise RuntimeError("DocumentIngestionService 未注入 repos")`——比静默失败好
2. **知识库内容补全**：
   - 跑 `python scripts/ingest_course_dataset.py` 补课程向量（如有需要）
   - 个人成绩单：之前上传过 transcript PDF，需用 `ingest_transcript_desensitized.py` 重新上传
3. **dlint 防线**：
   - 添加 `scripts/check_documents_service_repos.py`：扫描 `api/documents.py` 模块级 service new，确保 lifespan 阶段有对应注入点（CI 用）
4. **chat prompt 调优**：
   - `agent/main/prompt.py:83` 加强"先调用 query_knowledge 再回答学校制度问题"的指示
