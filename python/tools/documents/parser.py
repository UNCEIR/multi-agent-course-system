# -*- coding: utf-8 -*-
"""文档解析 tool — PDF/doc 文件解析兜底。

FastGPT KB 不可用/特定格式时使用 Python 本地解析。
Phase 1 实装完整功能。

Phase: 1 (stub — NotImplementedError)
"""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class ParseDocumentInput(BaseModel):
    """parse_document 工具输入参数。"""
    file_path: str = Field(..., description="文件路径", min_length=1, max_length=1024)
    file_type: str = Field(default="auto", description="文件类型（auto、pdf、docx、csv），auto 自动检测")


@tool(args_schema=ParseDocumentInput)
def parse_document(file_path: str, file_type: str = "auto") -> str:
    """解析文档文件内容。

    Args:
        file_path: 文件路径
        file_type: 文件类型（auto、pdf、docx、csv），auto 自动检测

    Returns:
        提取的文本内容
    """
    raise NotImplementedError(
        f"parse_document: Phase 1 实装。\n文件：{file_path}，类型：{file_type}"
    )