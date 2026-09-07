# -*- coding: utf-8 -*-
"""prometheus 指标注册/导出 + MetricsCollector 桥接单测（Phase 4 C1/C4）。"""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY

from observability.metrics import MetricsCollector
from observability.prometheus import render


def _sample_count(name: str, labels: dict | None = None) -> int:
    """从 prometheus registry 读采样数。"""
    metric = REGISTRY.get_sample_value(name, labels) if labels else REGISTRY.get_sample_value(name)
    return int(metric or 0)


@pytest.mark.unit
def test_record_agent_call_exported():
    c = MetricsCollector()
    c.record_agent_call("agent_x", True, 1500.0)
    text = render().decode("utf-8")
    assert 'agent_call_total{agent="agent_x",result="success"}' in text
    assert "agent_call_latency_seconds" in text


@pytest.mark.unit
def test_record_failure_and_error_label():
    c = MetricsCollector()
    c.record_agent_call("agent_x", False, 500.0, "boom")
    text = render().decode("utf-8")
    assert 'agent_call_total{agent="agent_x",result="error"}' in text


@pytest.mark.unit
def test_record_business_event_exported():
    c = MetricsCollector()
    c.record_business_event("llm_quota", phase="chat")
    text = render().decode("utf-8")
    assert 'business_event_total{code="llm_quota",phase="chat"}' in text


@pytest.mark.unit
def test_metrics_collector_json_contract():
    c = MetricsCollector()
    c.record_agent_call("agent_x", True, 100.0)
    stats = c.get_agent_stats()
    assert "agent_x" in stats
    assert stats["agent_x"]["success_rate"] == 1.0
    assert "recent_errors" in stats["agent_x"]
