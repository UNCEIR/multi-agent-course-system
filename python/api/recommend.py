"""推荐路由 — 统一流式入口 POST /api/v1/recommend/stream。

默认走 ReAct 流式，流式中失败自动兜底 Pipeline 流式（experiment_group=pipeline_fallback）。
所有前端推荐一律走本端点，满足 AGENTS.md 前端 API 流式契约。
"""

from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from agent import runtime
from models.schemas import RecommendationRequest

router = APIRouter()


@router.post("/api/v1/recommend/stream")
async def recommend_stream(request: RecommendationRequest):
    """SSE 流式公选课推荐（默认 ReAct → 兜底 Pipeline）。

    事件：phase / course_start / text / course_end / done / error。
    前端消费本流实现打字机效果 + 阶段进度。
    """
    return StreamingResponse(
        _sse_wrapper(runtime.supervisor.stream_recommend_unified(request)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _sse_wrapper(generator):
    async for event in generator:
        if event["event"] == "done":
            agent_results = event.get("data", {}).get("agent_results", {})
            for name, result in agent_results.items():
                runtime.metrics_collector.record_agent_call(
                    agent_name=name,
                    success=result.get("success", False),
                    latency_ms=result.get("latency_ms", 0),
                )
        elif event["event"] == "error":
            runtime.metrics_collector.record_business_event(
                "recommend_stream_error",
                code=event.get("data", {}).get("code", ""),
                phase=event.get("data", {}).get("phase", ""),
            )
        payload = json.dumps(event["data"], ensure_ascii=False)
        yield f"event: {event['event']}\ndata: {payload}\n\n"
