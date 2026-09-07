# -*- coding: utf-8 -*-
"""业务场景 Agent 工厂入口。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

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


async def build_business_subagents() -> list[dict]:
    """预编译全部业务子 agent，组装成 deepagents CompiledSubAgent 列表。

    每个子 agent 由 build_deep_agent(spec) 完整装配：spec.skills（自己的
    SKILL.md 渐进加载）+ spec.allowed_tools（业务工具白名单）+ ToolHooks/
    Summarization 横切。挂到 main_agent 后，主 agent 获得 task() 委派工具，
    report/evaluation/recommend/ppt 意图可委派子 agent 按 SKILL.md 流程真实执行。
    """
    from agent.main.specs import (
        EVALUATION_AGENT_SPEC,
        PPT_AGENT_SPEC,
        RECOMMENDATION_AGENT_SPEC,
        REPORT_AGENT_SPEC,
    )

    builds = (
        (RECOMMENDATION_AGENT_SPEC, build_recommendation_agent),
        (REPORT_AGENT_SPEC, build_report_agent),
        (EVALUATION_AGENT_SPEC, build_evaluation_agent),
        (PPT_AGENT_SPEC, build_ppt_agent),
    )
    compiled: list[dict] = []
    for spec, factory in builds:
        try:
            runnable = await factory()
        except Exception as exc:  # noqa: BLE001
            # 单个子 agent 编译失败只告警跳过，不拖垮 main_agent 启动
            logger.warning("build_business_subagents.skipped", name=spec.name, error=str(exc)[:200])
            continue
        compiled.append(
            {
                "name": spec.name,
                "description": spec.description,
                "runnable": runnable,
            }
        )
    return compiled
