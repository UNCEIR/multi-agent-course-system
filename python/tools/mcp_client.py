# -*- coding: utf-8 -*-
"""MCP 客户端 — 懒加载连接，MultiServerMCPClient 管理。

对接外部 TS 服务（FastGPT mcp_server 等），支持 tools/list 动态发现。
Phase 3 实装完整功能，当前为 stub 骨架。

Phase: 3 (stub — NotImplementedError, disconnect 已实装用于测试)
"""

from __future__ import annotations

from typing import Any


class MultiServerMCPClient:
    """多服务器 MCP 客户端管理。

    管理多个 MCP 服务器连接，支持懒加载和工具动态发现。
    Phase 3 接入 langchain-mcp-adapters 实装。
    """

    def __init__(self):
        self._connections: dict[str, Any] = {}

    async def connect(self, server_name: str, url: str) -> None:
        """连接到 MCP 服务器。

        Args:
            server_name: 服务器名称
            url: 服务器 URL（如 FastGPT mcp_server 地址）

        Raises:
            NotImplementedError: Phase 3 实装
        """
        raise NotImplementedError(f"MultiServerMCPClient.connect: Phase 3 实装。server={server_name}")

    async def disconnect(self, server_name: str) -> None:
        """断开 MCP 服务器连接。"""
        if server_name in self._connections:
            del self._connections[server_name]

    async def list_tools(self, server_name: str) -> list[dict]:
        """列出服务器的可用工具。"""
        raise NotImplementedError(f"MultiServerMCPClient.list_tools: Phase 3 实装。server={server_name}")

    async def call_tool(self, server_name: str, tool_name: str, args: dict) -> Any:
        """调用 MCP 服务器上的工具。"""
        raise NotImplementedError(f"MultiServerMCPClient.call_tool: Phase 3 实装。tool={tool_name}")


# 全局单例
_client: MultiServerMCPClient | None = None


def get_mcp_client() -> MultiServerMCPClient:
    """获取全局 MCP 客户端单例。"""
    global _client
    if _client is None:
        _client = MultiServerMCPClient()
    return _client