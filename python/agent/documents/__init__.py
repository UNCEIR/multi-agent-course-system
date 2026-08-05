"""
v2 文档摄入流水线（Documents）预留包 — Phase 1 实现

当前状态：空包（骨架预留）。

Phase 1 目标：
  实现文档上传/分切/解析流水线，对应 /api/v1/documents/upload 端点。核心功能：

  1. 上传：multipart/form-data，支持 CSV / PDF / doc 格式
  2. 分切：复用 v1 的 4 块策略（basic / schedule_capacity / learning_profile / audience_tags）
     或 FastGPT KB 自定义分割策略
  3. 存储：
     - 源文档存 MinIO（源文档桶）
     - 结构化元数据存 MySQL
     - 向量存 Milvus
  4. 兜底：FastGPT KB 不可用时，走 Python 脚本解析（CSV/PDF/doc）

  架构：
  - FastGPT KB 二次开发（主）：upload/split/embed/retrieve + 管理 UI
  - Python 兜底脚本（备）：CSV 用 pandas，PDF 用 PyMuPDF，doc 用 python-docx
  - HTTP admin API 调用 FastGPT KB（非 MCP，MCP 只暴露 app 不暴露 KB 管理操作）

  双角色 MinIO 桶：
  - source-documents：源文档（课程 CSV、学生手册 PDF、成绩单 Excel 等）
  - report-artifacts：报告产物（PDF 报告、中间 JSON）

参考文档：
  - docs/v2.0.0/notes/2026-07-27-设计决策问答记录.md 决策 6
  - docs/v2.0.0/notes/2026-07-28-设计决策补充说明.md 决策 6 补充
"""