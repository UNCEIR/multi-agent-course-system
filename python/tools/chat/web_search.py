# -*- coding: utf-8 -*-
"""网页搜索 tool — 使用 tavily 搜索引擎获取实时信息。

Phase 3 实装完整功能，当前为 stub 骨架。

Phase: 3 (stub — NotImplementedError)
"""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class WebSearchInput(BaseModel):
    """web_search 工具输入参数。"""
    query: str = Field(..., description="搜索关键词", min_length=1, max_length=500)
    max_results: int = Field(default=5, description="返回结果数量", ge=1, le=20)


@tool(args_schema=WebSearchInput)
def web_search(query: str, max_results: int = 5) -> str:
    """搜索互联网获取实时信息。

    Args:
        query: 搜索关键词
        max_results: 返回结果数量（默认 5）

    Returns:
        搜索结果摘要文本
    """
    raise NotImplementedError(
        f"web_search: Phase 3 实装 tavily 搜索。\n查询：{query}，最大结果：{max_results}"
    )