from __future__ import annotations

import httpx
from langchain_openai import ChatOpenAI

from config import get_settings
from ai.llm_task_name import LLMTaskName


def build_chat_openai(
    *,
    temperature: float,
    max_tokens: int,
    streaming: bool = False,
    task_name: LLMTaskName | None = None,
) -> ChatOpenAI:
    settings = get_settings()
    llm = _create_chat_openai(
        temperature=temperature,
        max_tokens=max_tokens,
        streaming=streaming,
    )
    if task_name is not None:
        # 用 pydantic 的 name 字段命名 trace（LangSmith 的 run name 取自
        # get_name()），同时保持返回类型为 BaseChatModel——deepagents 无法
        # 解析 with_config 产生的 RunnableBinding。
        llm.name = task_name.value
    return llm


def build_tool_calling_llm(
    tools: list[dict],
    *,
    temperature: float = 0.1,
    max_tokens: int = 4096,
    task_name: LLMTaskName | None = None,
) -> ChatOpenAI:
    llm = _create_chat_openai(temperature=temperature, max_tokens=max_tokens)
    if task_name is not None:
        # _ChatModelBinding.get_name() 委托给内部 bound，故在 bind 前命名。
        llm.name = task_name.value
    return llm.bind_tools(tools, tool_choice="auto")


def _create_chat_openai(
    *,
    temperature: float,
    max_tokens: int,
    streaming: bool = False,
) -> ChatOpenAI:
    settings = get_settings()
    extra_body = {}
    if settings.llm_enable_thinking:
        extra_body["enable_thinking"] = True

    verify = settings.httpx_verify_ssl
    http_client = httpx.Client(verify=verify)
    http_async_client = httpx.AsyncClient(verify=verify)

    return ChatOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        temperature=temperature,
        max_tokens=max_tokens,
        streaming=streaming,
        extra_body=extra_body or None,
        http_client=http_client,
        http_async_client=http_async_client,
    )
