# -*- coding: utf-8 -*-
"""E2B 代码执行自建 MCP server（stdio）— e2b Python SDK 内核封装为 MCP 工具。

暴露 execute_code（code/* namespace）：
- execute_code：{language, code, timeout} → {stdout, stderr, exit_code, source:"e2b"}，失败 isError 结构化

启动：python -m tools.code.e2b_mcp_server
注册（settings.mcp_servers）：
  {"e2b": {"transport": "stdio", "command": "python",
           "args": ["-m", "tools.code.e2b_mcp_server"], "namespace": "code"}}
凭据：容器 env 注入 E2B_API_KEY（mcp_client stdio 继承完整环境）

Phase: 2 (implemented)
"""

from __future__ import annotations

import asyncio
import json
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult

from tools.code.e2b_sandbox import run_code


def _tools() -> list[Tool]:
    return [
        Tool(
            name="execute_code",
            description=(
                "在 E2B 云沙箱中执行代码并返回 stdout/stderr/exit_code（source=e2b）。"
                "支持 python（python3 -c）、javascript（node -e）、bash（sh -c）。"
                "完整 Linux 环境，可联网；适合统计、脚本、算数等确定性执行。"
                "注意：一次执行应覆盖完整任务（含数据构造与输出），拿到结果后直接总结作答，不要反复执行同一段逻辑。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "language": {"type": "string", "description": "编程语言（python/javascript/bash，默认 python）"},
                    "code": {"type": "string", "description": "要执行的代码（≤8000 字符）"},
                    "timeout": {"type": "integer", "description": "超时秒数（1-120，默认 30）"},
                },
                "required": ["code"],
            },
        ),
    ]


async def main() -> None:
    server = Server("e2b-server")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return _tools()

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> CallToolResult:
        args = arguments or {}
        if name == "execute_code":
            payload = await run_code(
                language=str(args.get("language", "python")),
                code=str(args.get("code", "")),
                timeout=int(args.get("timeout", 30)),
            )
        else:
            payload = {"isError": True, "code": "TOOL_NOT_FOUND", "message": f"未知工具 {name}"}
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))])

    async with stdio_server() as (read, write):
        from mcp.server.models import InitializationOptions

        await server.run(
            read,
            write,
            InitializationOptions(
                server_name="e2b-server",
                server_version="0.1.0",
                capabilities={"tools": {}},
            ),
        )


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
