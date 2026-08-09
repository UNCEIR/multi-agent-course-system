"""本地文档摄入路由。"""

from fastapi import APIRouter, File, Form, UploadFile

from agent.documents.service import DocumentIngestionService

router = APIRouter()
service = DocumentIngestionService()


@router.post("/api/v1/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    dataset_name: str = Form(...),
    chunk_strategy: str = Form("auto"),
):
    """保存文件并执行本地解析、分块闭环。"""
    result = await service.ingest(file, dataset_name, chunk_strategy)
    return {
        "dataset_id": result["dataset_id"],
        "chunks_count": result["chunks_count"],
        "status": result["status"],
    }
