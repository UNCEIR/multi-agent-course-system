"""v2 评价寄语路由（Phase 2 实装）。

- POST /api/v1/evaluation  教师端生成（SSE：stage/radar/comment_token/done/error）→ 落库
- GET  /api/v1/evaluation/me  学生端读取本人评价（显式 user_id，遵循 /recommend/stream 先例）
"""

from __future__ import annotations

import asyncio
import json
import structlog
from fastapi import APIRouter, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from agent.evaluation.service import stream_evaluation
from tools.evaluation.generate_comment import COMMENT_TYPES

logger = structlog.get_logger()
router = APIRouter()


class EvaluationRequest(BaseModel):
    target_user_id: str = Field(..., min_length=1, max_length=64, description="目标学生 user_id")
    comment_type: str = Field(..., description=f"评语类型：{' / '.join(COMMENT_TYPES)}")
    generated_by: str = Field(default="", max_length=64, description="教师 user_id（临时口径）")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/api/v1/evaluation")
async def evaluation(req: EvaluationRequest):
    """教师端为学生生成学业评价（雷达图数据 + 评语），SSE 流式。"""
    if req.comment_type not in COMMENT_TYPES:
        return Response(
            status_code=422,
            content=json.dumps({"code": "INVALID_COMMENT_TYPE", "message": f"合法类型：{'/'.join(COMMENT_TYPES)}"}, ensure_ascii=False),
        )

    async def _generate():
        q: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(
            stream_evaluation(
                target_user_id=req.target_user_id,
                comment_type=req.comment_type,
                generated_by=req.generated_by,
                out_queue=q,
            )
        )
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


@router.get("/api/v1/evaluation/me")
async def evaluation_me(user_id: str = Query(..., min_length=1, max_length=64)):
    """学生端读取本人评价历史（append 保留，最新在前；无数据返回空列表）。"""
    from agent import runtime

    try:
        items = await asyncio.to_thread(runtime.evaluation_repo.list_by_user, user_id, 20)
    except Exception as exc:  # noqa: BLE001
        logger.warning("evaluation me failed", user_id=user_id, error=str(exc))
        items = []
    return {"user_id": user_id, "items": items}
