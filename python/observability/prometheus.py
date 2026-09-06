# -*- coding: utf-8 -*-
"""Prometheus 指标注册 / 导出（Phase 4 P1-C / C1）。

MetricsCollector（内存 JSON）并行输出 Prometheus 文本：agent 调用计数/延迟、
业务事件、检索命中。`/metrics` 端点（api/metrics.py）用 `render()` 导出；
`/api/v1/metrics` JSON 契约冻结保留在 health.py。
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

_AGENT_CALL_TOTAL = Counter(
    "agent_call_total", "Agent/工具调用次数", ["agent", "result"]
)
_AGENT_CALL_LATENCY = Histogram(
    "agent_call_latency_seconds",
    "Agent/工具调用延迟（秒）",
    ["agent"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)
_BUSINESS_EVENT_TOTAL = Counter("business_event_total", "业务事件计数", ["code", "phase"])
_RETRIEVAL_HITS = Counter("retrieval_hits_total", "检索命中计数", ["scope"])
_RETRIEVAL_CACHE_HIT = Counter("retrieval_cache_hit_total", "检索缓存命中计数", ["scope"])


def record_agent_call(agent_name: str, success: bool, latency_ms: float, error: str = "") -> None:
    _AGENT_CALL_TOTAL.labels(agent=agent_name, result="success" if success else "error").inc()
    _AGENT_CALL_LATENCY.labels(agent=agent_name).observe(max(0.0, float(latency_ms or 0)) / 1000.0)


def record_business_event(code: str, phase: str) -> None:
    _BUSINESS_EVENT_TOTAL.labels(code=str(code or "unknown"), phase=str(phase or "")).inc()


def record_retrieval(scope: str, hit: bool, cache_hit: bool = False) -> None:
    _RETRIEVAL_HITS.labels(scope=str(scope or "unknown")).inc()
    if cache_hit:
        _RETRIEVAL_CACHE_HIT.labels(scope=str(scope or "unknown")).inc()


def render() -> bytes:
    """Prometheus 文本格式（generate_latest）。"""
    return generate_latest()


def content_type() -> str:
    return CONTENT_TYPE_LATEST
