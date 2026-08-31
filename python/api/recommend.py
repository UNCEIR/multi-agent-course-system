"""推荐路由 — 统一流式入口 POST /api/v1/recommend/stream。

默认走并行 Pipeline（mode="pipeline"）；mode="react" 走 ReAct 流式，失败自动兜底
Pipeline（experiment_group=react_fallback/pipeline_fallback）。所有前端推荐一律走
本端点，满足 AGENTS.md 前端 API 流式契约。

事件协议（路 2 升级）：
- 每条事件携带 `id:` 字段（按 thread_id 单调递增）
- 客户端可通过 `Last-Event-ID` HTTP header 续传
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from agent import runtime
from models.schemas import RecommendationRequest
from services.sse_event_buffer import EventBuffer, parse_last_event_id, sse_with_id

router = APIRouter()


@router.post("/api/v1/recommend/stream")
async def recommend_stream(request: RecommendationRequest, raw: Request):
    """SSE 流式公选课推荐（mode="pipeline" 默认，mode="react" 可选 ReAct）。

    事件：phase / course_start / text / course_end / done / error。
    前端消费本流实现打字机效果 + 阶段进度。
    支持 Last-Event-ID 续传：客户端在 Last-Event-ID header 传最后收到的事件 id，
    服务端会先回放缓存中 id 更大的事件，再继续生成。
    """
    buf = EventBuffer(thread_id=_thread_id(request))
    last_event_id = parse_last_event_id(raw.headers.get("Last-Event-ID"))
    return StreamingResponse(
        _sse_wrapper(
            runtime.supervisor.stream_recommend_unified(request, mode=request.mode),
            buf,
            last_event_id=last_event_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _thread_id(request: RecommendationRequest) -> str:
    """以 user_id + prompt 哈希作为 buffer key（同一查询复用缓存）。"""
    import hashlib

    h = hashlib.sha1(f"{request.user_id}|{request.prompt}".encode("utf-8")).hexdigest()[:16]
    return f"recommend:{h}"


async def _sse_wrapper(generator, buf: EventBuffer, *, last_event_id: int | None):
    # 1) 续传：先把 last_event_id 之后的事件回放给客户端
    for buffered in await buf.replay_from(last_event_id):
        yield sse_with_id(buffered.event, buffered.payload, buffered.event_id)
    # 2) 继续生成新事件
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
        event_id = await buf.append(event["event"], payload)
        yield sse_with_id(event["event"], payload, event_id)
