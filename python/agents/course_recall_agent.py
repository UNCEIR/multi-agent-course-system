from __future__ import annotations

import asyncio
import re
from typing import Any

from models.schemas import Course, CourseRecallResult, StudentProfile
from repositories import CourseRecallCacheRepository, CourseRepository, CourseVectorRepository, RecallCacheKeyBuilder
from services import build_embedding_client

from .base_agent import BaseAgent


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
        cache_key = self.cache_key_builder.build(profile=profile, prompt=query, context=context)

        cached_courses = await self._cached_courses(cache_key)
        if cached_courses:
            candidates = self._score_candidates(cached_courses, profile, query)
            candidates.sort(key=lambda course: course.score, reverse=True)
            return CourseRecallResult(
                success=True,
                courses=candidates[: num_items * 3],
                recall_strategies=["redis_recall_cache_hit"],
                data={"total_candidates": len(candidates), "strategies": ["redis_recall_cache_hit"]},
                confidence=0.88,
            )

        lock_acquired = await self.recall_cache.try_acquire_lock(cache_key)
        if not lock_acquired:
            cached_courses = await self._wait_for_cached_courses(cache_key)
            if cached_courses:
                candidates = self._score_candidates(cached_courses, profile, query)
                candidates.sort(key=lambda course: course.score, reverse=True)
                return CourseRecallResult(
                    success=True,
                    courses=candidates[: num_items * 3],
                    recall_strategies=["redis_recall_cache_wait_hit"],
                    data={"total_candidates": len(candidates), "strategies": ["redis_recall_cache_wait_hit"]},
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

        semantic_courses: list[Course] = []
        if query:
            semantic_ids = self._semantic_course_ids(query, limit=num_items * 5)
            semantic_courses = self.course_repo.fetch_courses_by_ids(semantic_ids)
            if semantic_courses:
                strategies.append("milvus_course_chunks")

        if not db_candidates and not semantic_courses:
            db_candidates = self._fallback_courses()
            strategies.append("fallback_mock")

        candidates = self._merge_dedup([semantic_courses, db_candidates])
        candidates = self._score_candidates(candidates, profile, query)
        candidates.sort(key=lambda course: course.score, reverse=True)
        await self.recall_cache.set_course_ids(cache_key, [course.course_id for course in candidates])
        strategies.append("redis_recall_cache_write" if lock_acquired else "redis_recall_cache_bypass")

        return CourseRecallResult(
            success=True,
            courses=candidates[: num_items * 3],
            recall_strategies=strategies,
            data={"total_candidates": len(candidates), "strategies": strategies},
            confidence=0.86,
        )

    async def _cached_courses(self, cache_key: str) -> list[Course]:
        cached_ids = await self.recall_cache.get_course_ids(cache_key)
        if not cached_ids:
            return []
        courses = self.course_repo.fetch_courses_by_ids(cached_ids)
        if not courses:
            return []
        return courses

    async def _wait_for_cached_courses(self, cache_key: str) -> list[Course]:
        for _ in range(max(self.settings.course_recall_cache_wait_retries, 0)):
            await asyncio.sleep(self.settings.course_recall_cache_wait_seconds)
            courses = await self._cached_courses(cache_key)
            if courses:
                return courses
        return []

    def _semantic_course_ids(self, query: str, limit: int) -> list[str]:
        try:
            chunk_ids = self.vector_repo.search(query=query, limit=limit)
        except Exception as exc:
            self.logger.warning("course_recall.vector_search_failed", error=str(exc))
            return []
        course_ids = []
        for chunk_id in chunk_ids:
            course_id = str(chunk_id).split(":", 1)[0]
            if course_id and course_id not in course_ids:
                course_ids.append(course_id)
        return course_ids

    def _score_candidates(
        self, courses: list[Course], profile: StudentProfile | None, query: str
    ) -> list[Course]:
        query_terms = [term for term in re.split(r"\s+|，|,|。", query) if term]
        scored = []
        for course in courses:
            score = 0.0
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
            if profile:
                if course.domain in profile.preferred_domains:
                    score += 4.0
                if course.course_category in profile.preferred_categories:
                    score += 3.0
                if course.campus in profile.preferred_campus:
                    score += 2.0
                if profile.workload_preference == "少" and course.workload in ("低", "少"):
                    score += 1.5
                if profile.exam_preference == "不考试" and course.has_exam == "否":
                    score += 1.5
                if profile.grade_friendly_preference == "高" and course.grade_friendly in ("高", "中"):
                    score += 1.2
            if course.popularity_level in ("热门", "爆满"):
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
        if len(query) > 12:
            return ""
        return query[:30]

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
                popularity_level="爆满",
                rush_advice="非常热门，选课阶段需要优先抢课",
                description="通过啤酒游戏理解供应链管理和系统决策。",
                assessment="平时作业30%;案例作业30%;期末报告40%",
                difficulty="中",
                workload="中",
                grade_friendly="中",
                has_exam="否",
                group_work_required="否",
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
                popularity_level="爆满",
                rush_advice="非常热门，选课阶段需要优先抢课",
                description="关注自然科学、生态环境与现实生活之间的联系。",
                assessment="平时作业30%;案例分析40%;期末报告30%",
                difficulty="中",
                workload="中",
                grade_friendly="中",
                has_exam="否",
                group_work_required="否",
                tags=["自然科学", "环境", "案例分析", "报告"],
            ),
        ]
