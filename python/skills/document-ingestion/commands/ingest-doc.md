# Command: ingest-doc（上传与摄入）

## Steps
1. 确认文件路径与格式（CSV/PDF/doc）。
2. 调 `/api/v1/documents/upload`（multipart：`file` + `dataset_name` + `chunk_strategy=auto`）。
3. 摄入管线自动执行：存源 → 解析 → 分块 → 脱敏（个人文档）→ 向量化 → 元数据入库。
4. 返回 `dataset_id / chunks_count / status`。
