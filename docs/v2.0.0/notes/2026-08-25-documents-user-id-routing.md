# DocumentsPage 上传链路 user_id 路由修复（query_transcript 终于能查到个人成绩单）

## 背景与问题

- **症状 A**：用户在 DocumentsPage 上传"个人成绩单 PDF"，前端回显成功（`status: ok, chunks_count: N`）；在 chat 智能对话里问"我上学期高数考了多少分"，LLM 调 `query_transcript` 工具却返回"未检索到相关内容"。
- **症状 B**：刷新 DocumentsPage 后，已上传的列表"知识库管理模块为空"，看不到任何历史 dataset。
- **症状 C（隐藏）**：用户上传的所有文档（无论个人成绩单还是手册）都写到 **public 分区**——任何用户调 `query_handbook` 都能查到别人上传的成绩单，**严重数据安全 regression**（本次修复同时解决）。
- **触发原因**：根因 A/B/C 集中在 `python/api/documents.py` 端点层 + MySQL schema 层 + 前端 DocumentsPage 三层。

## 总体架构方案

### 三层修复映射

| 层 | 修复点 | 涉及文件 |
|---|---|---|
| **MySQL schema** | `document_records` 加 `user_id VARCHAR(128) DEFAULT 'public'` + 索引；`PREPARE/EXECUTE` 幂等迁移老表 | `sql/init-db.sql` |
| **后端路由** | `POST /upload` 接收 `user_id`（必填）+ `student_name`（可选）Form 字段；新增 `GET /datasets?user_id=&include_public=`；端点层 `_require_user_id` 兜底 401 | `python/api/documents.py` |
| **后端仓储** | `DocumentRepository.create_dataset(...)` 加 `user_id` 入参 + INSERT 列；`list_datasets(..., user_id, include_public)` SQL 过滤 | `python/storage/mysql/document_repo.py` |
| **前端 API 客户端** | `documentsUpload(files, datasetName, chunkStrategy, userId, studentName)`；新增 `documentsList(userId, includePublic)` | `frontend/src/lib/api.ts` + `frontend/src/types/index.ts` |
| **前端 UI** | useEffect load 已上传列表；Segmented 三 tab（全部 / 手册 / 我的成绩单）；未登录禁用上传按钮；Table 展示 dataset_name / 文件名 / 类型 / chunks / 状态 / 归属（public vs 我的）；提示"成绩单用 query_transcript 工具查询" | `frontend/src/app/(main)/documents/page.tsx` |

### 关键设计决策

| 决策 | 选定 | 原因 |
|---|---|---|
| user_id 传递方式 | **Form 字段** | 与 dataset_name / chunk_strategy 同 form 语义一致，改动面最小 |
| student_name 触发脱敏 | **API 接收并透传** | service.ingest 已有脱敏分支（service.py:82-90），只需保证 API 接进来 |
| 未登录用户能否上传 | **禁止（401）** | 杜绝再发生"成绩单写到 public 污染手册工具"的 regression |
| 管理列表展示 | **三 tab（全部 / 手册 / 我的成绩单）** | 用户最直观的分组方式，UI 体验最好 |
| 旧 public 分区里的脏数据 | **保留** | query_handbook 工具改造后只命中"手册 dataset"语义，避免暴露；后续 ingest_student_handbook.py 重跑会用 `delete_by_dataset` 自动清理 |

## 细节实现

### 1. SQL schema 迁移（MySQL 8.0 兼容）

```sql
-- CREATE TABLE 新增 user_id 列
CREATE TABLE IF NOT EXISTS document_records (
    ...
    user_id VARCHAR(128) NOT NULL DEFAULT 'public',
    INDEX idx_doc_records_user_id (user_id),
    ...
);

-- 兼容已存在的表（PREPARE/EXECUTE 避开 DELIMITER 不识别 + MySQL 8.0 < 8.0.29 不支持 ADD COLUMN IF NOT EXISTS）
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'document_records' AND COLUMN_NAME = 'user_id');
SET @stmt := IF(@col_exists = 0,
    "ALTER TABLE document_records ADD COLUMN user_id VARCHAR(128) NOT NULL DEFAULT 'public' AFTER error_message, ADD INDEX idx_doc_records_user_id (user_id)",
    "DO 0");
PREPARE stmt FROM @stmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
```

