# -*- coding: utf-8 -*-
"""LLM 工厂的 trace 命名契约测试。

保证 LangSmith 中的 run name 是业务名（LLMTaskName），而不是模型类名
ChatOpenAI；且返回类型保持 BaseChatModel 族，deepagents 可正常解析。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.language_models import BaseChatModel

from ai.llm_task_name import LLMTaskName


@pytest.fixture
def llm_settings():
    settings = MagicMock()
    settings.llm_enable_thinking = False
    settings.httpx_verify_ssl = True
    settings.llm_api_key = "test-key"
    settings.llm_base_url = "https://example.invalid/v1"
    settings.llm_model = "test-model"
    with patch("ai.llm_client.get_settings", return_value=settings):
        yield settings


@pytest.mark.unit
def test_build_chat_openai_sets_business_name(llm_settings):
    from ai.llm_client import build_chat_openai

    llm = build_chat_openai(
        temperature=0.1,
        max_tokens=2048,
        task_name=LLMTaskName.MAIN_AGENT_ROUTER,
    )

    assert isinstance(llm, BaseChatModel)
    assert llm.get_name() == LLMTaskName.MAIN_AGENT_ROUTER.value
    assert llm.name == LLMTaskName.MAIN_AGENT_ROUTER.value


@pytest.mark.unit
def test_build_chat_openai_without_task_name_keeps_default(llm_settings):
    from ai.llm_client import build_chat_openai

    llm = build_chat_openai(temperature=0.1, max_tokens=2048)

    assert isinstance(llm, BaseChatModel)
    assert llm.name is None
    assert llm.get_name() == "ChatOpenAI"


@pytest.mark.unit
def test_build_tool_calling_llm_sets_business_name(llm_settings):
    from ai.llm_client import build_tool_calling_llm

    tools = [
        {
            "type": "function",
            "function": {
                "name": "f",
                "description": "d",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    bound = build_tool_calling_llm(
        tools,
        task_name=LLMTaskName.REACT_ORCHESTRATOR,
    )

    assert bound.get_name() == LLMTaskName.REACT_ORCHESTRATOR.value
