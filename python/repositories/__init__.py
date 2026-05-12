from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "CourseRepository",
    "CourseRecallCacheRepository",
    "CourseVectorRepository",
    "MySQLRepository",
    "RecallCacheKeyBuilder",
    "RedisFeatureRepository",
    "MilvusRepository",
]

if TYPE_CHECKING:
    from .course_recall_cache_repository import CourseRecallCacheRepository, RecallCacheKeyBuilder
    from .course_repository import CourseRepository
    from .course_vector_repository import CourseVectorRepository
    from .milvus_repository import MilvusRepository
    from .mysql_repository import MySQLRepository
    from .redis_repository import RedisFeatureRepository


def __getattr__(name: str):
    if name == "CourseRepository":
        from .course_repository import CourseRepository

        return CourseRepository
    if name == "CourseRecallCacheRepository":
        from .course_recall_cache_repository import CourseRecallCacheRepository

        return CourseRecallCacheRepository
    if name == "RecallCacheKeyBuilder":
        from .course_recall_cache_repository import RecallCacheKeyBuilder

        return RecallCacheKeyBuilder
    if name == "CourseVectorRepository":
        from .course_vector_repository import CourseVectorRepository

        return CourseVectorRepository
    if name == "MySQLRepository":
        from .mysql_repository import MySQLRepository

        return MySQLRepository
    if name == "RedisFeatureRepository":
        from .redis_repository import RedisFeatureRepository

        return RedisFeatureRepository
    if name == "MilvusRepository":
        from .milvus_repository import MilvusRepository

        return MilvusRepository
    raise AttributeError(f"module 'repositories' has no attribute {name!r}")
