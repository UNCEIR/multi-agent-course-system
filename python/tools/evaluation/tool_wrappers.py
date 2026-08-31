# -*- coding: utf-8 -*-
"""evaluation 三函数的 @tool 薄壳（供 ToolRegistry / chat subagent 委派使用）。

- 只暴露数据入参（snapshot/dimensions/radar/comment_type）；
  llm/on_token/timeout_seconds 为运行时注入参数，不进 Pydantic schema。
- 薄壳内部构造各自 LLM（LLMTaskName 命名）并转调原函数，行为与
  agent/evaluation/service.py 的直调路径一致（service 仍直调原函数，不受影响）。
- generate_comment 薄壳不支撑 on_token 流式回调（透传 None）。
"""

from __future__ import annotations

import json

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from .compute_radar_values import compute_radar_values as _compute_radar_values
from .design_dimensions import design_dimensions as _design_dimensions
from .generate_comment import generate_comment as _generate_comment


class DesignDimensionsInput(BaseModel):
    """design_dimensions 工具输入（数据入参，不含 LLM/超时等运行时注入）。"""
    snapshot: dict = Field(..., description="成绩单快照（含 derived 派生统计，来自 get_academic_snapshot）")


class ComputeRadarValuesInput(BaseModel):
    """compute_radar_values 工具输入。"""
    dimensions: list[dict] = Field(..., description="维度提案列表（含 name/weight/metric/rationale）")
    snapshot: dict = Field(..., description="成绩单快照（含 derived 派生统计）")


class GenerateCommentInput(BaseModel):
    """generate_comment 工具输入。"""
    snapshot: dict = Field(..., description="成绩单快照（含 derived 派生统计）")
    radar: dict = Field(..., description="雷达计算结果（values/rejected）")
    comment_type: str = Field(
        ...,
        description="评语类型：semester_summary / encouragement / improvement_advice / recommendation",
    )


@tool(args_schema=DesignDimensionsInput)
async def design_dimensions(snapshot: dict) -> str:
    """设计评价维度提案（LLM 提议 + Pydantic 硬校验 + 默认维度集兜底）。"""
    result = await _design_dimensions(snapshot)
    return json.dumps(result, ensure_ascii=False)


@tool(args_schema=ComputeRadarValuesInput)
def compute_radar_values(dimensions: list[dict], snapshot: dict) -> str:
    """按维度提案确定性计算雷达数值（代码算值，手算可核对）。"""
    result = _compute_radar_values(dimensions, snapshot)
    return json.dumps(result, ensure_ascii=False)


@tool(args_schema=GenerateCommentInput)
async def generate_comment(snapshot: dict, radar: dict, comment_type: str) -> str:
    """生成评语（数值引用核验硬闸 + 规则化兜底，绝不空返回）。"""
    comment, status, usage = await _generate_comment(snapshot, radar, comment_type)
    return json.dumps(
        {"comment": comment, "status": status, "usage": usage},
        ensure_ascii=False,
    )