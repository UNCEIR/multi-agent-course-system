# Documents 批量上传（单/批统一，最多 5 份/请求）

## 背景与问题

- **症状**：`/documents`（DocumentsPage）原本 `Upload.Dragger` 设了 `maxCount={1}` + state 是单文件 `file: UploadFile | null`；前端提示"单个"。当用户在文件选择器或拖拽时一次选多个，antd truncate 到第 1 份，配合 `beforeUpload` 的边界态，按钮 `handleUpload` 看到 `file?.originFileObj` 为空就弹"请先选择文件"，但用户拖拽的多个文件已经被 antd 内部吞掉，体验很糟糕。
- **诉求**：支持单/批量（最多 5 份/请求）上传；批量失败时其他文件继续。
- **影响范围**：
  - 后端：`python/agent/documents/service.py`（加 `ingest_many` 薄包装）+ `python/api/documents.py`（route 切到 `files: list[UploadFile] = File(..., max_length=5)`）
  - 前端 types：`frontend/src/types/index.ts`（DocumentsUploadResult → `{count, datasets[]}`）
  - 前端 API client：`frontend/src/lib/api.ts`（`documentsUpload(files: File[], ...)`）
  - 前端 UI：`frontend/src/app/(main)/documents/page.tsx`（Dragger 改 `multiple + maxCount=5`、state 改数组、单/多结果切换卡片/表格）

## 总体架构方案

- **接口协议变更**（breaking，但仓库内部唯一调用方）
  - 旧：`file: UploadFile = File(...)` → `{dataset_id, chunks_count, status}`（单文件）
  - 新：`files: list[UploadFile] = File(..., max_length=5)` → `{count, datasets: Array<DatasetSummary>}`（每文件一份独立 dataset）
  - 颗粒度 **A（推荐）**：每文件一份独立 dataset_id，与 `DocumentIngestionService.ingest` 现有"`ingest` 每文件一份 dataset"语义 1:1 对齐，零侵入；前端可单独追溯每份文件结果
- **失败语义**：单文件失败（解析异常 / 不可读 / 内容损坏）→ `service.ingest_many` 在 except 分支 yield `{status: "error", error, message, dataset_id: null, ...}`；其它文件继续；HTTP 仍 200 OK，错误在 `datasets[]` 里收敛而非整批失败
- **大小上限**：前端 `beforeUpload` 单文件 >10MB → `Upload.LIST_IGNORE` 拦截；后端 `service.ingest_many.max_file_bytes=10MB` 二道防线（防止直 curl 绕过 UI）；真触发的返回 `{status: "error", error: "file_too_large", max_file_bytes}`
- **文件名冲突**：dataset_dir 用 uuid 作为子目录，跟单文件语义对齐。同一批次内有同名文件 → 自动加 `-1`/`-2` 后缀（如 `notes.csv` / `notes-1.csv`）避免 dataset_dir 内 source_path 冲突

## 细节实现

- `agent/documents/service.py`
  - 加 `import structlog` + `logger = structlog.get_logger()`
  - 现有 `ingest(file)` 逻辑**完全不动**——> 复用为最小侵入
  - 新增 `ingest_many(files: list[UploadFile], dataset_name, chunk_strategy="auto", user_id="public", student_name=None, max_file_bytes=10*1024*1024) -> list[dict]`：
    - 空列表 → 返回 `[]`；dataset_name 空 → 抛 `ValueError`
    - 文件大小校验（读 `UploadFile.file` spool 的 tell/seek）→ 超限不入库、记 `{status: "error", error: "file_too_large"}`
    - 同名文件计数 `seen_counts: dict[str, int]` → `-1/-2` 后缀
    - 每文件 try/except 包住 `ingest(...)` 调用 → 失败时 `logger.warning` + yield 失败 summary
    - 成功结果补 `filename` 字段（方便前端表格展示）
- `api/documents.py`
  - `MAX_FILES_PER_REQUEST = 5` 常量
  - route 签名：`files: list[UploadFile] = File(..., max_length=MAX_FILES_PER_REQUEST)`、`dataset_name: str = Form(...)`、`chunk_strategy: str = Form("auto")`
  - 实现：直接 `await service.ingest_many(...)` → 返回 `{count, datasets: results}`
  - 注释明确：旧 `file` 单参形式**已删除**（无外部 API 调用方）
- `frontend/src/types/index.ts`
  - 拆 `DocumentsUploadResult` → `{count, datasets: DocumentUploadDataset[]}`
  - `DocumentUploadDataset` 含 `dataset_id: string | null`、`filename?`、`file_size?`、`chunks_count`、`status: 'ok' | 'completed' | 'error'`、`error? / message? / max_file_bytes?`
- `frontend/src/lib/api.ts`
  - `documentsUpload(files: File[], datasetName, chunkStrategy, signal?)`
  - 客户端先做 `files.length === 0 / > 5` 双重校验
  - `form.append('files', f)` 多次 append（**关键**：FastAPI 才能解析成 `list[UploadFile]`，add 数组形式不行）
