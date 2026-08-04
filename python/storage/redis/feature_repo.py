from __future__ import annotations

import json
from typing import Any

import redis.asyncio as redis

from config import get_settings


class RedisFeatureRepository:
    def __init__(self):
        self.settings = get_settings()
        self._client: redis.Redis | None = None

    @property
    def is_available(self) -> bool:
        return self._client is not None

    async def connect(self) -> None:
        if self._client:
            return
        self._client = redis.from_url(self.settings.redis_url, decode_responses=True)
        await self._client.ping()

    async def ping(self) -> bool:
        try:
            await self.connect()
            assert self._client is not None
            await self._client.ping()
            return True
        except Exception:
            self._client = None
            return False

    async def get_user_features(self, user_id: str) -> dict[str, Any]:
        if not await self.ping():
            return {}
        assert self._client is not None
        key = f"feature:user:{user_id}"
        raw = await self._client.get(key)
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    async def upsert_user_features(self, user_id: str, features: dict[str, Any]) -> None:
        if not await self.ping():
            return
        assert self._client is not None
        key = f"feature:user:{user_id}"
        await self._client.set(key, json.dumps(features, ensure_ascii=False), ex=self.settings.feature_ttl_seconds)
