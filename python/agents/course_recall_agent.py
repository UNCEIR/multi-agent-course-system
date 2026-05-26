from __future__ import annotations

import asyncio
import re
from typing import Any, Literal
import structlog

from models.schemas import Course, CourseRecallResult, StudentProfile
from repositories import CourseRecallCacheRepository, CourseRepository, CourseVectorRepository, RecallCacheKeyBuilder
from services import build_embedding_client

from .base_agent import BaseAgent

logger = structlog.get_logger()

class CourseRecallAgent(BaseAgent):
    def __init__(self):
        from config import get_settings

        settings = get_settings()
        self.settings = settings
        super().__init__(
            name="course_recall",
            timeout=settings.agent_timeout_product_recall,
        )
        self.course_repo = CourseRepository()
        self.vector_repo = CourseVectorRepository(build_embedding_client())
        self.cache_key_builder = RecallCacheKeyBuilder()
        self.recall_cache = CourseRecallCacheRepository()
    async def _execute(self, **kwargs: Any) -> CourseRecallResult:
        profile: StudentProfile | None = kwargs.get("student_profile")
        prompt: str = kwargs.get("prompt", "")
        context: dict[str, Any] = kwargs.get("context", {})
        num_items: int = kwargs.get("num_items", 10)
        query = (prompt or context.get("query") or "").strip()
        query_embedding: list[float] | None = None
        if query:
            try:
                query_embedding = self.vector_repo.embedding_client.embed_text(query)
                self.logger.info(
                    "course_recall.query_embedded",
                    query_len=len(query),
                    embedding_dim=len(query_embedding),
                )
            except Exception as exc:
                self.logger.warning("course_recall.query_embedding_failed", error=str(exc), query_len=len(query))
        cache_context = self.cache_key_builder.build_context(profile=profile, prompt=query, context=context)
        cache_key = cache_context.cache_key
        self.logger.info(
            "course_recall.cache_probe",
            cache_key_suffix=self._cache_key_suffix(cache_key),
            structured_signature=cache_context.structured_signature,
            query_len=len(query),
            has_profile=profile is not None,
        )

        cached_courses = await self._cached_courses(cache_key, source="exact")
        if cached_courses:
            self.logger.info(
                "course_recall.cache_hit",
                match_type="exact",
                cache_key_suffix=self._cache_key_suffix(cache_key),
                candidate_count=len(cached_courses),
                milvus_skipped=True,
            )
            candidates = self._score_candidates(cached_courses, profile, query)
            candidates.sort(key=lambda course: course.score, reverse=True)
            return CourseRecallResult(
                success=True,
                courses=candidates,
                recall_strategies=["redis_recall_cache_hit"],
                data={
                    "total_candidates": len(candidates),
                    "strategies": ["redis_recall_cache_hit"],
                    "cache_match_type": "exact",
                    "cache_key_suffix": self._cache_key_suffix(cache_key),
                    "milvus_skipped": True,
                },
                confidence=0.88,
            )

        semantic_courses, semantic_similarity, semantic_cache_key = await self._semantic_cached_courses(
            query=query,
            structured_signature=cache_context.structured_signature,
            excluded_keys={cache_key},
            query_embedding=query_embedding,
        )
        if semantic_courses:
            self.logger.info(
                "course_recall.cache_hit",
                match_type="semantic",
                cache_key_suffix=self._cache_key_suffix(semantic_cache_key),
                similarity=round(semantic_similarity, 4),
                candidate_count=len(semantic_courses),
                milvus_skipped=True,
            )
            candidates = self._score_candidates(semantic_courses, profile, query)
            candidates.sort(key=lambda course: course.score, reverse=True)
            return CourseRecallResult(
                success=True,
                courses=candidates,
                recall_strategies=["redis_recall_cache_semantic_hit"],
                data={
                    "total_candidates": len(candidates),
                    "strategies": ["redis_recall_cache_semantic_hit"],
                    "cache_match_type": "semantic",
                    "cache_key_suffix": self._cache_key_suffix(semantic_cache_key),
                    "cache_similarity": round(semantic_similarity, 4),
                    "milvus_skipped": True,
                },
                confidence=0.87,
            )

        lock_acquired = await self.recall_cache.try_acquire_lock(cache_key)
        self.logger.info(
            "course_recall.cache_lock",
            cache_key_suffix=self._cache_key_suffix(cache_key),
            lock_acquired=lock_acquired,
        )
        if not lock_acquired:
            cached_courses = await self._wait_for_cached_courses(cache_key)
            if cached_courses:
                self.logger.info(
                    "course_recall.cache_hit",
                    match_type="wait_hit",
                    cache_key_suffix=self._cache_key_suffix(cache_key),
                    candidate_count=len(cached_courses),
                    milvus_skipped=True,
                )
                candidates = self._score_candidates(cached_courses, profile, query)
                candidates.sort(key=lambda course: course.score, reverse=True)
                return CourseRecallResult(
                    success=True,
                    courses=candidates,
                    recall_strategies=["redis_recall_cache_wait_hit"],
                    data={
                        "total_candidates": len(candidates),
                        "strategies": ["redis_recall_cache_wait_hit"],
                        "cache_match_type": "wait_hit",
                        "cache_key_suffix": self._cache_key_suffix(cache_key),
                        "milvus_skipped": True,
                    },
                    confidence=0.87,
                )

        db_candidates = self.course_repo.fetch_courses(
            limit=max(num_items * 8, 40),
            domains=profile.preferred_domains if profile else None,
            categories=profile.preferred_categories if profile else None,
            campus=profile.preferred_campus if profile else None,
            query_text=self._short_query(query),
        )
        strategies = ["mysql_structured"]
        self.logger.info(
            "course_recall.mysql_structured.done",
            cache_key_suffix=self._cache_key_suffix(cache_key),
            candidate_count=len(db_candidates),
            query_short_used=bool(self._short_query(query)),
        )

        semantic_courses: list[Course] = []
        semantic_status: str | None = None
        if query and query_embedding is not None:
            semantic_ids, semantic_distances, semantic_status = self._semantic_course_ids(
                query, limit=num_items * 5, query_embedding=query_embedding
            )
            semantic_courses = self.course_repo.fetch_courses_by_ids(semantic_ids)
            id_to_distance = dict(zip(semantic_ids, semantic_distances))
            for course in semantic_courses:
                distance = id_to_distance.get(course.course_id, 1.0)
                course.score = max(0.0, 1.0 - distance)
            if semantic_status == "failed":
                strategies.append("milvus_vector_search_failed")
            elif semantic_status == "empty":
                strategies.append("milvus_course_chunks_empty")
            elif semantic_status == "hit":
                strategies.append("milvus_course_chunks")
            self.logger.info(
                "course_recall.milvus_query.done",
                status=semantic_status,
                semantic_id_count=len(semantic_ids),
                semantic_course_count=len(semantic_courses),
            )

        if not db_candidates and not semantic_courses:
            self.logger.warning(
                "course_recall.empty_recall",
                cache_key_suffix=self._cache_key_suffix(cache_key),
            )
            db_candidates = self._fallback_courses()
            strategies.append("fallback_mock")

        self.logger.info(
            "course_recall.merge_input",
            mysql_count=len(db_candidates),
            semantic_count=len(semantic_courses),
        )
        candidates = self._merge_dedup([semantic_courses, db_candidates])
        self.logger.info(
            "course_recall.merge_done",
            merged_count=len(candidates),
            mysql_source=len(db_candidates),
            semantic_source=len(semantic_courses),
        )
        candidates = self._score_candidates(candidates, profile, query)
        candidates.sort(key=lambda course: course.score, reverse=True)
        if candidates:
            scores = [course.score for course in candidates]
            self.logger.info(
                "course_recall.scored",
                candidate_count=len(candidates),
                score_min=round(min(scores), 4),
                score_max=round(max(scores), 4),
                score_avg=round(sum(scores) / len(scores), 4),
            )
        await self.recall_cache.set_course_ids(cache_key, [course.course_id for course in candidates])
        if lock_acquired and query and query_embedding is not None:
            await self._index_semantic_cache(
                cache_key=cache_key,
                structured_signature=cache_context.structured_signature,
                query=query,
                query_embedding=query_embedding,
            )
        strategies.append("redis_recall_cache_write" if lock_acquired else "redis_recall_cache_bypass")
        self.logger.info(
            "course_recall.cache_write",
            cache_key_suffix=self._cache_key_suffix(cache_key),
            lock_acquired=lock_acquired,
            candidate_count=len(candidates),
        )

        return CourseRecallResult(
            success=True,
            courses=candidates,
            recall_strategies=strategies,
            data={
                "total_candidates": len(candidates),
                "strategies": strategies,
                "semantic_status": semantic_status or "skipped",
                "cache_match_type": "miss",
                "cache_key_suffix": self._cache_key_suffix(cache_key),
            },
            confidence=0.86,
        )

    async def _cached_courses(self, cache_key: str, source: str = "exact") -> list[Course]:
        cached_ids = await self.recall_cache.get_course_ids(cache_key)
        if not cached_ids:
            self.logger.info(
                "course_recall.cache_miss",
                source=source,
                cache_key_suffix=self._cache_key_suffix(cache_key),
            )
            return []
        courses = self.course_repo.fetch_courses_by_ids(cached_ids)
        if not courses:
            self.logger.warning(
                "course_recall.cache_ids_stale",
                source=source,
                cache_key_suffix=self._cache_key_suffix(cache_key),
                cached_id_count=len(cached_ids),
            )
            return []
        self.logger.info(
            "course_recall.cache_course_ids_loaded",
            source=source,
            cache_key_suffix=self._cache_key_suffix(cache_key),
            cached_id_count=len(cached_ids),
            loaded_course_count=len(courses),
        )
        return courses

    async def _wait_for_cached_courses(self, cache_key: str) -> list[Course]:
        for attempt in range(max(self.settings.course_recall_cache_wait_retries, 0)):
            await asyncio.sleep(self.settings.course_recall_cache_wait_seconds)
            courses = await self._cached_courses(cache_key, source="wait")
            if courses:
                self.logger.info(
                    "course_recall.wait_success",
                    cache_key_suffix=self._cache_key_suffix(cache_key),
                    attempt=attempt + 1,
                )
                return courses
            self.logger.info(
                "course_recall.wait_retry",
                cache_key_suffix=self._cache_key_suffix(cache_key),
                attempt=attempt + 1,
            )
        return []

    async def _semantic_cached_courses(
        self,
        query: str,
        structured_signature: str,
        excluded_keys: set[str],
        query_embedding: list[float] | None = None,
    ) -> tuple[list[Course], float, str]:
        if (
            not getattr(self.settings, "course_recall_cache_semantic_enabled", False)
            or not query
            or len(query) < max(int(self.settings.course_recall_cache_semantic_min_prompt_chars), 1)
        ):
            self.logger.info(
                "course_recall.semantic_cache_skipped",
                reason="disabled_short_or_empty",
                semantic_enabled=getattr(self.settings, "course_recall_cache_semantic_enabled", False),
                query_len=len(query),
            )
            return [], 0.0, ""
        if query_embedding is None:
            self.logger.info(
                "course_recall.semantic_cache_skipped",
                reason="no_query_embedding",
            )
            return [], 0.0, ""
        find_match = getattr(self.recall_cache, "find_semantic_cache_key", None)
        if not callable(find_match):
            return [], 0.0, ""
        try:
            matched_key, similarity = await find_match(
                structured_signature=structured_signature,
                query_embedding=query_embedding,
                similarity_threshold=float(self.settings.course_recall_cache_semantic_threshold),
                max_candidates=int(self.settings.course_recall_cache_semantic_max_candidates),
                exclude_keys=excluded_keys,
            )
        except Exception as exc:
            self.logger.warning(
                "course_recall.semantic_cache_find_failed",
                error=str(exc),
                structured_signature=structured_signature,
            )
            return [], 0.0, ""
        if not matched_key:
            self.logger.info(
                "course_recall.semantic_cache_miss",
                structured_signature=structured_signature,
                similarity=round(similarity, 4),
            )
            return [], 0.0, ""
        courses = await self._cached_courses(matched_key, source="semantic")
        if not courses:
            return [], 0.0, ""
        return courses, similarity, matched_key

    async def _index_semantic_cache(
        self,
        cache_key: str,
        structured_signature: str,
        query: str,
        query_embedding: list[float] | None = None,
    ) -> None:
        index_semantic = getattr(self.recall_cache, "index_semantic_cache", None)
        if not callable(index_semantic):
            return
        if query_embedding is None:
            return
        try:
            await index_semantic(
                cache_key=cache_key,
                structured_signature=structured_signature,
                prompt=query,
                embedding=query_embedding,
            )
            self.logger.info(
                "course_recall.semantic_cache_indexed",
                cache_key_suffix=self._cache_key_suffix(cache_key),
                structured_signature=structured_signature,
            )
        except Exception as exc:
            self.logger.warning(
                "course_recall.semantic_cache_index_failed",
                cache_key_suffix=self._cache_key_suffix(cache_key),
                error=str(exc),
            )

    def _semantic_course_ids(
        self, query: str, limit: int, query_embedding: list[float] | None = None
    ) -> tuple[list[str], list[float], Literal["hit", "empty", "failed"]]:
        try:
            results = self.vector_repo.search(query=query, limit=limit, query_vector=query_embedding)
        except Exception as exc:
            self.logger.warning("course_recall.vector_search_failed", error=str(exc))
            return [], [], "failed"
        if not results:
            return [], [], "empty"
        course_ids: list[str] = []
        distances: list[float] = []
        seen: set[str] = set()
        for result in results:
            course_id = str(result.get("course_id", ""))
            if course_id and course_id not in seen:
                seen.add(course_id)
                course_ids.append(course_id)
                distances.append(float(result.get("distance", 1.0)))
        if not course_ids:
            self.logger.warning(
                "course_recall.vector_search_no_unique_courses",
                chunk_count=len(results),
            )
            return [], [], "empty"
        return course_ids, distances, "hit"

    def _score_candidates(
        self, courses: list[Course], profile: StudentProfile | None, query: str
    ) -> list[Course]:
        query_terms = [term for term in re.split(r"\s+|，|,|。", query) if term]
        scored = []
        for course in courses:
            score = course.score
            text = " ".join(
                [
                    course.course_name,
                    course.teacher,
                    course.domain,
                    course.course_category,
                    course.description,
                    course.suitable_for,
                    " ".join(course.tags),
                ]
            )
            for term in query_terms:
                if term and term in text:
                    score += 1.5
            if course.popularity_level >= 3:
                score += 0.8
            scored.append(course.model_copy(update={"score": round(score, 4)}))
        return scored

    @staticmethod
    def _merge_dedup(result_sets: list[list[Course]]) -> list[Course]:
        seen: set[str] = set()
        merged: list[Course] = []
        max_len = max((len(result_set) for result_set in result_sets), default=0)
        for index in range(max_len):
            for result_set in result_sets:
                if index >= len(result_set):
                    continue
                course = result_set[index]
                if course.course_id not in seen:
                    seen.add(course.course_id)
                    merged.append(course)
        return merged

    @staticmethod
    def _short_query(query: str) -> str:
        if not query:
            return ""
        if len(query) > 50:
            return ""
        return query[:50]

    @staticmethod
    def _cache_key_suffix(cache_key: str) -> str:
        return cache_key.rsplit(":", 1)[-1]

    @staticmethod
    def _fallback_courses() -> list[Course]:
        return [
            Course(
                course_id="GXK2026001",
                course_name="啤酒游戏-漫谈供应链管理",
                teacher="范捷",
                credits=1.5,
                course_category="自然科学与工程技术类",
                domain="工程技术",
                campus="南校区",
                time_slot="周二第5-6节",
                capacity=100,
                current_enrolled=101,
                popularity_level=4,
                rush_advice="非常热门，选课阶段需要优先抢课",
                description="通过啤酒游戏理解供应链管理和系统决策。",
                assessment="平时作业30%;案例作业30%;期末报告40%",
                difficulty="中",
                workload="中",
                grade_friendly="中",
                has_exam=0,
                group_work_required=0,
                tags=["工程技术", "产业", "案例", "报告"],
            ),
            Course(
                course_id="GXK2026003",
                course_name="风景地貌学",
                teacher="杨雪强",
                credits=1.5,
                course_category="自然科学与工程技术类",
                domain="自然环境",
                campus="东校区",
                time_slot="周四第7-8节",
                capacity=200,
                current_enrolled=200,
                popularity_level=4,
                rush_advice="非常热门，选课阶段需要优先抢课",
                description="关注自然科学、生态环境与现实生活之间的联系。",
                assessment="平时作业30%;案例分析40%;期末报告30%",
                difficulty="中",
                workload="中",
                grade_friendly="中",
                has_exam=0,
                group_work_required=0,
                tags=["自然科学", "环境", "案例分析", "报告"],
            ),
        ]
