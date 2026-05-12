from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "ABTestEngine",
    "EmbeddingClient",
    "FeatureStore",
    "MetricsCollector",
    "build_chat_openai",
    "build_embedding_client",
]

if TYPE_CHECKING:
    from .ab_test import ABTestEngine
    from .embedding_client import EmbeddingClient, build_embedding_client
    from .feature_store import FeatureStore
    from .llm_client import build_chat_openai
    from .metrics import MetricsCollector


def __getattr__(name: str):
    if name == "ABTestEngine":
        from .ab_test import ABTestEngine

        return ABTestEngine
    if name == "EmbeddingClient":
        from .embedding_client import EmbeddingClient

        return EmbeddingClient
    if name == "build_embedding_client":
        from .embedding_client import build_embedding_client

        return build_embedding_client
    if name == "FeatureStore":
        from .feature_store import FeatureStore

        return FeatureStore
    if name == "build_chat_openai":
        from .llm_client import build_chat_openai

        return build_chat_openai
    if name == "MetricsCollector":
        from .metrics import MetricsCollector

        return MetricsCollector
    raise AttributeError(f"module 'services' has no attribute {name!r}")
