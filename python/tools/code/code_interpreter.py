# -*- coding: utf-8 -*-
"""代码执行 tool — E2B 自建 MCP server 主路（code/* namespace）+ 本地受限沙箱兜底。

e2b stdio server（tools/code/e2b_mcp_server.py，e2b Python SDK 内核）→ 真实云沙箱执行；
MCP 熔断/不可达 → 本地 Docker 受限沙箱（超时 kill）→ 双失败 → 结构化 error。
"""

from __future__ import annotations

import asyncio
import json
import logging

from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CodeInterpreterInput(BaseModel):
    """code_interpreter 工具输入参数。"""
    language: str = Field(default="python", description="编程语言（python/javascript/bash 等）")
    code: str = Field(..., description="要执行的代码", min_length=1, max_length=8000)
    timeout: int = Field(default=30, description="超时秒数", ge=1, le=120)


async def _local_sandbox(language: str, code: str, timeout: int) -> dict:
    """本地受限执行兜底：Docker 单容器、内存限制、超时 kill。"""
    import subprocess

    image = {"python": "python:3.12-slim", "javascript": "node:20-slim", "bash": "bash:5"}.get(language, "python:3.12-slim")
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "run",
            "--rm",
            "--memory=256m",
            "--cpus=1",
            "--network=none",
            image,
            "sh",
            "-c",
            code if language == "bash" else (f"python -c {json.dumps(code)}" if language == "python" else f"node -e {json.dumps(code)}"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return {"isError": True, "code": "SANDBOX_TIMEOUT", "message": f"执行超时（>{timeout}s）"}
        return {
            "stdout": stdout.decode(errors="replace")[:4000],
            "stderr": stderr.decode(errors="replace")[:2000],
            "exit_code": proc.returncode,
            "source": "local-sandbox",
        }
    except FileNotFoundError:
        return {"isError": True, "code": "DOCKER_UNAVAILABLE", "message": "本地沙箱依赖 docker"}
    except Exception as exc:  # noqa: BLE001
        return {"isError": True, "code": "SANDBOX_FAILED", "message": str(exc)[:200]}


@tool(args_schema=CodeInterpreterInput)
async def code_interpreter(language: str = "python", code: str = "", timeout: int = 30) -> str:
    """在隔离沙箱中执行代码并返回 stdout/stderr（E2B 云沙箱主路 → 本地 Docker 兜底）。

    适合统计/脚本/数值计算等确定性任务。一次调用应包含完整逻辑（含造数据与输出），
    拿到结果后直接向用户总结，无需重复执行。"""
    from tools.mcp_client import get_mcp_client

    client = get_mcp_client()
    result = await client.call_tool("e2b", "execute_code", {"language": language, "code": code, "timeout": timeout})
    if isinstance(result, dict) and result.get("isError"):
        logger.info("e2b MCP failed (%s), fallback local sandbox", result.get("code"))
        result = await _local_sandbox(language, code, timeout)
    return json.dumps(result, ensure_ascii=False)[:6000]
