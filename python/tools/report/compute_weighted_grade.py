# -*- coding: utf-8 -*-
"""加权成绩统计 tool — 复合加权计算。

展示性评价 × 30% + 考试性评价 × 70%。
Phase 2 实装完整功能，当前为 stub 骨架。

Phase: 2 (stub — NotImplementedError)
"""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class ComputeWeightedGradeInput(BaseModel):
    """compute_weighted_grade 工具输入参数。"""
    display_eval: float = Field(..., description="展示性评价分数", ge=0, le=100)
    exam_eval: float = Field(..., description="考试性评价分数", ge=0, le=100)
    bonus: float = Field(default=0.0, description="额外加分（如平时分奖励）", ge=0, le=20)


@tool(args_schema=ComputeWeightedGradeInput)
def compute_weighted_grade(
    display_eval: float,
    exam_eval: float,
    bonus: float = 0.0,
) -> dict:
    """计算加权期末总评。

    公式：总评 = display_eval × 0.3 + exam_eval × 0.7 + bonus

    Args:
        display_eval: 展示性评价分数（0-100）
        exam_eval: 考试性评价分数（0-100）
        bonus: 额外加分（默认 0，如平时分奖励）

    Returns:
        包含 total、display_weighted、exam_weighted、bonus 的字典
    """
    # Phase 2 实装完整逻辑
    raise NotImplementedError(
        f"compute_weighted_grade: Phase 2 实装。\n"
        f"展示性评价：{display_eval}，考试性评价：{exam_eval}，加分：{bonus}"
    )