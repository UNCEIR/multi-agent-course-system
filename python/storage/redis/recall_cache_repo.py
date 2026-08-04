from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

import redis.asyncio as redis

from config import get_settings
from models.schemas import StudentProfile


@dataclass(frozen=True)
class RecallCacheContext:
    cache_key: str
    payload: dict[str, Any]
    structured_signature: str
    normalized_prompt: str


class RecallCacheKeyBuilder:
    """Builds stable keys from structured recall constraints."""

    version = "v1"

    def build(
        self,
        profile: StudentProfile | None,
        prompt: str = "",
        context: dict[str, Any] | None = None,
    ) -> str:
        return self.build_context(profile=profile, prompt=prompt, context=context).cache_key

    def build_context(
        self,
        profile: StudentProfile | None,
        prompt: str = "",
        context: dict[str, Any] | None = None,
    ) -> RecallCacheContext:
        payload = self._build_payload(profile=profile, prompt=prompt, context=context)
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        cache_key = f"recall:{self.version}:{digest}"
        return RecallCacheContext(
            cache_key=cache_key,
            payload=payload,
            structured_signature=self._structured_signature(payload),
            normalized_prompt=self._normalize_scalar(prompt),
        )

    def _build_payload(
        self,
        profile: StudentProfile | None,
        prompt: str = "",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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
        payload["prompt"] = self._normalize_scalar(prompt)[:80]
        return payload

    @staticmethod
    def _structured_signature(payload: dict[str, Any]) -> str:
        structured_payload = {key: value for key, value in payload.items() if key != "prompt"}
        if not any(structured_payload.values()):
            return "none"
        raw = json.dumps(structured_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

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

    async def index_semantic_cache(
        self,
        cache_key: str,
        structured_signature: str,
        prompt: str,
        embedding: list[float],
    ) -> None:
        if (
            not self.settings.course_recall_cache_enabled
            or not self.settings.course_recall_cache_semantic_enabled
            or not prompt.strip()
            or not embedding
        ):
            return
        try:
            client = await self.connect()
            meta_payload = {
                "cache_key": cache_key,
                "structured_signature": structured_signature or "none",
                "prompt": prompt.strip()[:120],
                "embedding": [float(value) for value in embedding],
            }
            ttl = int(self.settings.course_recall_cache_ttl_seconds)
            await client.set(self.semantic_meta_key(cache_key), json.dumps(meta_payload, ensure_ascii=False), ex=ttl)
            bucket_key = self.semantic_bucket_key(structured_signature or "none")
            await client.sadd(bucket_key, cache_key)
            await client.expire(bucket_key, ttl)
        except Exception:
            self._client = None

    async def find_semantic_cache_key(
        self,
        structured_signature: str,
        query_embedding: list[float],
        similarity_threshold: float,
        max_candidates: int,
        exclude_keys: set[str] | None = None,
    ) -> tuple[str | None, float]:
        if (
            not self.settings.course_recall_cache_enabled
            or not self.settings.course_recall_cache_semantic_enabled
            or not query_embedding
        ):
            return None, 0.0
        try:
            client = await self.connect()
            bucket_key = self.semantic_bucket_key(structured_signature or "none")
            member_keys = sorted(await client.smembers(bucket_key))
            if not member_keys:
                return None, 0.0
            excluded = exclude_keys or set()
            stale_keys: list[str] = []
            best_key: str | None = None
            best_score = -1.0

            for cache_key in member_keys[: max(max_candidates, 1)]:
                if cache_key in excluded:
                    continue
                if not await client.exists(cache_key):
                    stale_keys.append(cache_key)
                    continue
                raw_meta = await client.get(self.semantic_meta_key(cache_key))
                if not raw_meta:
                    stale_keys.append(cache_key)
                    continue
                try:
                    meta = json.loads(raw_meta)
                    candidate_embedding = [float(value) for value in meta.get("embedding") or []]
                except (TypeError, ValueError, json.JSONDecodeError):
                    stale_keys.append(cache_key)
                    continue
                score = self._cosine_similarity(query_embedding, candidate_embedding)
                if score > best_score:
                    best_score = score
                    best_key = cache_key

            if stale_keys:
                await client.srem(bucket_key, *stale_keys)
            if best_key is None or best_score < similarity_threshold:
                return None, max(best_score, 0.0)
            return best_key, best_score
        except Exception:
            self._client = None
            return None, 0.0

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

    @staticmethod
    def semantic_meta_key(cache_key: str) -> str:
        return f"{cache_key}:semantic"

    @staticmethod
    def semantic_bucket_key(structured_signature: str) -> str:
        return f"recall:semantic:v1:{structured_signature}"

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
