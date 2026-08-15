# -*- coding: utf-8 -*-
"""CircuitBreaker — 熔断器。

closed/open/half_open 三种状态，3 次失败熔断，支持恢复探测。
"""

from __future__ import annotations

import time


class CircuitBreaker:
    """熔断器 — 防止级联故障。

    状态机：closed → open（失败次数超阈值）→ half_open（恢复探测）→ closed（成功恢复）。

    Args:
        failure_threshold: 连续失败次数阈值（默认 3）
        recovery_timeout: 熔断后等待恢复的秒数（默认 30）
    """

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 30.0):
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._state = "closed"
        self._failure_count = 0
        self._last_failure_time = 0.0

    @property
    def state(self) -> str:
        """当前熔断器状态：closed / open / half_open。"""
        return self._state

    def call(self, func, *args, **kwargs):
        """在熔断保护下执行函数。

        Args:
            func: 要执行的函数
            *args, **kwargs: 传递给函数的参数

        Returns:
            函数执行结果

        Raises:
            RuntimeError: 熔断器处于 open 状态且未到恢复时间
            Exception: 函数执行抛出的异常
        """
        if self._state == "open":
            if time.time() - self._last_failure_time >= self._recovery_timeout:
                self._state = "half_open"
            else:
                raise RuntimeError(f"CircuitBreaker is OPEN (failure_count={self._failure_count})")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    async def acall(self, awaitable_factory):
        """熔断保护下执行 async 函数（工厂返回 coroutine）。

        Args:
            awaitable_factory: 返回 coroutine 的可调用对象

        Raises:
            RuntimeError: 熔断器处于 open 状态且未到恢复时间
            Exception: coroutine 抛出的异常
        """
        if self._state == "open":
            if time.time() - self._last_failure_time >= self._recovery_timeout:
                self._state = "half_open"
            else:
                raise RuntimeError(f"CircuitBreaker is OPEN (failure_count={self._failure_count})")

        try:
            result = await awaitable_factory()
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def record_success(self) -> None:
        """手动记录一次成功（MCP 工具返回 isError 结果时由调用方判定）。"""
        self._on_success()

    def record_failure(self) -> None:
        """手动记录一次失败（连接/调用失败且不抛异常的路径）。"""
        self._on_failure()

    def can_proceed(self) -> bool:
        """当前是否允许调用（open 且未到恢复时间 → False）。"""
        if self._state == "open":
            if time.time() - self._last_failure_time >= self._recovery_timeout:
                self._state = "half_open"
                return True
            return False
        return True

    def _on_success(self) -> None:
        """成功调用后的状态转换。"""
        if self._state == "half_open":
            self._state = "closed"
        self._failure_count = 0

    def _on_failure(self) -> None:
        """失败调用后的状态转换。"""
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self._failure_threshold:
            self._state = "open"

    def reset(self) -> None:
        """手动重置熔断器到 closed 状态。"""
        self._state = "closed"
        self._failure_count = 0
        self._last_failure_time = 0.0