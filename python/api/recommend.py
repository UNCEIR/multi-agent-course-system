"""推荐路由 — /api/v1/recommend* 端点。"""

from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from agent import runtime
from models.schemas import RecommendationRequest, RecommendationResponse

router = APIRouter()


@router.post("/api/v1/recommend", response_model=RecommendationResponse)
async def recommend(request: RecommendationRequest):
    """使用 Supervisor 编排器进行公选课推荐 (生产推荐用法)"""
    response = await runtime.supervisor.recommend(request)
    _collect_metrics(response)
    return response


def _recommend_stream_response(request: RecommendationRequest) -> StreamingResponse:
    return StreamingResponse(
        _sse_wrapper(runtime.supervisor.stream_recommend(request)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/v1/recommend/stream")
async def recommend_stream(request: RecommendationRequest):
    """SSE 流式公选课推荐 (前端打字效果 + 阶段进度推送)"""
    return _recommend_stream_response(request)


@router.post("/api/v1/recommend/react")
async def recommend_react(request: RecommendationRequest):
    """ReAct 推荐"""
    return await runtime.supervisor.react_recommend(request)


@router.post("/api/v1/recommend/react/stream")
async def recommend_react_stream(request: RecommendationRequest):
    """SSE 流式 ReAct 推荐"""
    return StreamingResponse(
        _sse_wrapper(runtime.supervisor.react_stream_recommend(request)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/v1/recommend/graph")
async def recommend_via_graph(request: RecommendationRequest):
    """使用 LangGraph 状态图进行公选课推荐 (展示 LangGraph 能力)"""
    if not runtime.rec_graph:
        return {"error": "Graph not initialized"}
    state = {
        "user_id": request.user_id,
        "scene": request.scene,
        "num_items": request.num_items,
        "prompt": request.prompt or request.query or request.context.get("query", ""),
        "context": request.context,
    }
    result = await runtime.rec_graph.ainvoke(state)
    return {
        "request_id": result.get("request_id"),
        "user_id": result.get("user_id"),
        "courses": [course.model_dump() for course in result.get("final_courses", [])],
        "recommendation_reasons": result.get("recommendation_reasons", []),
        "selection_warnings": result.get("selection_warnings", []),
        "priority_advice": result.get("priority_advice", {}),
        "experiment_group": result.get("experiment_group", "control"),
        "total_latency_ms": round(result.get("total_latency_ms", 0), 1),
    }


def _collect_metrics(response: RecommendationResponse):
    for name, result in response.agent_results.items():
        runtime.metrics_collector.record_agent_call(
            agent_name=name,
            success=result.success,
            latency_ms=result.latency_ms,
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
        payload = json.dumps(event["data"], ensure_ascii=False)
        yield f"event: {event['event']}\ndata: {payload}\n\n"