from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from config import get_settings
from agents.course_recall_agent import CourseRecallAgent
from models.schemas import Course, StudentProfile

# Embedding 维度跟随配置（中转站 text-embedding-v4，1024 维），避免维度变更时测试漏改。
_EMBED_DIM = get_settings().embedding_dimension


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


class _SemanticCacheHit:
    async def get_course_ids(self, cache_key: str) -> list[str]:
        if cache_key == "semantic:hit:key":
            return ["GXK003"]
        return []

    async def find_semantic_cache_key(
        self,
        structured_signature: str,
        query_embedding: list[float],
        similarity_threshold: float,
        max_candidates: int,
        exclude_keys: set[str] | None = None,
    ) -> tuple[str | None, float]:
        return "semantic:hit:key", 0.97

    async def set_course_ids(self, cache_key: str, course_ids: list[str]) -> None:
        raise AssertionError("semantic cache hit should not rewrite")

    async def try_acquire_lock(self, cache_key: str) -> bool:
        raise AssertionError("semantic cache hit should bypass lock")


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
    agent.vector_repo.embedding_client.embed_text = MagicMock(return_value=[0.1] * _EMBED_DIM)

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
    agent.vector_repo.search = MagicMock(return_value=[
        {"chunk_id": "GXK002:0:basic", "course_id": "GXK002", "distance": 0.2}
    ])
    agent.vector_repo.embedding_client.embed_text = MagicMock(return_value=[0.1] * _EMBED_DIM)
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
    agent.vector_repo.embedding_client.embed_text = MagicMock(return_value=[0.1] * _EMBED_DIM)
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


@pytest.mark.asyncio
async def test_course_recall_uses_semantic_cache_when_exact_key_misses():
    agent = CourseRecallAgent()
    agent.recall_cache = _SemanticCacheHit()

    profile = StudentProfile(student_id="S10001", preferred_domains=[])
    semantic_course = Course(course_id="GXK003", course_name="地球科学概论", domain="自然环境")

    agent.course_repo.fetch_courses_by_ids = MagicMock(return_value=[semantic_course])
    agent.course_repo.fetch_courses = MagicMock(side_effect=AssertionError("semantic hit should skip structured recall"))
    agent.vector_repo.search = MagicMock(side_effect=AssertionError("semantic hit should skip milvus search"))
    agent.vector_repo.embedding_client.embed_text = MagicMock(return_value=[0.1] * _EMBED_DIM)

    result = await agent.run(
        student_profile=profile,
        prompt="我想找轻松一点的地理相关通识课",
        context={},
        num_items=1,
    )

    assert [course.course_id for course in result.courses] == ["GXK003"]
    assert result.recall_strategies == ["redis_recall_cache_semantic_hit"]
    assert result.data["cache_match_type"] == "semantic"
