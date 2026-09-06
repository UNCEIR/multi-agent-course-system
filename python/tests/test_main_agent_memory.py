# -*- coding: utf-8 -*-
"""主 Agent 当前工厂契约与记忆资源测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_settings(tmp_path):
    settings = MagicMock()
    settings.memory_dir = ""
    settings.skills_dir = ""
    settings.checkpoint_sqlite_path = str(tmp_path / "checkpoint.db")
    settings.agent_context_window_tokens = 128000
    settings.agent_compaction_trigger_tokens = None
    settings.agent_compaction_keep_tokens = 20000
    settings.agent_compaction_trigger_messages = 8
    with patch("agent.main.factory.get_settings", return_value=settings):
        yield settings


@pytest.mark.asyncio
async def test_main_agent_delegates_to_shared_factory():
    from agent.main.agent import build_main_agent
    from agent.main.specs import MAIN_AGENT_SPEC

    compiled = MagicMock()
    with patch("agent.main.agent.build_deep_agent", new_callable=AsyncMock, return_value=compiled) as build:
        result = await build_main_agent(tools=[])

    assert result is compiled
    build.assert_awaited_once_with(MAIN_AGENT_SPEC, tools=[], subagents=None)


@pytest.mark.asyncio
async def test_scenario_builders_share_factory():
    from agent.main.specs import (
        EVALUATION_AGENT_SPEC,
        PPT_AGENT_SPEC,
        RECOMMENDATION_AGENT_SPEC,
        REPORT_AGENT_SPEC,
    )
    from agent.main import subagents

    with patch("agent.main.subagents.build_deep_agent", new_callable=AsyncMock) as build:
        await subagents.build_recommendation_agent(tools=[])
        await subagents.build_report_agent(tools=[])
        await subagents.build_evaluation_agent(tools=[])
        await subagents.build_ppt_agent(tools=[])

    assert [call.args[0] for call in build.await_args_list] == [
        RECOMMENDATION_AGENT_SPEC,
        REPORT_AGENT_SPEC,
        EVALUATION_AGENT_SPEC,
        PPT_AGENT_SPEC,
    ]


def test_main_agent_prompt_and_memory_seed_exist():
    from agent.main.prompt import MAIN_AGENT_SYSTEM_PROMPT

    repo_root = Path(__file__).resolve().parents[2]
    memory_file = repo_root / "python" / "memories" / "AGENTS.md"
    assert "课程推荐" in MAIN_AGENT_SYSTEM_PROMPT
    assert memory_file.is_file()
    assert "大学校园多智能体平台" in memory_file.read_text(encoding="utf-8")


def test_all_scenario_specs_have_isolated_context():
    from agent.main.specs import (
        EVALUATION_AGENT_SPEC,
        MAIN_AGENT_SPEC,
        PPT_AGENT_SPEC,
        RECOMMENDATION_AGENT_SPEC,
        REPORT_AGENT_SPEC,
    )

    specs = [
        MAIN_AGENT_SPEC,
        RECOMMENDATION_AGENT_SPEC,
        REPORT_AGENT_SPEC,
        EVALUATION_AGENT_SPEC,
        PPT_AGENT_SPEC,
    ]
    assert len({spec.name for spec in specs}) == len(specs)
    assert all(spec.system_prompt for spec in specs)
    assert all(spec.skills for spec in specs)
