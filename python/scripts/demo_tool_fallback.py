# -*- coding: utf-8 -*-
"""工具断裂兜底演示（Phase 4 P1-F / F1）。

链路：外部工具断裂（抛异常）→ 熔断（3 次失败 open）→ 工具 middleware 拦截
（结构化 error ToolMessage，不吞异常）→ 恢复（breaker reset → 第 5 次成功）。

纯本地演示：不连真实 LLM / 外部服务；输出可复现状态序列。
用法：python scripts/demo_tool_fallback.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage

from agent.middleware.tool_hooks import ToolHooksMiddleware
from tools.circuit_breaker import CircuitBreaker


class _FakeRegistry:
    def __init__(self, breaker):
        self._breakers = {"external_api": breaker}


class _ExternalAPI:
    """模拟外部工具：连续 3 次抛异常（断裂），reset 后恢复。"""

    def __init__(self):
        self._fail_countdown = 3
        self.calls = 0

    def invoke(self, *args, **kwargs):
        self.calls += 1
        if self._fail_countdown > 0:
            self._fail_countdown -= 1
            raise RuntimeError("external api timeout (模拟断裂)")
        return {"ok": True, "data": "部分结果保留"}


def _request() -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": "external_api", "args": {}, "id": "call_demo", "type": "tool_call"},
        tool=None,
        state=None,
        runtime=None,
    )


def _handle(mw, handler):
    try:
        return mw.wrap_tool_call(_request(), handler)
    except Exception as exc:  # noqa: BLE001
        return {"_raised": str(exc)}


def main() -> int:
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
    registry = _FakeRegistry(breaker)
    mw = ToolHooksMiddleware(registry=registry, failure_threshold=3)
    external = _ExternalAPI()

    def handler(req):
        return external.invoke()

    print("== 工具断裂兜底演示（Phase 4 F1）==")
    sequence = []
    for i in range(1, 6):
        result = _handle(mw, handler)
        state = {
            "step": i,
            "breaker": breaker.state,
            "external_calls": external.calls,
            "type": type(result).__name__,
        }
        if isinstance(result, ToolMessage):
            payload = json.loads(result.content)
            state["outcome"] = "blocked"
            state["reason"] = payload.get("reason", "")
            state["isError"] = payload.get("isError")
        elif isinstance(result, dict) and "_raised" in result:
            state["outcome"] = "raised"
            state["detail"] = result["_raised"][:40]
        else:
            state["outcome"] = "success"
            state["data"] = result
        sequence.append(state)
        print(f"  step{i}: breaker={state['breaker']:9s} calls={external.calls} -> {state['outcome']} {state.get('reason', '')}")

    # 恢复：重置熔断 + 清连续失败计数后重试成功
    breaker.reset()
    mw._consecutive_failures.clear()
    final = _handle(mw, handler)
    print(f"  step6(reset): breaker={breaker.state} -> {type(final).__name__} data={final.get('data') if isinstance(final, dict) else ''}")
    assert any(s["outcome"] == "blocked" for s in sequence), "必须出现熔断拦截"
    assert isinstance(final, dict) and final.get("ok"), "恢复后必须成功（部分结果保留）"
    print("== 演示通过：断裂 → 熔断 → 拦截 → 恢复 ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
