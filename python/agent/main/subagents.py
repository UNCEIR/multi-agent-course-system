# -*- coding: utf-8 -*-
"""业务场景 Agent 工厂入口。"""

from __future__ import annotations

from typing import Any

from .factory import build_deep_agent
from .specs import (
    EVALUATION_AGENT_SPEC,
    PPT_AGENT_SPEC,
    RECOMMENDATION_AGENT_SPEC,
    REPORT_AGENT_SPEC,
)


async def build_recommendation_agent(tools: list[Any] | None = None):
    """创建课程推荐场景 Agent。"""
    return await build_deep_agent(RECOMMENDATION_AGENT_SPEC, tools=tools)


async def build_report_agent(tools: list[Any] | None = None):
    """创建成绩报告场景 Agent。"""
    return await build_deep_agent(REPORT_AGENT_SPEC, tools=tools)


async def build_evaluation_agent(tools: list[Any] | None = None):
    """创建评价寄语场景 Agent。"""
    return await build_deep_agent(EVALUATION_AGENT_SPEC, tools=tools)


async def build_ppt_agent(tools: list[Any] | None = None):
    """创建课程小组 PPT 场景 Agent。"""
    return await build_deep_agent(PPT_AGENT_SPEC, tools=tools)


# 旧名称保留为显式别名，避免调用方把 evaluation 场景误认为通用 subagent。
build_report_subagent = build_report_agent
