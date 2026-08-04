from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "LLMTaskName",
    "build_chat_openai",
    "build_tool_calling_llm",
    "build_embedding_client",
    "EmbeddingClient",
    "MetricsCollector",
    "StreamTokenMarkupParser",
]

if TYPE_CHECKING:
    from .embedding_client import EmbeddingClient, build_embedding_client
    from .llm_client import build_chat_openai
    from .llm_task_name import LLMTaskName


def __getattr__(name: str):
    if name == "LLMTaskName":
        from .llm_task_name import LLMTaskName

        return LLMTaskName
    if name == "build_chat_openai":
        from .llm_client import build_chat_openai

        return build_chat_openai
    if name == "build_tool_calling_llm":
        from .llm_client import build_tool_calling_llm

        return build_tool_calling_llm
    if name == "build_embedding_client":
        from .embedding_client import build_embedding_client

        return build_embedding_client
    if name == "EmbeddingClient":
        from .embedding_client import EmbeddingClient

        return EmbeddingClient
    raise AttributeError(f"module 'ai' has no attribute {name!r}")