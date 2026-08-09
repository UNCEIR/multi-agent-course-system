# Phase 1 功能验证补充

## 背景与范围

- 本轮目标是完善 Phase 1 的可执行验证闭环，而不是为旧测试恢复旧架构。
- 当前阶段明确排除 FastGPT、MCP、真实外部 KB，以及 MySQL/Milvus 文档持久化。

## 已实现

- `parse_document` 支持 CSV、PDF、DOCX、TXT、MD 的 Python 本地解析。
- `chunk_document` 支持段落分块和固定字符窗口分块，固定窗口支持 overlap。
- `DocumentIngestionService` 保存源文件并完成解析、分块；`POST /api/v1/documents/upload` 已注册。
- `recommend_courses` tool 委托现有 v1 `SupervisorOrchestrator`，不重复实现推荐逻辑。
- `ToolRegistry.call()` 使用每个工具独立的 CircuitBreaker。

## 验证结果

- `python -m compileall -q agent api tools tests/test_documents_upload.py`：通过。
- `python -m pytest tests/ -m "not slow" -q`：`95 passed, 4 deselected`。
- 新增验证覆盖：本地 CSV 上传、真实 multipart API、分块 overlap、推荐 tool 委托、统一 Agent 工厂和异步 SQLite checkpointer。

## 未完成项

- 文档元数据写入 MySQL、向量写入 Milvus、MinIO 对象存储仍未接入当前本地闭环。
- 报告、评价寄语、PPT 业务逻辑仍由统一 Agent 工厂提供场景入口，尚未进入对应 Phase 的业务实现。
- FastGPT/MCP 保留为后续阶段，不作为本阶段失败项。
