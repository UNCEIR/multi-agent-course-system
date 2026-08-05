"""运行时单例容器。

管理所有全局单例（supervisor/repos/ab_engine/metrics）的生命周期。
v2 加 report/evaluation/chat 时各自单例也统一进此模块。
"""

from __future__ import annotations

from typing import Any

import structlog

from agent.recommend.supervisor import SupervisorOrchestrator
from experiment.ab_test import ABTestEngine
from observability.metrics import MetricsCollector

logger = structlog.get_logger()

# 全局单例（初始化后赋值）
ab_engine: ABTestEngine | None = None
metrics_collector: MetricsCollector | None = None
supervisor: SupervisorOrchestrator | None = None
rec_graph: Any = None
mysql_repo: Any = None
redis_repo: Any = None
course_vector_repo: Any = None


def init() -> None:
    """初始化所有运行时单例。在 lifespan 启动时调用。"""
    global ab_engine, metrics_collector, supervisor, rec_graph
    global mysql_repo, redis_repo, course_vector_repo

    from ai.embedding_client import build_embedding_client
    from ai.llm_task_name import LLMTaskName
    from agent.recommend.graph import build_recommendation_graph
    from storage.milvus.course_vector_repo import CourseVectorRepository
    from storage.mysql.base import MySQLRepository
    from storage.redis.feature_repo import RedisFeatureRepository

    ab_engine = ABTestEngine()
    metrics_collector = MetricsCollector()
    supervisor = SupervisorOrchestrator(ab_engine=ab_engine)
    rec_graph = build_recommendation_graph()
    mysql_repo = MySQLRepository()
    redis_repo = RedisFeatureRepository()
    course_vector_repo = CourseVectorRepository(build_embedding_client(task_name=LLMTaskName.COURSE_RECALL))

    logger.info("runtime.init", supervisor=supervisor is not None)


def shutdown() -> None:
    """清理运行时资源。在 lifespan 关闭时调用。"""
    logger.info("runtime.shutdown")