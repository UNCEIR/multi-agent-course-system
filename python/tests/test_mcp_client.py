# -*- coding: utf-8 -*-
"""MCP 客户端测试：注册表/发现/调用/namespace/熔断/未配置跳过。"""

from __future__ import annotations

import pytest

from tests.fake_mcp_server import install_fake_tools
from tools.circuit_breaker import CircuitBreaker
from tools.mcp_client import MultiServerMCPClient, reset_mcp_client


@pytest.fixture
def client():
    reset_mcp_client()
    yield MultiServerMCPClient()
    reset_mcp_client()


@pytest.mark.unit
async def test_server_registry_and_skip_without_url(client):
    """未配置 url 的服务器连接失败但不抛（跳过），熔断计数。"""
    client.register_server("ghost", {"transport": "streamable_http", "url": "", "namespace": "x"})
    assert await client.connect("ghost") is False
    assert client._breaker("ghost")._failure_count == 1


@pytest.mark.unit
async def test_list_tools_with_namespace(client):
    install_fake_tools(client)
    tools = await client.list_tools("tavily")
    assert tools[0]["name"].startswith("search/")


@pytest.mark.unit
async def test_call_tool_ok(client):
    install_fake_tools(client)
    result = await client.call_tool("tavily", "search", {"query": "高考"})
    assert "高考" in str(result)


@pytest.mark.unit
async def test_call_tool_not_found(client):
    install_fake_tools(client)
    result = await client.call_tool("tavily", "no_such_tool", {})
    assert result["isError"] is True
    assert result["code"] == "MCP_TOOL_NOT_FOUND"


@pytest.mark.unit
async def test_breaker_opens_after_failures(client):
    """连续失败 3 次 → 熔断 → 直接结构化错误（不调底层）。"""
    install_fake_tools(client, fail_on_call=True)
    for _ in range(3):
        await client.call_tool("tavily", "search", {"query": "x"})
    result = await client.call_tool("tavily", "search", {"query": "x"})
    assert result["code"] == "MCP_CIRCUIT_OPEN"
    assert client._breaker("tavily").state == "open"


@pytest.mark.unit
def test_circuit_breaker_acall():
    """acall：async 函数熔断/复位（评审 P1-6）。"""
    import asyncio

    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=30)

    async def _fail():
        raise ValueError("boom")

    async def _ok():
        return "ok"

    async def run():
        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.acall(_fail)
        assert cb.state == "open"
        with pytest.raises(RuntimeError):
            await cb.acall(_ok)

    asyncio.run(run())