`document_chunks.metadata_json` 已存有 user_id 字段（脱敏路径写入的 `structured["user_id"]`），无需再改 schema。

### 2. 后端 API 端点

```python
@router.post("/api/v1/documents/upload")
async def upload_documents(
    files: list[UploadFile] = File(..., max_length=MAX_FILES_PER_REQUEST),
    dataset_name: str = Form(...),
    chunk_strategy: str = Form("auto"),
    user_id: str = Form(...),                 # 2026-08-25：必填
    student_name: str = Form(default=""),       # 可选（仅 user_id != public 时触发脱敏）
):
    user_id = _require_user_id(user_id)         # 兜底 401
    results = await service.ingest_many(files, dataset_name, chunk_strategy,
                                        user_id=user_id, student_name=student_name.strip() or None)
    return {"count": len(results), "datasets": results}


@router.get("/api/v1/documents/datasets")
async def list_datasets(
    user_id: str = Query(..., min_length=1, max_length=128),
    include_public: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
):
    user_id = _require_user_id(user_id)
    if runtime.document_repo is None:
        raise HTTPException(status_code=503, detail="document_repo 未就绪")
    datasets = runtime.document_repo.list_datasets(
        limit=limit, user_id=user_id, include_public=include_public
    )
    return {"count": len(datasets), "datasets": datasets}
```

### 3. DocumentRepository 仓储

```python
def create_dataset(self, *, ..., user_id: str = "public"):
    sql = text("""
        INSERT INTO document_records (
            dataset_id, dataset_name, source_doc_name, storage_path,
            file_type, file_size, chunk_strategy, chunks_count, status, user_id
        ) VALUES (...)
        ON DUPLICATE KEY UPDATE
            ..., user_id = VALUES(user_id)
    """)

def list_datasets(self, *, limit=50, user_id=None, include_public=True):
    if user_id is None:
        # 老语义：列出全部
        sql = "SELECT ... FROM document_records ORDER BY created_at DESC LIMIT :limit"
    elif include_public:
        sql = "SELECT ... FROM document_records WHERE user_id IN ('public', :user_id) ORDER BY ..."
    else:
        sql = "SELECT ... FROM document_records WHERE user_id = :user_id ORDER BY ..."
```

### 4. 前端 UI

DocumentsPage 加：
- `Alert`（未登录警告 + 提示去 /login）
- `useEffect` + `useCallback` 调 `api.documentsList(user.user_id, true)` 加载列表
- `handleUpload` 把 `user.user_id` + `user.name` 传给 API
- `Segmented` 三 tab：全部 / 手册（public）/ 我的成绩单
- `Table` 展示：dataset_name / source_doc_name / file_type / chunks_count / status / 归属（public 蓝标签 / 我的紫标签）
- 上传按钮 `disabled={!user?.user_id}` 防止 anon 上传
- Dragger 内置提示"成绩单用 query_transcript 工具查询；手册用 query_handbook"

## Debug 结论

1. **PowerShell GBK 编码**：所有中文 fixture 字符串在 host console 输出乱码 → 测试断言改用 ASCII marker（如 `[HANDBOOK-MARKER]`）。
2. **DELIMITER 兼容性**：`docker-entrypoint-initdb.d` 用 `mysqld --init-file` 模式执行 SQL，**不识别** mysql 客户端的 `DELIMITER //` 指令 → 改用 `SET @stmt + PREPARE/EXECUTE` 纯 SQL 写法。
3. **FastAPI TestClient + multipart**：直接 `TestClient(router)` 缺少中间件栈 → multipart 上传时报 `fastapi_middleware_astack not found` → 用 `TestClient(agent.app.app)` 替代（继承完整中间件）。
4. **fixture monkeypatch 嵌套**：spy 在 fixture 设置 `ingest_many`，但测试想 spy `ingest` —— spy 需要分别在不同位置设置，否则 spy_injest 会被 spy_ingest_many 拦截。修复：让 fixture 的 `ingest_many` 透传到底层 `ingest`，让 ingest spy 接住。
5. **老 documents_upload 测试回归**：之前几个 batch 测试不传 user_id（依赖 public 默认值），现在 user_id 必填 → 全部回归失败。修复：4 个老测试加 `user_id=public`。

