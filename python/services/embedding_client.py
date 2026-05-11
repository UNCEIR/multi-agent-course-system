from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from typing import Any

import httpx

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


class DashScopeMultimodalEmbeddingClient(EmbeddingClient):
    """DashScope multimodal embedding client for real third-party vectors."""

    def __init__(
        self,
        api_key: str,
        model: str,
        dimension: int,
        base_url: str,
        batch_size: int,
        timeout_seconds: float,
    ):
        if not api_key.strip():
            raise ValueError("ECOM_EMBEDDING_API_KEY is required for dashscope_multimodal")
        if not model.strip():
            raise ValueError("ECOM_EMBEDDING_MODEL is required for dashscope_multimodal")
        self.api_key = api_key
        self.model = model
        self.dimension = dimension
        self.endpoint = self._build_endpoint(base_url)
        self.batch_size = max(1, batch_size)
        self.timeout_seconds = timeout_seconds

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            vectors.extend(self._embed_batch(batch))
        return vectors

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": {
                "contents": [{"text": text.strip() or " "} for text in texts],
            },
            "parameters": {
                "dimension": self.dimension,
            },
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(self.endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        embeddings = data.get("output", {}).get("embeddings", [])
        if len(embeddings) != len(texts):
            raise RuntimeError(
                f"DashScope embedding response size mismatch: expected {len(texts)}, got {len(embeddings)}"
            )
        embeddings.sort(key=lambda item: item.get("index", 0))
        vectors = [item["embedding"] for item in embeddings]
        for vector in vectors:
            if len(vector) != self.dimension:
                raise RuntimeError(
                    f"Embedding dimension mismatch: expected {self.dimension}, got {len(vector)}"
                )
        return vectors

    @staticmethod
    def _build_endpoint(base_url: str) -> str:
        base = base_url.strip().rstrip("/") or "https://dashscope.aliyuncs.com/api/v1"
        if "/services/embeddings/multimodal-embedding/multimodal-embedding" in base:
            return base
        if base.endswith("/api/v1"):
            return f"{base}/services/embeddings/multimodal-embedding/multimodal-embedding"
        return f"{base}/api/v1/services/embeddings/multimodal-embedding/multimodal-embedding"


def build_embedding_client() -> EmbeddingClient:
    settings = get_settings()
    provider = settings.embedding_provider.lower().strip()
    if provider == "local":
        return LocalDeterministicEmbeddingClient(dimension=settings.embedding_dimension)
    if provider == "dashscope_multimodal":
        return DashScopeMultimodalEmbeddingClient(
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
            dimension=settings.embedding_dimension,
            base_url=settings.embedding_base_url,
            batch_size=settings.embedding_batch_size,
            timeout_seconds=settings.embedding_timeout_seconds,
        )
    raise ValueError(f"Unsupported ECOM_EMBEDDING_PROVIDER: {settings.embedding_provider}")
