"""v2 文档摄入路由 — Phase 1 实现

当前状态：路由骨架预留。

Phase 1 实现目标：
  POST /api/v1/documents/upload
    请求：multipart/form-data
      file: UploadFile          — CSV / PDF / doc 格式
      dataset_name: str         — 数据集名称（如 "course_data", "student_handbook"）
      chunk_strategy: str       — 分块策略（可选，默认复用 v1 4 块策略）
    响应：JSON
      {dataset_id: str, chunks_count: int, status: str}

  实现参考：
    router = APIRouter()

    @router.post("/api/v1/documents/upload")
    async def upload_document(
        file: UploadFile,
        dataset_name: str,
        chunk_strategy: str = "default",
    ):
        # 1. 存源文档到 MinIO（source-documents 桶）
        # 2. 调用 FastGPT KB HTTP admin API 摄入
        # 3. 兜底：Python 解析（CSV→pandas, PDF→PyMuPDF, doc→python-docx）
        ...

架构决策：
  - FastGPT KB 二次开发为主，Python 兜底脚本为备
  - 源文档存 MinIO 源文档桶，不直接存 MySQL
  - 此文件只做路由注册 + 参数校验 + 文件接收
  - 业务逻辑在 app/documents/ 下实现
"""
from fastapi import APIRouter

router = APIRouter()