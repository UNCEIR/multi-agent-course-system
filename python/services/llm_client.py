from __future__ import annotations

import httpx
from langchain_openai import ChatOpenAI

from config import get_settings


def build_chat_openai(*, temperature: float, max_tokens: int) -> ChatOpenAI:
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
        extra_body=extra_body or None,
        http_client=http_client,
        http_async_client=http_async_client,
    )
