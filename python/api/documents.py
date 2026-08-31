"""本地文档摄入路由（单/批量，最多 5 份/请求）+ 列表查询。

2026-08-25 修复：
- user_id 路由：成绩单 / 个人文档写入 user_id=<当前用户> 分区（query_transcript 可查）；
  手册类工具路径保留 user_id='public' 兼容
- GET /datasets：DocumentsPage 上传后能展示已上传列表（按 user_id 过滤个人 + public）
- student_name 触发脱敏（仅 user_id != 'public' 时）
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from agent.documents.service import DocumentIngestionService

router = APIRouter()
service = DocumentIngestionService()

# 单次请求最大文件数；与 batch upload 设计对齐
MAX_FILES_PER_REQUEST = 5


def _require_user_id(user_id: str) -> str:
    """anon 不允许上传（避免再发生"成绩单写到 public 污染手册工具"的事故）。"""
    if not user_id or not user_id.strip():
        raise HTTPException(
            status_code=401,
            detail="上传文档需要先登录（user_id 必填）",
        )
    return user_id.strip()


@router.post("/api/v1/documents/upload")
async def upload_documents(
    files: list[UploadFile] = File(..., max_length=MAX_FILES_PER_REQUEST),
    dataset_name: str = Form(...),
    chunk_strategy: str = Form("auto"),
    user_id: str = Form(...),                 # 2026-08-25：必填
    student_name: str = Form(default=""),       # 2026-08-25：可选，仅 user_id != public 时用于脱敏
):
    """保存 1~5 份文件并执行本地解析、分块、向量入库闭环。

    路由规则（修复 query_knowledge 拆分后的分区语义）：
    - user_id='public'（前端固定传或显式选）：写入 public 分区 → query_handbook 可查
    - user_id=<当前用户>：写入本人分区 → query_transcript 可查
    - student_name 非空 + user_id != public：触发脱敏（姓名/学号/班级→占位符）

    返回结构：
      {count, datasets: [
          {dataset_id, chunks_count, status, filename, user_id, ...}  // success
       或 {dataset_id: null, status: "error", error, message?, filename, ...}  // 单文件失败
      ]}
    """
    user_id = _require_user_id(user_id)

    results = await service.ingest_many(
        files,
        dataset_name,
        chunk_strategy,
        user_id=user_id,
        student_name=student_name.strip() or None,
    )
    return {
        "count": len(results),
        "datasets": results,
    }


@router.get("/api/v1/documents/datasets")
async def list_datasets(
    user_id: str = Query(..., min_length=1, max_length=128),
    include_public: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
):
    """DocumentsPage 上传后展示已上传列表。

    默认 include_public=True：返回 user_id + public 分区所有 dataset（手册+个人）
    include_public=False：仅返回当前 user_id 的个人 dataset
    """
    user_id = _require_user_id(user_id)

    # lazy 取 runtime 的 document_repo（lifespan 后才有）
    from agent import runtime

    if runtime.document_repo is None:
        raise HTTPException(status_code=503, detail="document_repo 未就绪")
    datasets = runtime.document_repo.list_datasets(
        limit=limit,
        user_id=user_id,
        include_public=include_public,
    )
    return {"count": len(datasets), "datasets": datasets}
