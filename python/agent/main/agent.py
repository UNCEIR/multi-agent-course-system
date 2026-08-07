# -*- coding: utf-8 -*-
"""主 Agent 工厂 — build_main_agent()。

使用 deepagents 0.7.5 的 create_deep_agent 注入：
- MemoryMiddleware（长期记忆，FilesystemBackend 真实 AGENTS.md）
- SummarizationMiddleware（compaction，对齐决策 11 contextWindow-13000/keepRecentTokens=20000）
- FilesystemMiddleware（必选，大 tool result 落盘）
- SkillsMiddleware（渐进式 skill 披露）
- SqliteSaver（thread_id 跨会话恢复 checkpointer）

tools 参数来自 ToolRegistry（runtime.tool_registry.get_all()），
build_main_agent 不直接 import 具体 tool，保持编排层与能力层分离。
"""

from __future__ import annotations

from typing import Any

from deepagents import create_deep_agent
from deepagents.middleware.summarization import (
    SummarizationMiddleware,
    SummarizationToolMiddleware,
)

from ai.llm_client import build_chat_openai
from ai.llm_task_name import LLMTaskName
from config import get_settings

from .backend import build_main_backend
from .checkpointer import build_checkpointer
from .prompt import MAIN_AGENT_SYSTEM_PROMPT


def build_main_agent(tools: list[Any] | None = None):
    """构建主 deep agent 实例。

    Args:
        tools: 工具列表（来自 ToolRegistry）。None 时尝试从 runtime 读取，
               runtime 未初始化时使用空列表（兼容单测无 runtime 场景）。

    Returns:
        Compiled deep agent 实例（可调用 .ainvoke / .invoke）。
    """
    s = get_settings()
    backend = build_main_backend()
    checkpointer = build_checkpointer()

    # 主 agent LLM：低温 + 适中 max_tokens 用于路由决策
    llm = build_chat_openai(
        temperature=0.2,
        max_tokens=2048,
        task_name=LLMTaskName.MAIN_AGENT_ROUTER,
    )

    # 对齐决策 11：trigger=contextWindow-13000, keep=20000
    # demo 可降为 messages 触发便于验证（settings.agent_compaction_trigger_messages=8）
    trigger = (
        ("messages", s.agent_compaction_trigger_messages)
        if s.agent_compaction_trigger_messages
        else ("tokens", s.agent_context_window_tokens - 13000)
    )
    summ = SummarizationMiddleware(
        model=llm,
        backend=backend,
        trigger=trigger,
        keep=("tokens", s.agent_compaction_keep_tokens),
    )
    tool_mw = SummarizationToolMiddleware(summ)

    # 解析 tool 来源：优先参数 → runtime 单例 → 空列表
    if tools is None:
        try:
            from agent import runtime as _runtime
            if _runtime.tool_registry is not None:
                tools = _runtime.tool_registry.get_all()
            else:
                tools = []
        except Exception:
            tools = []

    # 创建 deep agent
    # skills=["/skills/"] → SkillsMiddleware 自动加载 SKILL.md
    # memory=["/memories/AGENTS.md"] → MemoryMiddleware 自动加载 AGENTS.md
    # middleware=[summ, tool_mw] → 覆盖默认 SummarizationMiddleware
    return create_deep_agent(
        model=llm,
        tools=tools,
        backend=backend,
        skills=["/skills/"],
        memory=["/memories/AGENTS.md"],
        checkpointer=checkpointer,
        system_prompt=MAIN_AGENT_SYSTEM_PROMPT,
        middleware=[summ, tool_mw],
    )