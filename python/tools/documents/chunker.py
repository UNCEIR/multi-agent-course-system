# -*- coding: utf-8 -*-
"""文档分块 tool — 文本分块与向量化。

支持多种分块策略（按段落/按 token 数/语义分块），
对比 v1 的 4 块策略（basic/schedule_capacity/learning_profile/audience_tags）。
Phase 1 实装完整功能。

Phase: 1 (stub — NotImplementedError)
"""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class ChunkDocumentInput(BaseModel):
    """chunk_document 工具输入参数。"""
    text: str = Field(..., description="文档文本内容", min_length=1)
    chunk_size: int = Field(default=500, description="每块目标大小（字符数或 token 数，取决于 strategy）", ge=50, le=2000)
    chunk_overlap: int = Field(default=50, description="块间重叠大小", ge=0, le=500)
    strategy: str = Field(default="paragraph", description="分块策略（paragraph、token、semantic）")


@tool(args_schema=ChunkDocumentInput)
def chunk_document(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    strategy: str = "paragraph",
) -> list[dict]:
    """将文档文本分块。

    Args:
        text: 文档文本内容
        chunk_size: 每块目标大小（字符数或 token 数，取决于 strategy）
        chunk_overlap: 块间重叠大小
        strategy: 分块策略（paragraph、token、semantic）

    Returns:
        分块列表，每块包含 text 和 metadata
    """
    raise NotImplementedError(
        f"chunk_document: Phase 1 实装。\n策略：{strategy}，块大小：{chunk_size}"
    )