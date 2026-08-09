# -*- coding: utf-8 -*-
"""主 Agent 场景入口，具体装配统一委托给 deepagent 工厂。"""

from __future__ import annotations

from typing import Any

from .factory import build_deep_agent
from .specs import MAIN_AGENT_SPEC


async def build_main_agent(tools: list[Any] | None = None):
    """创建统一对话入口 Agent。"""
    return await build_deep_agent(MAIN_AGENT_SPEC, tools=tools)
