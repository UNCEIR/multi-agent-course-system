# -*- coding: utf-8 -*-
"""monitor 规则单测（Phase 4 C3/C4）：命中/去重/建议。"""

from __future__ import annotations

import pytest

from observability.metrics import MetricsCollector
from observability.monitor import MonitorAgent, RULES


@pytest.mark.unit
def test_rules_threshold_table_defined():
    codes = {r["code"] for r in RULES}
    assert {"success_rate_drop", "avg_latency_high", "error_spike"} <= codes


@pytest.mark.unit
def test_success_rate_drop_alert():
    c = MetricsCollector()
    for _ in range(5):
        c.record_agent_call("agent_x", False, 100.0, "err quota")
    m = MonitorAgent(metrics_collector=c)
    alerts = m.scan()
    codes = {a["code"] for a in alerts}
    assert "success_rate_drop" in codes
    assert "quota_error" in codes  # err 文本含 quota 标记 → 配额告警


@pytest.mark.unit
def test_quota_error_alert_marker():
    c = MetricsCollector()
    c.record_agent_call("agent_x", False, 100.0, "RateLimitError quota exceeded")
    m = MonitorAgent(metrics_collector=c)
    alerts = m.scan()
    assert any(a["code"] == "quota_error" for a in alerts)


@pytest.mark.unit
def test_dedupe_same_alert_once():
    c = MetricsCollector()
    for _ in range(5):
        c.record_agent_call("agent_x", False, 100.0, "err")
    m = MonitorAgent(metrics_collector=c)
    first = m.scan()
    second = m.scan()
    assert len(first) > 0
    assert len(second) == 0  # 短窗去重


@pytest.mark.unit
def test_insufficient_samples_no_alert():
    c = MetricsCollector()
    c.record_agent_call("agent_x", False, 100.0, "err")  # 样本 <3
    m = MonitorAgent(metrics_collector=c)
    assert m.scan() == []


@pytest.mark.unit
def test_suggestions_non_empty():
    m = MonitorAgent(metrics_collector=None)
    assert len(m.suggest("quota_error")) > 0
    assert len(m.suggest("success_rate_drop")) > 0
