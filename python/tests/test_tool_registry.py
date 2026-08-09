# -*- coding: utf-8 -*-
"""ToolRegistry 单元测试。

验证 tool 注册、获取、allowlist 门控、边界条件。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_core.tools import tool


@pytest.fixture
def fresh_registry():
    from tools.registry import ToolRegistry
    return ToolRegistry()


class TestToolRegistry:
    """验证 ToolRegistry 核心功能。"""

    def test_register_and_get(self, fresh_registry):
        """注册一个 tool 后能按名称获取。"""
        registry = fresh_registry

        @tool
        def my_tool() -> str:
            """A test tool."""
            return "hello"

        registry.register(my_tool)
        assert registry.get("my_tool") is my_tool

    def test_get_nonexistent_returns_none(self, fresh_registry):
        """获取不存在的 tool 返回 None。"""
        registry = fresh_registry
        assert registry.get("nonexistent") is None

    def test_register_many(self, fresh_registry):
        """批量注册多个 tool。"""
        registry = fresh_registry

        @tool
        def tool_a() -> str:
            """tool a"""
            return "a"

        @tool
        def tool_b() -> str:
            """tool b"""
            return "b"

        registry.register_many([tool_a, tool_b])
        assert registry.get("tool_a") is tool_a
        assert registry.get("tool_b") is tool_b
        assert len(registry.list_tools()) == 2

    def test_get_all_returns_all(self, fresh_registry):
        """get_all() 返回全部已注册 tool。"""
        registry = fresh_registry

        @tool
        def tool_a() -> str:
            """tool a"""
            return "a"

        registry.register(tool_a)
        all_tools = registry.get_all()
        assert len(all_tools) == 1
        assert all_tools[0] is tool_a

    def test_get_all_filtered_by_allowlist(self, fresh_registry):
        """get_all(allowed=[...]) 只返回允许的 tool。"""
        registry = fresh_registry

        @tool
        def tool_a() -> str:
            """tool a"""
            return "a"

        @tool
        def tool_b() -> str:
            """tool b"""
            return "b"

        registry.register_many([tool_a, tool_b])
        filtered = registry.get_all(allowed=["tool_a"])
        assert len(filtered) == 1
        assert filtered[0] is tool_a

    def test_get_all_filtered_unknown_skipped(self, fresh_registry):
        """allowlist 中包含未注册的 tool 名称时静默跳过。"""
        registry = fresh_registry

        @tool
        def tool_a() -> str:
            """tool a"""
            return "a"

        registry.register(tool_a)
        filtered = registry.get_all(allowed=["tool_a", "unknown_tool"])
        assert len(filtered) == 1
        assert filtered[0] is tool_a

    def test_get_all_empty_registry(self, fresh_registry):
        """空注册表返回空列表。"""
        registry = fresh_registry
        assert registry.get_all() == []

    def test_get_all_empty_allowlist(self, fresh_registry):
        """空 allowlist 返回空列表。"""
        registry = fresh_registry

        @tool
        def tool_a() -> str:
            """tool a"""
            return "a"

        registry.register(tool_a)
        assert registry.get_all(allowed=[]) == []

    def test_is_allowed_after_register(self, fresh_registry):
        """注册后自动加入 allowlist。"""
        registry = fresh_registry

        @tool
        def my_tool() -> str:
            """my tool desc"""
            return "ok"

        registry.register(my_tool)
        assert registry.is_allowed("my_tool") is True

    def test_is_allowed_unknown(self, fresh_registry):
        """未注册的 tool 不在 allowlist 中。"""
        registry = fresh_registry
        assert registry.is_allowed("unknown") is False

    def test_list_tools_metadata(self, fresh_registry):
        """list_tools() 返回 name 和 description。"""
        registry = fresh_registry

        @tool
        def my_tool(arg1: str) -> str:
            """My custom tool description."""
            return arg1

        registry.register(my_tool)
        meta = registry.list_tools()
        assert len(meta) == 1
        assert meta[0]["name"] == "my_tool"
        assert "description" in meta[0]

    def test_register_twice_overwrites(self, fresh_registry):
        """重复注册同名 tool 会覆盖（允许热更新）。"""
        registry = fresh_registry

        @tool
        def my_tool() -> str:
            """tool v1"""
            return "v1"

        registry.register(my_tool)

        @tool
        def my_tool() -> str:  # noqa: F811
            """tool v2"""
            return "v2"

        registry.register(my_tool)
        assert registry.get("my_tool") is my_tool


class TestGlobalRegistry:
    """验证全局单例 get_registry()。"""

    def test_get_registry_singleton(self):
        """get_registry() 返回同一实例。"""
        from tools.registry import get_registry

        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_get_registry_is_tool_registry(self):
        """get_registry() 返回 ToolRegistry 实例。"""
        from tools.registry import ToolRegistry, get_registry

        assert isinstance(get_registry(), ToolRegistry)