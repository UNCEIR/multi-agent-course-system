---
name: document-ingestion
description: 上传文档到知识库（CSV/PDF/doc），自动完成解析→分块→向量化→元数据入库。当用户需要上传文档、导入数据、建立知识库时使用。
allowed_tools: [parse_document, chunk_document]
---

## 文档摄入流程

### 1. 识别触发场景

用户请求中出现以下情况时调用本技能：

- 上传：上传文档、导入文件、添加资料
- 入库：把 XX 加入知识库、保存这份材料
- 格式：CSV / PDF / doc 文档

### 2. 执行步骤

1. **接收文件**：确认用户提供的文件路径和格式（CSV/PDF/doc）
2. **调 `/api/v1/documents/upload` 端点**（HTTP POST，multipart/form-data）：
   - `file`：源文档
   - `dataset_name`：数据集名称（如 "course_data"、"student_handbook"）
   - `chunk_strategy`：`auto`（按文件类型自动选）/ `course_four_block` / `generic_fixed`
   > 注：`/api/v1/documents/upload` 是 HTTP 端点，非 ToolRegistry 注册的 tool。`read_file`/`write_file` 是 deepagents FilesystemMiddleware 内置工具，不在此 allowlist 中。
3. **后端流水线自动执行**：
   - 源文档存 MinIO `source-documents` 桶
   - Python 解析（CSV→pandas，PDF→pypdf，doc→python-docx）
   - 分块（`course_four_block` 或 `generic_fixed`：512 字符 + 50 overlap）
   - 向量化（embedding）→ 入 Milvus `document_chunks` collection
   - 元数据入 MySQL `document_records`/`document_chunks` 表
   - FastGPT KB 摄入（Phase 3 真实链路，Phase 1 mock）
4. **向用户呈现结果**：
   - 返回 `dataset_id` / `chunks_count` / `status`
   - 说明文档已入库，可用于后续检索

### 3. 注意事项

- **只支持 CSV/PDF/doc 三种格式**：其他格式提示用户转换
- **大文件**（>10MB）：提示用户分批上传
- **失败兜底**：FastGPT KB 不可用时走 Python 解析兜底链路，不影响入库
- **证据可追踪**：每个 chunk 记录来源页码，可回链到源文档