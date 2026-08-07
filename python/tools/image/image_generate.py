# -*- coding: utf-8 -*-
"""图片生成 tool — 经 MCP 调用图片生成服务。

独立 Page 组件（ImageGeneratePage）使用，需要画布/参数配置等深度交互。
Phase 3 实装完整功能，当前为 stub 骨架。

Phase: 3 (stub — NotImplementedError)
"""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class ImageGenerateInput(BaseModel):
    """image_generate 工具输入参数。"""
    prompt: str = Field(..., description="图片描述文本", min_length=1, max_length=2000)
    style: str = Field(default="写实", description="图片风格（写实、卡通、水彩、油画、扁平化等）")
    width: int = Field(default=1024, description="图片宽度（像素）", ge=256, le=4096)
    height: int = Field(default=768, description="图片高度（像素）", ge=256, le=4096)


@tool(args_schema=ImageGenerateInput)
def image_generate(
    prompt: str,
    style: str = "写实",
    width: int = 1024,
    height: int = 768,
) -> str:
    """根据文本描述生成图片。

    Args:
        prompt: 图片描述文本
        style: 图片风格（写实、卡通、水彩、油画、扁平化等）
        width: 图片宽度（像素）
        height: 图片高度（像素）

    Returns:
        生成图片的 URL 或 base64 数据
    """
    raise NotImplementedError(
        f"image_generate: Phase 3 实装 MCP 图片生成服务。\n提示词：{prompt}，风格：{style}"
    )