from __future__ import annotations

import hashlib
import json
from typing import Any

import redis.asyncio as redis

from config import get_settings
from models.schemas import StudentProfile


class RecallCacheKeyBuilder:
    """Builds stable keys from structured recall constraints."""

    version = "v1"

    def build(
        self,
        profile: StudentProfile | None,
        prompt: str = "",
        context: dict[str, Any] | None = None,
    ) -> str:
        context = context or {}
        payload: dict[str, Any] = {
            "domains": self._normalize_list(profile.preferred_domains if profile else []),
            "categories": self._normalize_list(profile.preferred_categories if profile else []),
            "campus": self._normalize_list(profile.preferred_campus if profile else context.get("campus", [])),
            "exam": self._normalize_scalar(profile.exam_preference if profile else context.get("exam_preference", "")),
            "workload": self._normalize_scalar(
                profile.workload_preference if profile else context.get("workload_preference", "")
            ),
            "grade_friendly": self._normalize_scalar(
                profile.grade_friendly_preference if profile else context.get("grade_friendly_preference", "")
            ),
            "group_work": self._normalize_scalar(
                profile.group_work_preference if profile else context.get("group_work_preference", "")
            ),
            "grade": self._normalize_scalar(context.get("grade", "")),
            "major": self._normalize_scalar(context.get("major", "")),
        }
        if not any(payload.values()):
            payload["prompt"] = self._normalize_scalar(prompt)[:80]

        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        return f"recall:{self.version}:{digest}"

    @staticmethod
    def _normalize_list(value: Any) -> list[str]:
        if value in (None, ""):
            return []
        if isinstance(value, str):
            items = [value]
        else:
            items = list(value)
        normalized = {str(item).strip() for item in items if str(item).strip()}
        return sorted(normalized)

    @staticmethod
    def _normalize_scalar(value: Any) -> str:
        return str(value or "").strip()


class CourseRecallCacheRepository:
    """Redis-backed cache for recall candidate course IDs."""

    def __init__(self):
        self.settings = get_settings()
        self._client: redis.Redis | None = None

    async def connect(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(self.settings.redis_url, decode_responses=True)
            await self._client.ping()
        return self._client

    async def get_course_ids(self, cache_key: str) -> list[str]:
        if not self.settings.course_recall_cache_enabled:
            return []
        try:
            client = await self.connect()
            raw = await client.get(cache_key)
            if not raw:
                return []
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                await client.delete(cache_key)
                return []
            return [str(course_id) for course_id in parsed if str(course_id).strip()]
        except Exception:
            self._client = None
            return []

    async def set_course_ids(self, cache_key: str, course_ids: list[str]) -> None:
        if not self.settings.course_recall_cache_enabled or not course_ids:
            return
        try:
            client = await self.connect()
            unique_ids = list(dict.fromkeys(str(course_id) for course_id in course_ids if str(course_id).strip()))
            if unique_ids:
                await client.set(
                    cache_key,
                    json.dumps(unique_ids, ensure_ascii=False),
                    ex=self.settings.course_recall_cache_ttl_seconds,
                )
        except Exception:
            self._client = None

    async def try_acquire_lock(self, cache_key: str) -> bool:
        if not self.settings.course_recall_cache_enabled:
            return False
        try:
            client = await self.connect()
            acquired = await client.set(
                self.lock_key(cache_key),
                "1",
                ex=self.settings.course_recall_cache_lock_ttl_seconds,
                nx=True,
            )
            return bool(acquired)
        except Exception:
            self._client = None
            return False

    @staticmethod
    def lock_key(cache_key: str) -> str:
        return f"{cache_key}:lock"
