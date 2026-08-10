# -*- coding: utf-8 -*-
"""统一 deepagent 工厂的架构契约测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def factory_settings():
    settings = MagicMock()
    settings.agent_compaction_trigger_messages = 8
    settings.agent_context_window_tokens = 128000
    settings.agent_compaction_keep_tokens = 20000
    with patch("agent.main.factory.get_settings", return_value=settings):
        yield settings


@pytest.mark.asyncio
async def test_shared_factory_loads_scenario_context(factory_settings):
    from agent.main.factory import build_deep_agent
    from agent.main.specs import REPORT_AGENT_SPEC

    backend = MagicMock()
    checkpointer = MagicMock()
    llm = MagicMock()
    compiled_agent = MagicMock()
    tools = [MagicMock(name="compute_weighted_grade")]

    with (
        patch("agent.main.factory.build_agent_backend", return_value=backend),
        patch("agent.main.factory.build_checkpointer", new_callable=AsyncMock, return_value=checkpointer),
        patch("agent.main.factory.build_chat_openai", return_value=llm) as build_llm,
        patch("agent.main.factory.create_deep_agent", return_value=compiled_agent) as create_agent,
    ):
        result = await build_deep_agent(REPORT_AGENT_SPEC, tools=tools)

    assert result is compiled_agent.with_config.return_value
    kwargs = create_agent.call_args.kwargs
    assert kwargs["backend"] is backend
    assert kwargs["checkpointer"] is checkpointer
    assert kwargs["tools"] == tools
    assert kwargs["skills"] == ["/skills/report-generation/"]
    assert kwargs["memory"] == []
    assert kwargs["system_prompt"] == REPORT_AGENT_SPEC.system_prompt
    assert build_llm.call_args.kwargs["task_name"] == REPORT_AGENT_SPEC.task_name
    assert compiled_agent.with_config.call_args.kwargs["run_name"] == REPORT_AGENT_SPEC.task_name.value


@pytest.mark.asyncio
async def test_main_agent_is_a_thin_scenario_entrypoint():
    from agent.main.agent import build_main_agent
    from agent.main.specs import MAIN_AGENT_SPEC

    compiled_agent = MagicMock()
    tools = [MagicMock()]
    with patch("agent.main.agent.build_deep_agent", new_callable=AsyncMock, return_value=compiled_agent) as build:
        result = await build_main_agent(tools=tools)

    assert result is compiled_agent
    build.assert_awaited_once_with(MAIN_AGENT_SPEC, tools=tools)


@pytest.mark.asyncio
async def test_factory_passes_streaming_flag_to_llm(factory_settings):
    """chat/stream 依赖 LLM 的 streaming=True 透出 on_chat_model_stream token 事件。

    回归：此前主 agent LLM 用默认 streaming=False，deepagents 按 stream_mode=updates
    聚合后 chat/stream 永远只能产出空的 done 事件（空回复）。
    """
    from agent.main.factory import build_deep_agent
    from agent.main.specs import MAIN_AGENT_SPEC

    backend = MagicMock()
    checkpointer = MagicMock()
    llm = MagicMock()
    compiled_agent = MagicMock()
    tools = [MagicMock()]

    with (
        patch("agent.main.factory.build_agent_backend", return_value=backend),
        patch("agent.main.factory.build_checkpointer", new_callable=AsyncMock, return_value=checkpointer),
        patch("agent.main.factory.build_chat_openai", return_value=llm) as build_llm,
        patch("agent.main.factory.create_deep_agent", return_value=compiled_agent),
    ):
        await build_deep_agent(MAIN_AGENT_SPEC, tools=tools)

    assert build_llm.call_args.kwargs["streaming"] is True
    assert MAIN_AGENT_SPEC.streaming is True
