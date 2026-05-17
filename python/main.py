"""
学校公选课 Multi-Agent 推荐系统 — FastAPI Entry Point

Endpoints:
  POST /api/v1/recommend          - 获取公选课个性化推荐
  POST /api/v1/recommend/stream   - SSE 流式公选课推荐
  POST /api/v1/recommend/graph    - 通过LangGraph pipeline推荐公选课
  GET  /api/v1/experiments        - 查看A/B实验状态
  GET  /api/v1/metrics            - 查看系统监控指标
  GET  /api/v1/health             - 健康检查（与前端 /api 前缀一致）
  GET  /health                    - 健康检查（运维探活常用路径）
"""

from __future__ import annotations

import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from config import get_settings
from models.schemas import RecommendationRequest, RecommendationResponse
from orchestrator.supervisor import SupervisorOrchestrator
from orchestrator.graph import build_recommendation_graph
from repositories import CourseVectorRepository, MySQLRepository, RedisFeatureRepository
from services.ab_test import ABTestEngine
from services.embedding_client import build_embedding_client
from services.metrics import MetricsCollector

logger = structlog.get_logger()
settings = get_settings()


ab_engine = ABTestEngine()
metrics_collector = MetricsCollector()
supervisor = SupervisorOrchestrator(ab_engine=ab_engine)
rec_graph = None
mysql_repo = MySQLRepository()
redis_repo = RedisFeatureRepository()
course_vector_repo = CourseVectorRepository(build_embedding_client())


@asynccontextmanager
async def lifespan(app: FastAPI):
    global rec_graph
    _assert_llm_config()
    rec_graph = build_recommendation_graph()
    llm_parsed = urlparse(settings.llm_base_url)
    logger.info(
        "app.startup",
        model=settings.llm_model,
        llm_api_host=llm_parsed.netloc or llm_parsed.path,
    )
    yield
    logger.info("app.shutdown")


app = FastAPI(
    title="Public Elective Course Multi-Agent Recommendation System",
    description="学生画像Agent + 课程召回Agent + 课程重排Agent + 选课可行性Agent + 推荐理由Agent",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _llm_runtime_summary() -> dict[str, Any]:
    """便于核对灵积：若 base_url_host 不是 dashscope.aliyuncs.com，控制台不会有对应用量。"""
    parsed = urlparse(settings.llm_base_url)
    host = parsed.netloc or parsed.path
    return {
        "model": settings.llm_model,
        "base_url_host": host,
        "looks_like_dashscope": "dashscope.aliyuncs.com" in host,
    }


async def _health_payload() -> dict[str, Any]:
    redis_ok = await redis_repo.ping()
    return {
        "status": "healthy",
        "model": settings.llm_model,
        "llm": _llm_runtime_summary(),
        "embedding_provider": settings.embedding_provider,
        "deps": {
            "mysql": mysql_repo.ping(),
            "redis": redis_ok,
            "milvus": course_vector_repo.ping(),
        },
    }


@app.get("/health")
async def health():
    return await _health_payload()


@app.get("/api/v1/health")
async def health_api_v1():
    return await _health_payload()


@app.post("/api/v1/recommend", response_model=RecommendationResponse)
async def recommend(request: RecommendationRequest):
    """使用Supervisor编排器进行公选课推荐 (生产推荐用法)"""
    response = await supervisor.recommend(request)
    _collect_metrics(response)
    return response


@app.post("/api/v1/recommend/stream")
async def recommend_stream(request: RecommendationRequest):
    """SSE 流式公选课推荐 (前端打字效果 + 阶段进度推送)"""
    return StreamingResponse(
        _sse_wrapper(supervisor.stream_recommend(request)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/v1/recommend/graph")
async def recommend_via_graph(request: RecommendationRequest):
    """使用LangGraph状态图进行公选课推荐 (展示LangGraph能力)"""
    if not rec_graph:
        return {"error": "Graph not initialized"}
    state = {
        "user_id": request.user_id,
        "scene": request.scene,
        "num_items": request.num_items,
        "prompt": request.prompt or request.query or request.context.get("query", ""),
        "context": request.context,
    }
    result = await rec_graph.ainvoke(state)
    return {
        "request_id": result.get("request_id"),
        "user_id": result.get("user_id"),
        "courses": [course.model_dump() for course in result.get("final_courses", [])],
        "recommendation_reasons": result.get("recommendation_reasons", []),
        "selection_warnings": result.get("selection_warnings", []),
        "experiment_group": result.get("experiment_group", "control"),
        "total_latency_ms": round(result.get("total_latency_ms", 0), 1),
    }


@app.get("/api/v1/experiments")
async def get_experiments():
    """查看所有A/B实验状态"""
    experiments = {}
    for exp_id, exp in ab_engine.experiments.items():
        experiments[exp_id] = {
            "name": exp.name,
            "enabled": exp.enabled,
            "groups": [
                {
                    "name": g.name,
                    "weight": g.weight,
                    "config": g.config,
                    "successes": g.successes,
                    "failures": g.failures,
                }
                for g in exp.groups
            ],
            "stats": ab_engine.get_stats(exp_id),
        }
    return experiments


@app.get("/api/v1/metrics")
async def get_metrics():
    """查看系统监控指标"""
    return {
        "agents": metrics_collector.get_agent_stats(),
        "business": metrics_collector.get_business_stats(),
    }


@app.post("/api/v1/experiments/{experiment_id}/outcome")
async def record_outcome(experiment_id: str, group: str, success: bool):
    """记录A/B测试结果,更新Thompson Sampling"""
    ab_engine.record_outcome(experiment_id, group, success)
    return {"status": "recorded"}


def _collect_metrics(response: RecommendationResponse):
    for name, result in response.agent_results.items():
        metrics_collector.record_agent_call(
            agent_name=name,
            success=result.success,
            latency_ms=result.latency_ms,
        )


async def _sse_wrapper(generator):
    async for event in generator:
        payload = json.dumps(event["data"], ensure_ascii=False)
        yield f"event: {event['event']}\ndata: {payload}\n\n"


def _assert_llm_config() -> None:
    required = {
        "ECOM_LLM_API_KEY": settings.llm_api_key,
        "ECOM_LLM_BASE_URL": settings.llm_base_url,
        "ECOM_LLM_MODEL": settings.llm_model,
    }
    missing = [name for name, value in required.items() if not str(value).strip()]
    if missing:
        raise RuntimeError(f"Missing required LLM env vars: {', '.join(missing)}")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
