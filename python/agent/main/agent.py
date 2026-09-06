# -*- coding: utf-8 -*-
"""主 Agent 场景入口，具体装配统一委托给 deepagent 工厂。"""

from __future__ import annotations

from typing import Any

from .factory import build_deep_agent
from .specs import MAIN_AGENT_SPEC


async def build_main_agent(tools: list[Any] | None = None, subagents: list[dict] | None = None):
    """创建统一对话入口 Agent；subagents 为可委派的业务子 agent（CompiledSubAgent）。"""
    return await build_deep_agent(MAIN_AGENT_SPEC, tools=tools, subagents=subagents)