## 测试与验证

### 单测

`python/tests/test_documents_api_user_id.py`（**9 例全过**）：
- `test_upload_without_user_id_returns_422` — FastAPI Form(...) 必填
- `test_upload_with_user_id_passes_to_ingest` — user_id 透传到 service.ingest（不再默认 public）
- `test_upload_with_student_name_triggers_desensitize` — 触发脱敏
- `test_upload_without_student_name_no_desensitize` — student_name 空时不脱敏
- `test_list_datasets_filters_by_user_id_with_public` — 默认含公共手册
- `test_list_datasets_strict_personal_only` — include_public=false 仅本人
- `test_list_datasets_without_user_id_returns_422` — Query 必填
- `test_list_datasets_repo_unavailable_returns_503` — runtime 未就绪
- `test_document_repo_create_dataset_persists_user_id` — repo SQL 层 user_id 落库

`python/tests/test_documents_upload.py`（**7 例全过**）：
- 4 个老测试加 `user_id=public` 修复回归

### 全量回归

```
$ pytest tests/ -m "not slow" -q
=============== 358 passed, 4 deselected, 2 warnings in 37.26s ================
```

之前 349 → 358 = +9（4 个新 + 5 个回归 fix）。

## 兼容性 / 迁移

### 旧 public 分区里的脏数据（query_knowledge 拆分前的"成绩单误写到 public"）

- 不会自动清理（避免误删真实公共手册）
- **告知用户**：本次修复后请重新上传个人成绩单（会写到正确 user_id 分区）
- 后续 `ingest_student_handbook.py` 重跑会用 `delete_by_dataset` 清理旧的"成绩单脏数据"
- `query_handbook` 工具只查 public 分区，但语义是"学生手册"——如果未来发现 public 分区里有非手册内容，可写一次性清理脚本

### 向后兼容

- 旧 clients（不带 user_id 调 upload）→ 422（FastAPI Form 必填拒绝）
- 旧 DocumentRepository.create_dataset 调用（不传 user_id）→ 默认 "public"，向后兼容 OK
- GET /datasets 不带 user_id → 422

## 后续待办

1. **`query_handbook` 工具保护**：当前 query_handbook 检索 user_ids=[public]，如果未来公共分区里有非手册内容（脏数据），会被错误检索到。建议给 `DocumentIngestionService.create_dataset` 加 `dataset_kind` 字段（'handbook' / 'transcript' / 'generic'），query_handbook 仅查 `dataset_kind='handbook'`，query_transcript 仅查 `dataset_kind='transcript'`。
2. **CLI 脚本端到端校验**：`python scripts/ingest_transcript_desensitized.py --user-id 3123003252 --name xxx` 跑一遍，确认 CLI 路径写的 user_id 与 DocumentsPage 路径一致。
3. **eval 集成**：`eval_sets/kb_retrieval.jsonl` 加 user_id 路由场景（personal transcript query 命中个人分区、handbook query 命中 public 分区）。
4. **前端 user.name 拿不到时**：当前默认从 `auth.user.name` 取；如果 auth 接口后续把 name 改为可选，需要让 user 必填。

## 部署踩坑（2026-08-29 实测 + 修复）

### 坑 1：`docker-entrypoint-initdb.d` 只在 volume 首次创建时跑

**症状**：`sql/init-db.sql` 已经把 `user_id` 列写在 `CREATE TABLE` + `PREPARE/EXECUTE` 迁移块里，但**已存在的 `mysql_python_data` volume 不会重新跑这些 SQL**——首次跑过 init-db 后，schema 就被锁定成当时的版本。后续对 init-db.sql 的修改（哪怕是 `ALTER TABLE`），对已存在 volume **完全无效**。

