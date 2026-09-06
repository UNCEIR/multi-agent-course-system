# -*- coding: utf-8 -*-
"""ToolRegistry — 工具注册、MCP 懒加载、allowlist 门控。

统一管理所有 tool 的注册、发现和权限控制。
支持 MCP 动态发现接入外部工具。

Phase: 1 (implemented, MCP 懒加载待 Phase 3)
"""

from __future__ import annotations

import logging
from typing import Any

from .circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册中心。

    管理所有 tool 的注册、MCP 懒加载、allowlist 门控。
    Phase 1 为骨架，Phase 3 接入 MCP 动态发现。
    """

    def __init__(self, *, failure_threshold: int = 3, recovery_timeout: float = 30.0):
        self._tools: dict[str, Any] = {}
        self._allowlist: set[str] = set()
        self._breakers: dict[str, CircuitBreaker] = {}
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._internal: set[str] = set()  # Phase 4 D10（M7）：受控暴露工具（仅系统显式触发）

    # M6（Phase 4 D5）：description 硬门槛检查点（warning 级，不阻断注册）
    _DESC_SIGNALS = ("何时用", "何时不用", "边界", "不要", "请用")

    def _validate_description(self, name: str, desc: str) -> None:
        """description 结构校验：缺「做什么/边界/消歧」信号时告警，便于意图消歧排查。"""
        missing = [s for s in self._DESC_SIGNALS if s not in desc]
        if missing and len(desc) < 60:
            logger.warning("tool_description_missing_usage_clause tool=%s missing=%s", name, missing)

    def register(self, tool: Any) -> None:
        """注册一个 tool。

        Args:
            tool: @tool 装饰器装饰的函数或 StructuredTool 实例
        """
        name = getattr(tool, "name", None) or tool.__name__
        self._tools[name] = tool
        self._validate_description(name, getattr(tool, "description", "") or "")
        self._allowlist.add(name)
        self._breakers[name] = CircuitBreaker(
            failure_threshold=self._failure_threshold,
            recovery_timeout=self._recovery_timeout,
        )

    def register_many(self, tools: list) -> None:
        """批量注册多个 tool。

        Args:
            tools: @tool 列表
        """
        for t in tools:
            self.register(t)

    def get(self, name: str) -> Any | None:
        """按名称获取已注册的 tool。"""
        return self._tools.get(name)

    def get_all(self, allowed: list[str] | None = None) -> list[Any]:
        """返回所有已注册的 tool，按 allowlist 过滤。

        Args:
            allowed: 允许的 tool 名称列表。None 返回全部。

        Returns:
            tool 实例列表
        """
        if allowed is None:
            return list(self._tools.values())
        return [self._tools[n] for n in allowed if n in self._tools]

    def list_tools(self) -> list[dict[str, str]]:
        """列出所有已注册的 tool 元数据。"""
        return [
            {"name": name, "description": getattr(tool, "description", "")}
            for name, tool in self._tools.items()
        ]

    def is_allowed(self, name: str) -> bool:
        """检查 tool 是否在 allowlist 中。"""
        return name in self._allowlist

    def mark_internal(self, name: str) -> None:
        """标注工具为内部编排/敏感工具（Phase 4 D10 / M7）：默认不对模型可见可调，仅系统显式触发。

        当前无敏感工具需标记（dispatch_module 本就是 main_agent 路由工具）；该方法与
        is_internal 提供受控暴露的注册点，供后续敏感 skill/工具（成绩单写库/审批等）接入。
        """
        self._internal.add(name)

    def is_internal(self, name: str) -> bool:
        return name in self._internal

    def call(self, name: str, *args, **kwargs) -> Any:
        """通过对应熔断器调用已注册的 tool。

        LangChain tool 使用 ``invoke``，普通 callable 直接调用；统一入口便于
        API、subagent 和后续 MCP tool 共享失败计数。
        """
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"未注册工具：{name}")
        target = getattr(tool, "invoke", tool)
        invocation = lambda: target(*args, **kwargs)
        return self._breakers[name].call(invocation)

    def breaker_state(self, name: str) -> str:
        """返回工具熔断器状态，便于健康检查和测试观察。"""
        if name not in self._breakers:
            raise KeyError(f"未注册工具：{name}")
        return self._breakers[name].state


# 全局单例
_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    """获取全局 ToolRegistry 单例。"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
