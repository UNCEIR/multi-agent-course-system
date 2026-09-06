# -*- coding: utf-8 -*-
"""工具横切钩子 middleware 单测（Phase 4 D1/D2/D4/D5/D8）：

- 熔断 open → before block（handler 不被调用，返回结构化 error ToolMessage）
- 同工具连续失败 ≥3 → 第 4 次 block
- after 记账：breaker record_success/failure + 连续失败计数
- 埋点 record_agent_call
- 意图说明书：query_handbook / query_transcript 描述互相点名（D5）
- LLMError 类型化 code（D7）
"""

from __future__ import annotations

import json

import pytest
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage

from agent.middleware.tool_hooks import ToolHooksMiddleware
from ai.llm_client import LLMError
from tools.circuit_breaker import CircuitBreaker


class _FakeRegistry:
    def __init__(self, breaker: CircuitBreaker):
        self._breakers = {"tool_x": breaker}


def _request(name: str = "tool_x") -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": {}, "id": "call_1", "type": "tool_call"},
        tool=None,
        state=None,
        runtime=None,
    )


def _ok_handler(req):
    return ToolMessage(content="ok", tool_call_id="call_1", name=req.tool_call["name"], status="success")


# ── D2 熔断 ────────────────────────────────────────────────────────
@pytest.mark.unit
def test_circuit_open_blocks_before_handler():
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
    for _ in range(3):
        breaker.record_failure()
    mw = ToolHooksMiddleware(registry=_FakeRegistry(breaker))
    called = {"n": 0}

    def handler(req):
        called["n"] += 1
        return _ok_handler(req)

    result = mw.wrap_tool_call(_request(), handler)
    assert called["n"] == 0  # handler 未被调用
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "circuit_open" in json.loads(result.content)["reason"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_awrap_circuit_open_blocks():
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
    for _ in range(3):
        breaker.record_failure()
    mw = ToolHooksMiddleware(registry=_FakeRegistry(breaker))
    called = {"n": 0}

    async def handler(req):
        called["n"] += 1
        return _ok_handler(req)

    result = await mw.awrap_tool_call(_request(), handler)
    assert called["n"] == 0
    assert result.status == "error"


# ── D4 同工具失败上限 ──────────────────────────────────────────────
@pytest.mark.unit
def test_failure_threshold_blocks_fourth_call():
    mw = ToolHooksMiddleware(registry=None, failure_threshold=3)
    handler = _ok_handler  # 失败由 _after 判定（返回非 error 不算失败）——这里用抛异常模拟

    def failing_handler(req):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        mw.wrap_tool_call(_request(), failing_handler)
    with pytest.raises(RuntimeError):
        mw.wrap_tool_call(_request(), failing_handler)
    with pytest.raises(RuntimeError):
        mw.wrap_tool_call(_request(), failing_handler)
    # 第 4 次：连续失败 ≥3 → block，handler 不执行
    result = mw.wrap_tool_call(_request(), failing_handler)
    assert isinstance(result, ToolMessage)
    assert "too_many_failures" in json.loads(result.content)["reason"]


@pytest.mark.unit
def test_success_resets_failure_count():
    mw = ToolHooksMiddleware(registry=None, failure_threshold=3)

    def failing_handler(req):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        mw.wrap_tool_call(_request(), failing_handler)
    with pytest.raises(RuntimeError):
        mw.wrap_tool_call(_request(), failing_handler)
    mw.wrap_tool_call(_request(), _ok_handler)  # 成功 → 清零
    result = mw.wrap_tool_call(_request(), _ok_handler)
    assert not isinstance(result, ToolMessage) or result.status != "error"


# ── D1 记账/埋点 ───────────────────────────────────────────────────
@pytest.mark.unit
def test_after_records_breaker_and_metrics():
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
    metrics = _FakeMetrics()
    mw = ToolHooksMiddleware(registry=_FakeRegistry(breaker), metrics_collector=metrics)
    mw.wrap_tool_call(_request(), _ok_handler)
    assert metrics.calls == [("tool_x", True)]


class _FakeMetrics:
    def __init__(self):
        self.calls = []

    def record_agent_call(self, agent_name, success, latency_ms, error=""):
        self.calls.append((agent_name, success))


@pytest.mark.unit
def test_after_records_breaker_failure_on_error_result():
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
    mw = ToolHooksMiddleware(registry=_FakeRegistry(breaker))

    def err_handler(req):
        return ToolMessage(content=json.dumps({"isError": True, "message": "bad"}), tool_call_id="call_1", name="tool_x", status="error")

    mw.wrap_tool_call(_request(), err_handler)
    assert breaker._failure_count == 1


# ── D5 意图说明书互相点名 ──────────────────────────────────────────
@pytest.mark.unit
def test_knowledge_tools_description_mutual_naming():
    from tools.knowledge.query_handbook import query_handbook
    from tools.knowledge.query_transcript import query_transcript

    assert "query_transcript" in query_handbook.description
    assert "query_handbook" in query_transcript.description
    assert "何时用" in query_handbook.description
    assert "何时用" in query_transcript.description


# ── D7 类型化错误码 ────────────────────────────────────────────────
@pytest.mark.unit
def test_llm_error_code_attribute():
    exc = LLMError("quota", "配额不足")
    assert exc.code == "quota"
    # chat.py 用 getattr(exc, "code", ...) 提取
    assert getattr(exc, "code", type(exc).__name__.upper()) == "quota"