- `frontend/src/app/(main)/documents/page.tsx`
  - `MAX_FILES = 5` + `MAX_FILE_BYTES = 10 * 1024 * 1024` 常量
  - state 改 `files: UploadFile[] = []`
  - `Upload.Dragger` 改 `multiple` + `maxCount={MAX_FILES}` + `fileList={files}` + `onChange={({fileList}) => setFiles(fileList.slice(0, MAX_FILES))}` + `onRemove={(r) => setFiles(prev => prev.filter(f => f.uid !== r.uid))}`
  - `beforeUpload` 单文件 >10MB → `Upload.LIST_IGNORE` + `message.error` 提示
  - `handleUpload` 校验文件数 + dataset_name，调 `api.documentsUpload(ready, ...)`
  - 结果展示按 `count` 分两路：
    - **1 个**：复用原 Descriptions 单卡片（避免改原有用例视觉）
    - **>1 个**：`Table` 4 列（filename / dataset_id / chunks / status + error message）
  - toast 按 `okCount / failCount` 分两种文案
  - 上传按钮 `disabled={files.length === 0}` 防止空提交

## Debug 结论（实施过程中踩到的坑）

1. **`Upload.LIST_IGNORE` 必须放在 `beforeUpload` 返回**——不要 return false 又忽略，否则 antd 会 trigger `onChange` 把文件加入 fileList 后又删掉，stale state。
2. **`form.append('files', f)` vs `form.append('files', [f1, f2])`**：FastAPI 0.95+ 对 list[UploadFile] 必须是**多次同名 append**，不能传数组（数组会被序列化成 JSON，不是 multipart）。这条踩过坑。
3. **`--no-cache` build 的边界**：python-api 容器镜像用 `COPY . .` 拷源码，改完 service.py 必须 `--build` 重建——但**前端容器 COPY src 也是 build 时固化**，HMR 不能覆盖 page.tsx 已 import 的常量（MAX_FILES 等）。要 `--no-cache` rebuild 或在 Turbopack HMR 起效前等几秒（一般 dev 模式能热替换，非 dev 模式要 full rebuild）。
4. **pytest 单测 `__bad__` 文件名假故障触发不了**：因为 `Path("__bad__").name == "__bad__"` 仍合法。改用 monkeypatch 替换 `DocumentIngestionService.ingest` 在文件名含 "bad" 时抛 RuntimeError → 精准触发 `ingest_many` except 分支。

## 测试与验证

- 端到端单测 `python/tests/test_documents_upload.py`（共 6 例）：
  - `test_document_ingestion_service_csv`（旧，覆盖原有 per-file 行为）
  - `test_documents_router_registered`（旧）
  - `test_documents_upload_endpoint`（旧，**已升级用 `files` key 而非 `file`**，断言 `count=1` + `datasets[0].status=ok`）
  - `test_documents_upload_batch_5_files`（新，5 个 CSV → count=5、dataset_id 互不相同）
  - `test_documents_upload_batch_exceeds_5_files`（新，6 个 → FastAPI 422）
  - `test_documents_upload_batch_one_bad_file_others_succeed`（新，monkeypatch 让 bad_file 触发 RuntimeError → 其它 2 个仍 ok）
- `python -m pytest tests/test_documents_upload.py -v` → **6 passed**
- `python -m pytest tests/ -m "not slow"` → **340 passed, 4 deselected**（无回归）
- 浏览器实测（chrome MCP /docsuments + fetch）：
  - 单文件 → `{count:1, datasets:[{...status:"ok"}]}`
  - 批量 3 文件 → `{count:3, datasets:[{dataset_id:..., filename:"a.csv"...}, {b.csv...}, {c.csv...}]}`，每个 `dataset_id` 互不相同
  - 6 个文件 → FastAPI 422 `List should have at most 5 items after validation, not 6`
- 容器构建：`docker compose -f docker-compose.yml -f docker-compose.pull-mirror.yml --profile frontend up -d --build`

## 兼容性 / 迁移

- **后端 breaking**：`file` 单参形式已删除。仓库内只有 `documents/page.tsx` 一个调用方，已同步升级。**外部 API 客户端**（如直接 curl 脚本）需改为 `-F 'files=@...'`，旧 `-F 'file=@...'` 会收 422。
- **前端 type**：旧测试 / store / 其它页面如有 import `DocumentsUploadResult` 需同步重构（仓库 grep 仅 `api.ts` 1 处使用，已改）。
- **`DocumentsUploadResult.datasets[i].dataset_id`** 现在可能为 `null`（失败），前端 UI 渲染时务必判空（已加 `<Tag>{v ?? '—'}</Tag>`）。

## 后续待办

- 文件大小上限现在**前端 + 后端双重校验**（与 Phase 2 settings.py 加 `DOCUMENTS_MAX_FILE_MB` 常量正交）——后续如果要全局可配置，应该让 settings 注入到 service.max_file_bytes 参数，文档同步更新
- 批量失败报告现在用 antd Tag + Table 错误列，**失败文件本身的错误堆栈**没展示给前端（message 简略）。下一步可考虑把 `documents_upload.results[].message` 加上 tooltip 展开更详细的 stack（生产环境慎用）
- 测试覆盖：当前 `frontend` 单测不覆盖这个页面（只有 vitest infra）；考虑加 `frontend/tests/pages/documents-page.spec.tsx` 验证 Dragger + 按钮 disabled + Table 渲染
