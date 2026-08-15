"""v2 成绩单报告路由（Phase 2 实装）。

- POST /api/v1/report    multipart files + semester + user_message → SSE
  事件：text / tool / progress / student_done / student_error / done / error
- GET  /api/v1/report/download?file_key&token&expires_at → 文件流 / 结构化错误
"""

from __future__ import annotations

import asyncio
import json
import structlog
from fastapi import APIRouter, Query, UploadFile
from fastapi.responses import Response, StreamingResponse

from agent.report.service import stream_report, verify_download_token
from config import get_settings

logger = structlog.get_logger()
router = APIRouter()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/api/v1/report")
async def report(
    files: list[UploadFile] | None = None,
    semester: str = "",
    user_message: str = "",
):
    """批量生成学生成绩单（SSE 流式；每学生独有下载链接）。"""
    settings = get_settings()
    files = files or []
    if not files:
        return Response(status_code=400, content=json.dumps({"code": "NO_FILES", "message": "未收到文件"}, ensure_ascii=False))
    if len(files) > settings.report_max_files:
        return Response(
            status_code=400,
            content=json.dumps({"code": "TOO_MANY_FILES", "message": f"最多 {settings.report_max_files} 个文件"}, ensure_ascii=False),
        )
    for f in files:
        if f.size and f.size > settings.report_max_file_mb * 1024 * 1024:
            return Response(
                status_code=400,
                content=json.dumps({"code": "FILE_TOO_LARGE", "message": f"{f.filename} 超过 {settings.report_max_file_mb}MB"}, ensure_ascii=False),
            )

    async def _generate():
        q: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(stream_report(files, semester=semester, user_message=user_message, out_queue=q))
        try:
            while True:
                try:
                    event, data = await asyncio.wait_for(q.get(), timeout=0.5)
                    yield _sse(event, data)
                    if event in ("done", "error"):
                        break
                except asyncio.TimeoutError:
                    if task.done():
                        break
        finally:
            if not task.done():
                task.cancel()
            try:
                await asyncio.wait_for(task, timeout=2)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):  # noqa: BLE001
                pass

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/v1/report/download")
async def download(
    file_key: str = Query(...),
    token: str = Query(...),
    expires_at: int = Query(0),
):
    """token 校验 → 文件流；三类结构化错误：invalid_token / token_expired / artifact_not_found。"""
    err = verify_download_token(file_key, token, expires_at)
    if err:
        return Response(
            status_code=403 if err == "invalid_token" else 410,
            content=json.dumps({"code": err, "retry_hint": "报告链接可能已过期，请重新生成"}, ensure_ascii=False),
            media_type="application/json",
        )
    from agent import runtime

    data = runtime.minio_repo.download(file_key)
    if data is None:
        return Response(
            status_code=404,
            content=json.dumps({"code": "artifact_not_found", "retry_hint": "文件不存在，请重新生成"}, ensure_ascii=False),
            media_type="application/json",
        )
    content_type = "application/pdf" if file_key.endswith(".pdf") else "text/html; charset=utf-8"
    return Response(content=data, media_type=content_type, headers={"Content-Disposition": f'attachment; filename="{file_key.split("/")[-1]}"'})
