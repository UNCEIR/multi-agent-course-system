# -*- coding: utf-8 -*-
"""统一 deepagent 工厂。

业务模块只声明 AgentSpec，不重复组装 deepagents middleware、backend 和
checkpointer。这样每个场景可以拥有自己的 skills、memory 和 tool allowlist。
"""

from __future__ import annotations

from typing import Any

import structlog
from deepagents import create_deep_agent
from deepagents.middleware.summarization import (
    SummarizationMiddleware,
    SummarizationToolMiddleware,
)

from ai.llm_client import build_chat_openai
from config import get_settings

from .backend import build_agent_backend
from .checkpointer import build_checkpointer
from .specs import AgentSpec

logger = structlog.get_logger()


async def build_deep_agent(
    spec: AgentSpec,
    *,
    tools: list[Any] | None = None,
):
    """按业务规格创建一个 deepagent。"""
    settings = get_settings()
    backend = build_agent_backend()
    checkpointer = await build_checkpointer()

    # build_chat_openai 通过 pydantic 的 name 字段命名 trace，保持 BaseChatModel
    # 类型，deepagents 可正常解析；LangSmith 中 LLM run 显示 spec.task_name。
    llm = build_chat_openai(
        temperature=spec.temperature,
        max_tokens=spec.max_tokens,
        streaming=spec.streaming,
        task_name=spec.task_name,
    )

    if tools is None:
        from agent import runtime

        registry = runtime.tool_registry
        if registry is None:
            tools = []
        elif spec.allowed_tools:
            tools = registry.get_all(allowed=list(spec.allowed_tools))
        else:
            tools = registry.get_all()

    middleware: list[Any] = []
    if spec.enable_compaction:
        trigger = (
            ("messages", settings.agent_compaction_trigger_messages)
            if settings.agent_compaction_trigger_messages
            else ("tokens", settings.agent_context_window_tokens - 13000)
        )
        summarization = SummarizationMiddleware(
            model=llm,
            backend=backend,
            trigger=trigger,
            keep=("tokens", settings.agent_compaction_keep_tokens),
        )
        middleware = [summarization, SummarizationToolMiddleware(summarization)]

    logger.info(
        "build_deep_agent",
        agent_name=spec.name,
        task_name=spec.task_name.value,
        tool_count=len(tools),
        skills=list(spec.skills),
        memory=list(spec.memory),
    )

    agent = create_deep_agent(
        model=llm,
        tools=tools,
        backend=backend,
        skills=list(spec.skills),
        memory=list(spec.memory),
        checkpointer=checkpointer,
        system_prompt=spec.system_prompt,
        middleware=middleware,

    )

    # 外层 agent run 也以业务名标识（图级别的 trace 根节点），LLM 层的
    # run 名由 build_chat_openai 的 name 字段承载，两层在 LangSmith 中一致。
    if spec.task_name:
        return agent.with_config(run_name=spec.task_name.value)

    return agent
