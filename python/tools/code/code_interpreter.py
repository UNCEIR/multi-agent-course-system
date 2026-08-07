# -*- coding: utf-8 -*-
"""编程插件 tool 骨架 — 沙箱执行/代码生成。

Phase 3/4 实装完整功能，当前为 stub 骨架。

Phase: 3/4 (stub — NotImplementedError)
"""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class CodeInterpreterInput(BaseModel):
    """code_interpreter 工具输入参数。"""
    code: str = Field(..., description="要执行的代码", min_length=1, max_length=10000)
    language: str = Field(default="python", description="编程语言（python、javascript、bash 等）")
    timeout_seconds: int = Field(default=30, description="执行超时时间（秒）", ge=1, le=300)


@tool(args_schema=CodeInterpreterInput)
def code_interpreter(
    code: str,
    language: str = "python",
    timeout_seconds: int = 30,
) -> str:
    """在沙箱环境中执行代码并返回结果。

    Args:
        code: 要执行的代码
        language: 编程语言（python、javascript、bash 等）
        timeout_seconds: 执行超时时间（秒）

    Returns:
        代码执行结果（stdout/stderr）
    """
    raise NotImplementedError(
        f"code_interpreter: Phase 3/4 实装沙箱执行环境。\n语言：{language}"
    )