**触发条件**：
- 第一次 `docker compose up -d` 启动 → init-db.sql 跑一次 → schema v1
- 修改 init-db.sql 加 `user_id` 列
- 第二次 `docker compose up -d` → mysql volume 已存在 → init-db.sql **不再执行** → schema 仍是 v1（没 user_id 列）→ 新代码 1054 Unknown column 报错

**正确做法（按优先级）**：
- **A（推荐，下一轮做）**：写 `python/storage/mysql/migrations.py` + 在 `runtime.init()` 末尾调一次。CHECK INFORMATION_SCHEMA.COLUMNS / STATISTICS，存在性检查后幂等 ALTER。
- **B（本次用的）**：手动 `docker exec mysql -e "ALTER TABLE..."` 加列，**但需要每次 schema 改都记得跑一次**。
- **C（不推荐）**：`docker compose down -v` 重建 → 丢所有数据。

**操作记录**：
```bash
docker exec mult-agent-university-system-mysql-1 mysql -uroot -p123456 course_system \
  -e "ALTER TABLE document_records
      ADD COLUMN user_id VARCHAR(128) NOT NULL DEFAULT 'public' AFTER error_message,
      ADD INDEX idx_doc_records_user_id (user_id)"
```
**然后必须重启 python-api** —— SQLAlchemy 不缓存 schema 元数据，但 application 层 service.ingest 调用链可能有依赖 import 时的状态。

### 坑 2：`service.ingest` 调 `document_repo.create_dataset` 时漏传 `user_id` 参数

**症状**：方案 B 跑完 ALTER 后，新上传文件仍然写 `user_id='public'` —— response body `user_id=trace_user` 正确，但 MySQL 里实际存的还是 `public`。

**根因**：`python/agent/documents/service.py:108-124` 调 `self.document_repo.create_dataset(...)` 时**位置参数列表里没传 `user_id`**，函数签名默认值是 `"public"`。Python 用了默认 `public`，**完全无视 api 层传入的 user_id**。

```python
# 错（之前）
await asyncio.to_thread(
    self.document_repo.create_dataset,
    dataset_id=dataset_id,
    dataset_name=dataset_name,
    # 漏了 user_id=user_id  ← 这里漏了
    ...
)
```

**修复**：补上 `user_id=user_id`。

```python
# 对
await asyncio.to_thread(
    self.document_repo.create_dataset,
    dataset_id=dataset_id,
    ...
    user_id=user_id,  # 2026-08-29 修复：之前漏传 → 默认 "public"，个人成绩单误写到 public 分区
)
```

**教训**：所有 `DocumentRepository.create_dataset(...)` 调用方必须显式传 `user_id` —— 写单测断言 SQL 里有 `:user_id` 绑定（`test_document_repo_create_dataset_persists_user_id` 已有这条断言，**测试是从 repo 角度检查 SQL 文案，但缺一个"上游 service 不漏传"的集成测试**）。后续建议加 `test_ingest_passes_user_id_to_create_dataset` 走 service 真实路径。

### 验证（修复后）

```bash
$ curl -X POST -F "files=@a.csv" -F "dataset_name=after_fix_test" \
       -F "chunk_strategy=auto" -F "user_id=after_fix_user" \
       http://127.0.0.1:8000/api/v1/documents/upload
# response: { "user_id": "after_fix_user", ... }

$ mysql -e "SELECT dataset_id, dataset_name, user_id FROM document_records WHERE dataset_name='after_fix_test'"
# dataset_id                       | dataset_name    | user_id
# 90c4017b134e4616ba17c3e423519fd3 | after_fix_test  | after_fix_user  ✓
```

### pytest 回归

- 新增 `test_documents_api_user_id.py` 9 例（user_id 路由 / 脱敏 / 列表过滤 / 422 / 503 / repo SQL 落库）
- 修复 `test_documents_upload.py` 老测试 4 例（加 `user_id=public`）
- 全量 `pytest tests/ -m "not slow"` → **358 passed, 4 deselected**（无回归）
