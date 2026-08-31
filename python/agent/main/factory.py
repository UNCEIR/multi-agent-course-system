# -*- coding: utf-8 -*-
"""统一 deepagent 工厂。

业务模块只声明 AgentSpec，不重复组装 deepagents middleware、backend 和
checkpointer。这样每个场景可以拥有自己的 skills、memory 和 tool allowlist。
"""

from __future__ import annotations

from pathlib import Path
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

_SUMMARIZATION_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "summarization.txt"


def _load_summarization_prompt() -> str | None:
    """读取决策 11 五字段 compaction 摘要模板；失败回退 None（deepagents 默认 prompt）。"""
    try:
        return _SUMMARIZATION_PROMPT_PATH.read_text(encoding="utf-8")
    except OSError:
        logger.warning("build_deep_agent.summarization_prompt_missing", path=str(_SUMMARIZATION_PROMPT_PATH))
        return None


async def build_deep_agent(
    spec: AgentSpec,
    *,
    tools: list[Any] | None = None,
):
    """按业务规格创建一个 deepagent。"""
    settings = get_settings()
    backend = build_agent_backend()
    checkpointer = await build_checkpointer() if spec.use_checkpointer else None

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
        summary_prompt = _load_summarization_prompt()
        if summary_prompt is not None:
            summarization = SummarizationMiddleware(
                model=llm,
                backend=backend,
                trigger=trigger,
                keep=("tokens", settings.agent_compaction_keep_tokens),
                summary_prompt=summary_prompt,
            )
        else:
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

    # Phase 2 多租户修复：main agent 对 AGENTS.md 代码级禁写
    # （deepagents MemoryMiddleware 内置 <memory_guidelines> 会主动教唆写回，
    # 仅靠 prompt 约束不可控；用户级记忆一律走 chat_memory_entries 表）
    permissions = None
    if spec.name == "main_agent":
        from deepagents import FilesystemPermission

        permissions = [
            FilesystemPermission(operations=["write"], paths=["/memories/AGENTS.md"], mode="deny")
        ]

    agent = create_deep_agent(
        model=llm,
        tools=tools,
        backend=backend,
        skills=list(spec.skills),
        memory=list(spec.memory),
        checkpointer=checkpointer,
        system_prompt=spec.system_prompt,
        middleware=middleware,
        permissions=permissions,
    )

    # 外层 agent run 也以业务名标识（图级别的 trace 根节点），LLM 层的
    # run 名由 build_chat_openai 的 name 字段承载，两层在 LangSmith 中一致。
    if spec.task_name:
        return agent.with_config(run_name=spec.task_name.value)

    return agent
