# -*- coding: utf-8 -*-
"""MCP 客户端 — 配置驱动多服务器注册表，懒连接，每服务器独立熔断。

- 服务器配置来自 settings.mcp_servers（env 注入 JSON）：
  {"server_name": {"transport": "streamable_http", "url": "...", "api_key_env": "...", "namespace": "search"}}
- 工具经 langchain-mcp-adapters 转 LangChain 工具，按 namespace 前缀注册
  （search/*、image/*、code/*）
- 调用失败 → isError 结构化结果（{code, message}），不抛异常（pi 模式）
- 真连需要凭据；未配置的服务器跳过（测试用假 MCP 服务器）

Phase: 2 (implemented; 真连待凭据)
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from tools.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class McpServerError(Exception):
    """MCP 服务器级错误（连接/调用失败）。"""


class MultiServerMCPClient:
    """多服务器 MCP 客户端管理：懒连接 + 工具发现 + 每服务器熔断。"""

    def __init__(self, servers: dict | None = None):
        self._configs: dict[str, dict] = dict(servers or {})
        self._connections: dict[str, Any] = {}
        self._transports: dict[str, Any] = {}  # streamablehttp/stdio 上下文（须持有引用防 GC）
        self._tools: dict[str, list[Any]] = {}
        self._breakers: dict[str, CircuitBreaker] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    # ── 配置 ──────────────────────────────────────────────────────────
    def register_server(self, name: str, config: dict) -> None:
        """注册（或覆盖）一个 MCP 服务器配置（不建连）。"""
        self._configs[name] = config

    def server_names(self) -> list[str]:
        return list(self._configs.keys())

    def _resolved_url(self, name: str, config: dict) -> str | None:
        url = config.get("url", "")
        if not url:
            return None
        key_env = config.get("api_key_env", "")
        if key_env:
            key = os.getenv(key_env, "")
            if not key:
                # 进程 env 未注入时 fallback 到 settings（.env 由 pydantic 读取）
                try:
                    from config import get_settings

                    key = str(getattr(get_settings(), key_env.lower(), "") or "")
                except Exception:  # noqa: BLE001
                    key = ""
            if key:
                url = url.replace("{key}", key)
        return url

    # ── 连接（懒） ────────────────────────────────────────────────────
    async def connect(self, server_name: str) -> bool:
        """连接到 MCP 服务器（幂等；失败 → 记熔断，不抛）。"""
        config = self._configs.get(server_name)
        if config is None:
            return False
        if server_name in self._connections:
            return True
        lock = self._locks.setdefault(server_name, asyncio.Lock())
        async with lock:
            if server_name in self._connections:
                return True
            transport_type = config.get("transport", "streamable_http")
            url = None
            if transport_type == "stdio":
                # stdio 服务器无 url，要求 command 存在
                if not config.get("command"):
                    logger.info("mcp server skipped (no command): %s", server_name)
                    self._breaker(server_name).record_failure()
                    return False
            else:
                url = self._resolved_url(server_name, config)
                if not url:
                    logger.info("mcp server skipped (no url/key): %s", server_name)
                    self._breaker(server_name).record_failure()
                    return False
            try:
                from mcp import ClientSession

                if transport_type == "stdio":
                    from mcp import StdioServerParameters
                    from mcp.client.stdio import stdio_client

                    # mcp 默认只继承白名单 env（DEFAULT_INHERITED_ENV_VARS），业务凭据
                    # （VOLC_* 等）会被裁剪导致子进程缺失配置——自建 stdio server 可信，
                    # 显式继承完整环境。
                    params = StdioServerParameters(
                        command=config["command"],
                        args=config.get("args", []),
                        env={**os.environ},
                    )
                    transport = stdio_client(params)
                else:
                    from mcp.client.streamable_http import streamablehttp_client

                    transport = streamablehttp_client(url)

                # 必须持有 transport 引用直到会话关闭（async generator 被 GC 会导致
                # anyio cancel scope 跨任务退出崩溃），且在同一任务内进入/退出。
                self._transports[server_name] = transport
                ctx = await transport.__aenter__()
                # stdio_client 返回 (read, write) 二元组；streamablehttp 返回三元组
                read, write = (ctx[0], ctx[1]) if isinstance(ctx, tuple) else (ctx, None)
                session = await ClientSession(read, write).__aenter__()
                await session.initialize()

                from langchain_mcp_adapters.tools import load_mcp_tools

                tools = await load_mcp_tools(session)
                self._connections[server_name] = session
                self._tools[server_name] = tools
                logger.info("mcp connected: %s (%d tools)", server_name, len(tools))
                return True
            except Exception as exc:  # noqa: BLE001
                logger.warning("mcp connect failed: %s (%s)", server_name, exc)
                await self._cleanup_transport(server_name)
                self._breaker(server_name).record_failure()
                return False

    def _breaker(self, server_name: str) -> CircuitBreaker:
        if server_name not in self._breakers:
            self._breakers[server_name] = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
        return self._breakers[server_name]

    # ── 工具发现 ──────────────────────────────────────────────────────
    async def list_tools(self, server_name: str) -> list[dict]:
        """列出服务器可用工具（转 LangChain 工具后的元信息）。"""
        if server_name not in self._tools:
            await self.connect(server_name)
        tools = self._tools.get(server_name, [])
        return [
            {
                "name": f"{self._configs.get(server_name, {}).get('namespace', 'mcp')}/{t.name}",
                "description": getattr(t, "description", "")[:120],
            }
            for t in tools
        ]

    def get_langchain_tools(self, server_name: str) -> list[Any]:
        """已连接服务器的 LangChain 工具列表（namespace 前缀重命名）。"""
        tools = self._tools.get(server_name, [])
        namespace = self._configs.get(server_name, {}).get("namespace", "mcp")
        renamed = []
        for t in tools:
            try:
                t.name = f"{namespace}/{t.name}"
            except Exception:  # noqa: BLE001
                pass
            renamed.append(t)
        return renamed

    # ── 调用 ──────────────────────────────────────────────────────────
    async def call_tool(self, server_name: str, tool_name: str, args: dict) -> Any:
        """调用 MCP 工具；熔断中 → 直接结构化错误；失败 → 结构化错误（不抛）。"""
        if not self._breaker(server_name).can_proceed():
            return {"isError": True, "code": "MCP_CIRCUIT_OPEN", "message": f"服务器 {server_name} 熔断中"}
        if server_name not in self._tools:
            ok = await self.connect(server_name)
            if not ok:
                return {"isError": True, "code": "MCP_NOT_CONNECTED", "message": f"服务器 {server_name} 不可用"}
        tools = self._tools.get(server_name, [])
        for t in tools:
            if t.name == tool_name:
                try:
                    result = await t.ainvoke(args)
                    self._breaker(server_name).record_success()
                    return result
                except Exception as exc:  # noqa: BLE001
                    self._breaker(server_name).record_failure()
                    return {"isError": True, "code": "MCP_CALL_FAILED", "message": str(exc)[:200]}
        return {"isError": True, "code": "MCP_TOOL_NOT_FOUND", "message": f"{tool_name} 未在 {server_name} 发现"}

    async def disconnect(self, server_name: str) -> None:
        """断开 MCP 服务器连接（按序关闭 session → transport）。"""
        session = self._connections.pop(server_name, None)
        if session is not None:
            try:
                await session.__aexit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
        await self._cleanup_transport(server_name)
        self._tools.pop(server_name, None)

    async def _cleanup_transport(self, server_name: str) -> None:
        transport = self._transports.pop(server_name, None)
        if transport is not None:
            try:
                await transport.__aexit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass


# 全局单例
_client: MultiServerMCPClient | None = None


def get_mcp_client() -> MultiServerMCPClient:
    """获取全局 MCP 客户端单例（首次调用从 settings 载入服务器注册表）。"""
    global _client
    if _client is None:
        from config import get_settings

        _client = MultiServerMCPClient(get_settings().mcp_servers)
    return _client


def reset_mcp_client() -> None:
    """重置单例（测试用）。"""
    global _client
    _client = None
