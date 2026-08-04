"""健康检查与监控路由 — /health /metrics /experiments 端点。"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter

from app import runtime
from config import get_settings
from ai.tracing import get_tracing_status

router = APIRouter()
settings = get_settings()


def _llm_runtime_summary() -> dict[str, Any]:
    parsed = urlparse(settings.llm_base_url)
    host = parsed.netloc or parsed.path
    return {
        "model": settings.llm_model,
        "base_url_host": host,
        "looks_like_dashscope": "dashscope.aliyuncs.com" in host,
    }


async def _health_payload() -> dict[str, Any]:
    redis_ok = False
    if runtime.redis_repo:
        redis_ok = await runtime.redis_repo.ping()
    return {
        "status": "healthy",
        "model": settings.llm_model,
        "llm": _llm_runtime_summary(),
        "embedding_provider": settings.embedding_provider,
        "langsmith": get_tracing_status(),
        "deps": {
            "mysql": runtime.mysql_repo.ping() if runtime.mysql_repo else False,
            "redis": redis_ok,
            "milvus": runtime.course_vector_repo.ping() if runtime.course_vector_repo else False,
        },
    }


@router.get("/health")
async def health():
    return await _health_payload()


@router.get("/api/v1/health")
async def health_api_v1():
    return await _health_payload()


@router.get("/api/v1/experiments")
async def get_experiments():
    experiments = {}
    for exp_id, exp in runtime.ab_engine.experiments.items():
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
            "stats": runtime.ab_engine.get_stats(exp_id),
        }
    return experiments


@router.get("/api/v1/metrics")
async def get_metrics():
    return {
        "agents": runtime.metrics_collector.get_agent_stats(),
        "business": runtime.metrics_collector.get_business_stats(),
    }


@router.post("/api/v1/experiments/{experiment_id}/outcome")
async def record_outcome(experiment_id: str, group: str, success: bool):
    runtime.ab_engine.record_outcome(experiment_id, group, success)
    return {"status": "recorded"}