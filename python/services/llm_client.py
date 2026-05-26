from __future__ import annotations

import httpx
from langchain_openai import ChatOpenAI

from config import get_settings


def build_chat_openai(*, temperature: float, max_tokens: int, streaming: bool = False) -> ChatOpenAI:
    settings = get_settings()
    return _create_chat_openai(
        temperature=temperature,
        max_tokens=max_tokens,
        streaming=streaming,
    )


def build_tool_calling_llm(
    tools: list[dict],
    *,
    temperature: float = 0.1,
    max_tokens: int = 4096,
) -> ChatOpenAI:
    llm = _create_chat_openai(temperature=temperature, max_tokens=max_tokens)
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
