from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod

from config import get_settings


class EmbeddingClient(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Generate one embedding vector for text."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]


class LocalDeterministicEmbeddingClient(EmbeddingClient):
    """Deterministic embedding for local development and stable tests."""

    def __init__(self, dimension: int):
        self.dimension = max(8, dimension)

    def embed_text(self, text: str) -> list[float]:
        seed = text.strip() or "empty"
        vector = [0.0] * self.dimension
        for idx in range(self.dimension):
            digest = hashlib.sha256(f"{seed}:{idx}".encode("utf-8")).digest()
            value = int.from_bytes(digest[:4], byteorder="big", signed=False)
            vector[idx] = (value / 2**32) * 2 - 1
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            return vector
        return [v / norm for v in vector]


def build_embedding_client() -> EmbeddingClient:
    settings = get_settings()
    provider = settings.embedding_provider.lower().strip()
    if provider != "local":
        # 当前闭环仅实现 local provider，真实 provider 保留配置入口。
        return LocalDeterministicEmbeddingClient(dimension=settings.embedding_dimension)
    return LocalDeterministicEmbeddingClient(dimension=settings.embedding_dimension)
