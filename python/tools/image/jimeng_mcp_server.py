# -*- coding: utf-8 -*-
"""即梦 4.0 自建 MCP server（stdio）— 将火山引擎异步任务 API 封装为 MCP 工具。

暴露两个工具（两段式链式调用，image/* namespace）：
- generate_image_submit：提交任务 → {task_id, status}
- generate_image_get：查询任务 → {status, image_urls?, next_poll_after_seconds, attempts_left}

启动：python -m tools.image.jimeng_mcp_server
注册（settings.mcp_servers）：
  {"jimeng": {"transport": "stdio", "command": "python",
              "args": ["-m", "tools.image.jimeng_mcp_server"], "namespace": "image"}}

Phase: 2 (implemented)
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult

from tools.image import jimeng_client


def _tools() -> list[Tool]:
    return [
        Tool(
            name="generate_image_submit",
            description=(
                "提交即梦 4.0 文生图/图生图任务，返回 task_id（异步，需后续调用 "
                "generate_image_get 查询）。组图场景 prompt 需明确 1-3 张；"
                "force_single=false 时由模型智能决定组图数量。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "提示词（≤800 字符，中英文均可）"},
                    "size": {"type": "integer", "description": "面积（默认 2048*2048=2K）"},
                    "width": {"type": "integer", "description": "宽（需与 height 同时传）"},
                    "height": {"type": "integer", "description": "高（需与 width 同时传）"},
                    "scale": {"type": "number", "description": "文本影响程度 0-1（默认 0.7）"},
                    "force_single": {"type": "boolean", "description": "是否强制单图（默认 false 智能组图）"},
                    "image_urls": {"type": "array", "items": {"type": "string"}, "description": "参考图 URL（0-10 张，图生图）"},
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="generate_image_get",
            description=(
                "查询即梦 4.0 生成任务状态：in_queue/generating/done/not_found/expired。"
                "done 时返回 image_urls（24h 有效）；未完成时返回 next_poll_after_seconds 建议等待后重查。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "提交任务返回的 task_id"},
                    "attempt": {"type": "integer", "description": "当前查询次数（从 1 起，用于退避计算）"},
                },
                "required": ["task_id"],
            },
        ),
    ]


async def _handle_submit(args: dict) -> dict:
    try:
        task_id = jimeng_client.submit_task(
            prompt=str(args["prompt"]),
            size=args.get("size"),
            width=args.get("width"),
            height=args.get("height"),
            scale=args.get("scale"),
            force_single=args.get("force_single"),
            image_urls=args.get("image_urls"),
        )
        return {"task_id": task_id, "status": "in_queue"}
    except jimeng_client.JimengError as exc:
        return {"isError": True, "code": f"JIMENG_{exc.code}", "message": exc.message,
                "retryable": exc.retryable, "request_id": exc.request_id}


async def _handle_get(args: dict) -> dict:
    task_id = str(args["task_id"])
    attempt = int(args.get("attempt", 1))
    from config import get_settings

    s = get_settings()
    try:
        # 内置退避等待：本次调用 ≈ 一次有效查询（避免 agent 忙轮询）
        if attempt > 1:
            await asyncio.sleep(jimeng_client.poll_interval(attempt - 1))
        result = jimeng_client.query_task(task_id)
        status = result["status"]
        if status == "done":
            return {
                "status": "done",
                "image_urls": result["image_urls"],
                "binary_data_base64": result["binary_data_base64"],
                "next_poll_after_seconds": 0,
                "attempts_left": 0,
            }
        if status in ("not_found", "expired"):
            return {"status": status, "image_urls": [], "next_poll_after_seconds": 0,
                    "attempts_left": 0, "message": f"任务 {status}，请重新提交"}
        # in_queue / generating
        interval = jimeng_client.poll_interval(attempt)
        attempts_left = max(0, s.jimeng_poll_max_attempts - attempt)
        return {"status": status, "image_urls": [], "next_poll_after_seconds": interval, "attempts_left": attempts_left}
    except jimeng_client.JimengError as exc:
        return {"isError": True, "code": f"JIMENG_{exc.code}", "message": exc.message,
                "retryable": exc.retryable, "request_id": exc.request_id}


async def main() -> None:
    server = Server("jimeng-server")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return _tools()

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> CallToolResult:
        args = arguments or {}
        if name == "generate_image_submit":
            payload = await _handle_submit(args)
        elif name == "generate_image_get":
            payload = await _handle_get(args)
        else:
            payload = {"isError": True, "code": "TOOL_NOT_FOUND", "message": f"未知工具 {name}"}
        import json as _json

        return CallToolResult(content=[TextContent(type="text", text=_json.dumps(payload, ensure_ascii=False))])

    async with stdio_server() as (read, write):
        from mcp.server.models import InitializationOptions

        await server.run(
            read,
            write,
            InitializationOptions(
                server_name="jimeng-server",
                server_version="0.1.0",
                capabilities={"tools": {}},
            ),
        )


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
