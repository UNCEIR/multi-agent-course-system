# -*- coding: utf-8 -*-
"""论文写作 tool — 在 main agent 对话框中协作完成论文写作。

支持多体裁/多风格写作（课程论文、实验报告、综述、读后感等）。
在 chat 对话框中自然交互：用户提出写作需求 → main agent 识别意图 → 调用本 tool。

Phase: 1 (stub — NotImplementedError)
"""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class WritingAssistantInput(BaseModel):
    """writing_assistant 工具输入参数。"""
    topic: str = Field(..., description="论文主题或标题", min_length=1, max_length=500)
    genre: str = Field(default="课程论文", description="写作体裁（课程论文、实验报告、文献综述、读后感、调研报告、开题报告等）")
    outline: str = Field(default="", description="论文大纲（可选，留空则自动生成）", max_length=2000)
    word_count: int = Field(default=1500, description="目标字数（约数）", ge=100, le=50000)


@tool(args_schema=WritingAssistantInput)
def writing_assistant(
    topic: str,
    genre: str = "课程论文",
    outline: str = "",
    word_count: int = 1500,
) -> str:
    """论文写作助手 — 根据主题和体裁生成论文内容。

    Args:
        topic: 论文主题或标题
        genre: 写作体裁（课程论文、实验报告、文献综述、读后感、调研报告、开题报告等）
        outline: 论文大纲（可选，留空则自动生成）
        word_count: 目标字数（约数）

    Returns:
        生成的论文内容 markdown 文本
    """
    # 当前为 stub 实现，Phase 1 后续接入 LLM 驱动
    # 实际实现将调用 LLM 生成完整论文，支持多轮协作修改
    raise NotImplementedError(
        f"writing_assistant: Phase 1 实装 LLM 驱动。\n"
        f"主题：{topic}\n体裁：{genre}\n大纲：{outline or '自动生成'}\n目标字数：{word_count}"
    )