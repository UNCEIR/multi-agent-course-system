# -*- coding: utf-8 -*-
"""脑图生成 tool 骨架 — 文本→思维导图 DSL→渲染。

Phase 3/4 实装完整功能，当前为 stub 骨架。

Phase: 3/4 (stub — NotImplementedError)
"""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class MindmapGeneratorInput(BaseModel):
    """mindmap_generator 工具输入参数。"""
    topic: str = Field(..., description="思维导图中心主题", min_length=1, max_length=200)
    nodes: list[dict] | None = Field(default=None, description="节点列表（可选，留空则自动生成），格式：[{'label': '节点名', 'children': [...]}]")
    format: str = Field(default="markdown", description="输出格式（markdown、json、svg 等）")


@tool(args_schema=MindmapGeneratorInput)
def mindmap_generator(
    topic: str,
    nodes: list[dict] | None = None,
    format: str = "markdown",
) -> str:
    """根据主题生成思维导图。

    Args:
        topic: 思维导图中心主题
        nodes: 节点列表（可选，留空则自动生成），格式：[{"label": "节点名", "children": [...]}]
        format: 输出格式（markdown、json、svg 等）

    Returns:
        思维导图数据（markdown 大纲或可渲染的 DSL）
    """
    raise NotImplementedError(
        f"mindmap_generator: Phase 3/4 实装思维导图渲染。\n主题：{topic}"
    )