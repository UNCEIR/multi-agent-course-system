# -*- coding: utf-8 -*-
"""工具横切钩子 middleware（Phase 4 P1-D：D1/D2/D4）。

实现 AgentMiddleware.wrap_tool_call / awrap_tool_call（deepagents ToolNode
直调 StructuredTool.invoke，`registry.call()` 在主 agent 路径是死代码，钩子必须挂
middleware）：

- D1 横切：before 返回 {block, reason} | None；after 记录 (ok, latency_ms, error)
- D2 熔断接入：before 查 registry breaker.can_proceed()（open 未到恢复 → block）；
  after 按结果 record_success / record_failure
- D4 同工具失败上限：连续失败 ≥ threshold（默认 3）→ 下次调用 block（强制换策略/终止）

block 返回结构化 ToolMessage（status=error，{code, message, isError: true}），
不吞异常、不静默。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage

logger = logging.getLogger(__name__)


class ToolHooksMiddleware(AgentMiddleware):
    """工具横切钩子：熔断 / 失败上限 / 记账 / 审计。"""

    def __init__(
        self,
        *,
        registry: Any = None,
        metrics_collector: Any = None,
        failure_threshold: int = 3,
    ) -> None:
        self._registry = registry
        self._metrics = metrics_collector
        self._failure_threshold = int(failure_threshold)
        self._consecutive_failures: dict[str, int] = {}

    # ── before / after ───────────────────────────────────────────────
    def _check_block(self, tool_name: str) -> str | None:
        """返回 block reason；可调用 → None。"""
        # D4：同工具连续失败上限
        if self._consecutive_failures.get(tool_name, 0) >= self._failure_threshold:
            return f"too_many_failures(count={self._consecutive_failures[tool_name]})"
        # D2：熔断（registry breaker）
        if self._registry is not None:
            breaker = self._registry._breakers.get(tool_name)
            if breaker is not None and not breaker.can_proceed():
                return f"circuit_open(state={breaker.state})"
        return None

    def _after(self, tool_name: str, ok: bool, latency_ms: float, error: str = "") -> None:
        # D2：熔断记账
        if self._registry is not None:
            breaker = self._registry._breakers.get(tool_name)
            if breaker is not None:
                if ok:
                    breaker.record_success()
                else:
                    breaker.record_failure()
        # D4：连续失败计数（成功清零）
        if ok:
            self._consecutive_failures.pop(tool_name, None)
        else:
            self._consecutive_failures[tool_name] = self._consecutive_failures.get(tool_name, 0) + 1
        # 埋点：对齐 recommend.py record_agent_call 模式（D8/C1）
        if self._metrics is not None:
            try:
                self._metrics.record_agent_call(tool_name, ok, latency_ms, error)
            except Exception:  # noqa: BLE001
                pass

    def _blocked_message(self, request: ToolCallRequest, reason: str) -> ToolMessage:
        tc = request.tool_call
        return ToolMessage(
            content=json.dumps(
                {"code": "TOOL_BLOCKED", "message": f"工具调用被拦截：{reason}", "isError": True, "reason": reason},
                ensure_ascii=False,
            ),
            tool_call_id=_tool_call_id(tc) or "call_unknown",
            name=_tool_call_name(tc),
            status="error",
        )

    # ── 同步（非流式 invoke 兜底） ───────────────────────────────────
    def wrap_tool_call(self, request: ToolCallRequest, handler):
        tool_name = _tool_call_name(request.tool_call)
        reason = self._check_block(tool_name)
        if reason:
            return self._blocked_message(request, reason)
        t0 = time.perf_counter()
        try:
            result = handler(request)
        except Exception as exc:  # noqa: BLE001
            self._after(tool_name, False, (time.perf_counter() - t0) * 1000, str(exc))
            raise
        ok = not _is_error_result(result)
        self._after(tool_name, ok, (time.perf_counter() - t0) * 1000, "" if ok else _result_error(result))
        return result

    # ── 异步（astream/ainvoke 主路径） ───────────────────────────────
    async def awrap_tool_call(self, request: ToolCallRequest, handler):
        tool_name = _tool_call_name(request.tool_call)
        reason = self._check_block(tool_name)
        if reason:
            return self._blocked_message(request, reason)
        t0 = time.perf_counter()
        try:
            result = await handler(request)
        except Exception as exc:  # noqa: BLE001
            self._after(tool_name, False, (time.perf_counter() - t0) * 1000, str(exc))
            raise
        ok = not _is_error_result(result)
        self._after(tool_name, ok, (time.perf_counter() - t0) * 1000, "" if ok else _result_error(result))
        return result


def _tool_call_name(tc) -> str:
    """ToolCallRequest.tool_call 是 dict（name/args/id）；兼容对象形态。"""
    if isinstance(tc, dict):
        return str(tc.get("name", "") or "")
    return str(getattr(tc, "name", "") or "")


def _tool_call_id(tc) -> str:
    if isinstance(tc, dict):
        return str(tc.get("id", "") or "")
    return str(getattr(tc, "id", "") or "")


def _is_error_result(result) -> bool:
    """判断工具结果是否 isError：ToolMessage status='error' 或 content JSON isError=true。"""
    if isinstance(result, ToolMessage):
        if result.status == "error":
            return True
        content = result.content
        if isinstance(content, str):
            try:
                return bool(json.loads(content).get("isError"))
            except (ValueError, TypeError):
                return False
        return False
    return False


def _result_error(result) -> str:
    if isinstance(result, ToolMessage):
        content = result.content
        if isinstance(content, str):
            try:
                data = json.loads(content)
                return str(data.get("message", content))[:120]
            except (ValueError, TypeError):
                return str(content)[:120]
        return str(content)[:120]
    return str(result)[:120]
