"""v2 成绩单报告路由（Phase 2 实装）。

- POST /api/v1/report    multipart files + semester + user_message → SSE
  事件：text / tool / progress / student_done / student_error / done / error
- GET  /api/v1/report/download?file_key&token&expires_at → 文件流 / 结构化错误

事件协议（路 2 升级）：
- 每条事件携带 `id:` 字段（按 batch_id 单调递增）
- 客户端可通过 `Last-Event-ID` HTTP header 续传
"""

from __future__ import annotations

import asyncio
import json
import structlog
from agent import runtime
import uuid
from fastapi import APIRouter, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

from agent.report.service import make_download_url, stream_report, verify_download_token
from config import get_settings
from services.sse_event_buffer import EventBuffer, parse_last_event_id, sse_with_id

logger = structlog.get_logger()
router = APIRouter()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/api/v1/report")
async def report(
    raw: Request,
    files: list[UploadFile] | None = None,
    semester: str = Form(""),
    user_message: str = Form(""),
    user_id: str = Form(""),
    class_name: str = Form(""),  # 前端手动选择班级（覆盖 Excel 里的班级，解决「班级：」为空）
):
    """批量生成学生成绩单（SSE 流式；每学生独有下载链接）。

    支持 Last-Event-ID 续传：header 传最后事件 id → 服务端先回放缓存再继续生成。
    buffer key 用 batch_id（首次请求无 → 随机生成，后续重连沿用）。
    """
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

    last_event_id = parse_last_event_id(raw.headers.get("Last-Event-ID"))
    # buffer key 优先用 Last-Event-ID 对应的 thread_id（续传场景）；否则新建
    thread_key = raw.headers.get("X-SSE-Thread-Key") or f"report:{uuid.uuid4().hex[:16]}"
    buf = EventBuffer(thread_id=thread_key)

    async def _generate():
        # 续传
        for buffered in await buf.replay_from(last_event_id):
            yield sse_with_id(buffered.event, buffered.payload, buffered.event_id)
        # 正常生成
        q: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(stream_report(files, semester=semester, user_message=user_message, user_id=user_id, class_name=class_name, out_queue=q))
        try:
            while True:
                try:
                    event, data = await asyncio.wait_for(q.get(), timeout=0.5)
                    payload = json.dumps(data, ensure_ascii=False)
                    event_id = await buf.append(event, payload)
                    yield sse_with_id(event, payload, event_id)
                    if event in ("done", "error"):
                        _metrics = getattr(runtime, "metrics_collector", None)
                        if _metrics is not None:
                            _metrics.record_agent_call("report_agent", event == "done", 0.0, "" if event == "done" else str(data)[:120])
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
            "X-SSE-Thread-Key": thread_key,
        },
    )


@router.get("/api/v1/report/batches")
async def list_batches(
    user_id: str = Query(..., min_length=1, max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
):
    """ReportPage「已生成批次」列表（输入侧上传记录，与知识库 /documents/datasets 对齐）。

    返回当前 user 的上传批次（processing/done/error + 文件清单 + 成功/失败份数），
    便于前端展示历史与审计；数据源 report_uploads 表（与 document_records 分表）。
    """
    user_id = user_id.strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="查看报告记录需要登录（user_id 必填）")
    from agent import runtime

    if runtime.report_upload_repo is None:
        raise HTTPException(status_code=503, detail="report_upload_repo 未就绪")
    batches = runtime.report_upload_repo.list_by_user(user_id=user_id, limit=limit)
    return {"count": len(batches), "batches": batches}


@router.get("/api/v1/report/batches/{batch_id}")
async def batch_detail(batch_id: str, user_id: str = Query(..., min_length=1, max_length=128)):
    """按批次查生成详情：上传记录（report_uploads）+ 逐学生产物（report_artifacts）。

    batch_id 兼容两种：上传批次 rb_xxx（经 merged_batch_id 反查产物）或工具合并批次 b_xxx。
    归属校验：上传记录存在时校验 user_id 一致（临时口径，与业务接口一致）。
    """
    from agent import runtime

    if runtime.report_upload_repo is None or runtime.report_artifact_repo is None:
        raise HTTPException(status_code=503, detail="report 仓储未就绪")
    upload = runtime.report_upload_repo.get_by_batch(batch_id)
    if upload is not None:
        owner = upload.get("user_id") or ""
        if owner and user_id and owner != user_id:
            raise HTTPException(status_code=403, detail="无权查看该批次")
        resolved = upload.get("merged_batch_id") or batch_id
    else:
        resolved = batch_id
    artifacts = runtime.report_artifact_repo.list_by_batch(resolved)
    for a in artifacts:
        if a.get("status") == "ok" and a.get("file_key"):
            a["url"] = make_download_url(a["file_key"])
    return {"batch_id": resolved, "batch": upload, "students": artifacts}


@router.get("/api/v1/report/download")
async def download(
    file_key: str = Query(...),
    token: str = Query(...),
    expires_at: int = Query(0),
    inline: bool = Query(default=False, description="true=浏览器内联预览（Content-Disposition: inline）；缺省=下载"),
):
    """token 校验 → 文件流；三类结构化错误：invalid_token / token_expired / artifact_not_found。

    inline=true 时 Content-Disposition 为 inline，浏览器新标签页直接渲染 PDF（前端「查看」）；
    缺省为 attachment（前端「下载」）。
    """
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
    disposition = "inline" if inline else "attachment"
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'{disposition}; filename="{file_key.split("/")[-1]}"'},
    )
