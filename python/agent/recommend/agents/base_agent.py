from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from inspect import isawaitable
from typing import Any

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from models.schemas import AgentResult

logger = structlog.get_logger()


class BaseAgent(ABC):
    def __init__(self, name: str, timeout: float = 30.0, max_retries: int = 5):
        self.name = name
        self.timeout = timeout
        self.max_retries = max_retries
        self._call_count = 0
        self._error_count = 0
        self.logger = structlog.get_logger()

    @abstractmethod
    async def _execute(self, **kwargs: Any) -> AgentResult:
        """Core logic implemented by each concrete agent."""

    async def run(self, **kwargs: Any) -> AgentResult:
        start = time.perf_counter()
        self._call_count += 1

        try:
            result = await self._run_with_retries(**kwargs)
            result.latency_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "agent.success",
                agent=self.name,
                latency_ms=round(result.latency_ms, 1),
            )
            return result
        except Exception as exc:
            self._error_count += 1
            latency_ms = (time.perf_counter() - start) * 1000
            logger.error("agent.failed", agent=self.name, error=str(exc))
            return self._fallback(latency_ms, exc)

    async def _run_with_retries(self, **kwargs: Any) -> AgentResult:
        @retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
            reraise=True,
        )
        async def _inner():
            # 单次 LLM 调用超时兜底：超过 self.timeout 抛 TimeoutError，
            # 由 run() 捕获后走 _fallback（规则/启发式兜底），避免单次调用卡死。
            result = await asyncio.wait_for(self._execute(**kwargs), timeout=self.timeout)
            if isawaitable(result):
                result = await result
            return result

        return await _inner()

    def _fallback(self, latency_ms: float, exc: Exception) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            success=False,
            latency_ms=latency_ms,
            error=str(exc),
            confidence=0.0,
        )

    @property
    def error_rate(self) -> float:
        if self._call_count == 0:
            return 0.0
        return self._error_count / self._call_count
