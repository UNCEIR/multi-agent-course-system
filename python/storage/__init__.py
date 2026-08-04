from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "CourseRepository",
    "CourseRecallCacheRepository",
    "CourseVectorRepository",
    "MySQLRepository",
    "RecallCacheKeyBuilder",
    "RedisFeatureRepository",
]

if TYPE_CHECKING:
    from .mysql.base import MySQLRepository
    from .mysql.course_repo import CourseRepository
    from .milvus.course_vector_repo import CourseVectorRepository
    from .redis.feature_repo import RedisFeatureRepository
    from .redis.recall_cache_repo import CourseRecallCacheRepository, RecallCacheKeyBuilder


def __getattr__(name: str):
    if name == "MySQLRepository":
        from .mysql.base import MySQLRepository

        return MySQLRepository
    if name == "CourseRepository":
        from .mysql.course_repo import CourseRepository

        return CourseRepository
    if name == "CourseVectorRepository":
        from .milvus.course_vector_repo import CourseVectorRepository

        return CourseVectorRepository
    if name == "RedisFeatureRepository":
        from .redis.feature_repo import RedisFeatureRepository

        return RedisFeatureRepository
    if name == "CourseRecallCacheRepository":
        from .redis.recall_cache_repo import CourseRecallCacheRepository

        return CourseRecallCacheRepository
    if name == "RecallCacheKeyBuilder":
        from .redis.recall_cache_repo import RecallCacheKeyBuilder

        return RecallCacheKeyBuilder
    raise AttributeError(f"module 'storage' has no attribute {name!r}")