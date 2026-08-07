# -*- coding: utf-8 -*-
"""ToolRegistry — 工具注册、MCP 懒加载、allowlist 门控。

统一管理所有 tool 的注册、发现和权限控制。
支持 MCP 动态发现接入外部工具。

Phase: 1 (implemented, MCP 懒加载待 Phase 3)
"""

from __future__ import annotations

from typing import Any


class ToolRegistry:
    """工具注册中心。

    管理所有 tool 的注册、MCP 懒加载、allowlist 门控。
    Phase 1 为骨架，Phase 3 接入 MCP 动态发现。
    """

    def __init__(self):
        self._tools: dict[str, Any] = {}
        self._allowlist: set[str] = set()

    def register(self, tool: Any) -> None:
        """注册一个 tool。

        Args:
            tool: @tool 装饰器装饰的函数或 StructuredTool 实例
        """
        name = getattr(tool, "name", None) or tool.__name__
        self._tools[name] = tool
        self._allowlist.add(name)

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


# 全局单例
_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    """获取全局 ToolRegistry 单例。"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry