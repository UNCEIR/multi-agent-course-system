from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agents.course_recall_agent import CourseRecallAgent
from models.schemas import Course, StudentProfile


class _CacheHit:
    async def get_course_ids(self, cache_key: str) -> list[str]:
        return ["GXK001", "GXK002"]

    async def set_course_ids(self, cache_key: str, course_ids: list[str]) -> None:
        raise AssertionError("cache should not be rewritten on hit")

    async def try_acquire_lock(self, cache_key: str) -> bool:
        raise AssertionError("lock should not be acquired on hit")


class _CacheMiss:
    def __init__(self):
        self.written_ids: list[str] = []
        self.lock_attempts = 0

    async def get_course_ids(self, cache_key: str) -> list[str]:
        return []

    async def set_course_ids(self, cache_key: str, course_ids: list[str]) -> None:
        self.written_ids = course_ids

    async def try_acquire_lock(self, cache_key: str) -> bool:
        self.lock_attempts += 1
        return True


class _UnavailableCache:
    async def get_course_ids(self, cache_key: str) -> list[str]:
        return []

    async def set_course_ids(self, cache_key: str, course_ids: list[str]) -> None:
        return None

    async def try_acquire_lock(self, cache_key: str) -> bool:
        return False


@pytest.mark.asyncio
async def test_course_recall_uses_cached_course_ids_and_skips_vector_search():
    agent = CourseRecallAgent()
    agent.recall_cache = _CacheHit()

    profile = StudentProfile(
        student_id="S10001",
        preferred_domains=["人文艺术"],
        preferred_campus=["东校区"],
        exam_preference="不考试",
        workload_preference="少",
        grade_friendly_preference="高",
    )
    cached_courses = [
        Course(course_id="GXK001", course_name="电影艺术赏析", domain="人文艺术"),
        Course(course_id="GXK002", course_name="心理学与生活", domain="社会科学"),
    ]

    agent.course_repo.fetch_courses_by_ids = MagicMock(return_value=cached_courses)
    agent.course_repo.fetch_courses = MagicMock(side_effect=AssertionError("structured recall should be skipped"))
    agent.vector_repo.search = MagicMock(side_effect=AssertionError("vector search should be skipped"))

    result = await agent.run(
        student_profile=profile,
        prompt="想选不考试、作业少、给分友好的艺术类公选课，东校区优先",
        context={},
        num_items=2,
    )

    assert [course.course_id for course in result.courses] == ["GXK001", "GXK002"]
    assert "redis_recall_cache_hit" in result.recall_strategies
    agent.course_repo.fetch_courses_by_ids.assert_called_once_with(["GXK001", "GXK002"])


@pytest.mark.asyncio
async def test_course_recall_writes_course_ids_when_cache_misses():
    agent = CourseRecallAgent()
    cache = _CacheMiss()
    agent.recall_cache = cache

    profile = StudentProfile(student_id="S10001", preferred_domains=["人文艺术"])
    db_course = Course(course_id="GXK001", course_name="电影艺术赏析", domain="人文艺术")
    semantic_course = Course(course_id="GXK002", course_name="心理学与生活", domain="人文艺术")

    agent.course_repo.fetch_courses = MagicMock(return_value=[db_course])
    agent.vector_repo.search = MagicMock(return_value=["GXK002:0:basic"])
    agent.course_repo.fetch_courses_by_ids = MagicMock(return_value=[semantic_course])

    result = await agent.run(
        student_profile=profile,
        prompt="想选艺术和心理学相关的公选课",
        context={},
        num_items=2,
    )

    assert [course.course_id for course in result.courses] == ["GXK002", "GXK001"]
    assert cache.written_ids == ["GXK002", "GXK001"]
    assert cache.lock_attempts == 1
    assert "redis_recall_cache_write" in result.recall_strategies


@pytest.mark.asyncio
async def test_course_recall_falls_back_to_full_recall_when_cache_unavailable():
    agent = CourseRecallAgent()
    agent.recall_cache = _UnavailableCache()

    profile = StudentProfile(student_id="S10001", preferred_domains=["人文艺术"])
    db_course = Course(course_id="GXK001", course_name="电影艺术赏析", domain="人文艺术")

    agent.course_repo.fetch_courses = MagicMock(return_value=[db_course])
    agent.vector_repo.search = MagicMock(return_value=[])
    agent.course_repo.fetch_courses_by_ids = MagicMock(return_value=[])

    result = await agent.run(
        student_profile=profile,
        prompt="想选艺术类公选课",
        context={},
        num_items=1,
    )

    assert [course.course_id for course in result.courses] == ["GXK001"]
    assert "mysql_structured" in result.recall_strategies
    assert "redis_recall_cache_bypass" in result.recall_strategies
