"""运行时单例容器。

管理所有全局单例（supervisor/repos/ab_engine/metrics/tool_registry）的生命周期。
ToolRegistry 在 build_main_agent 之前初始化，确保主 agent 能从注册中心获取工具。
"""

from __future__ import annotations

import sqlite3
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
mysql_repo: Any = None
redis_repo: Any = None
course_vector_repo: Any = None

# v2.0.0 主 agent 单例
main_agent: Any = None
_main_checkpointer_conn: sqlite3.Connection | None = None

# v2.0.0 ToolRegistry 单例
tool_registry: Any = None

# v2.0.0 知识库（学生手册/个人成绩单）仓储
document_vector_repo: Any = None
document_repo: Any = None


async def init() -> None:
    """初始化所有运行时单例。在 lifespan 启动时调用。"""
    global ab_engine, metrics_collector, supervisor
    global mysql_repo, redis_repo, course_vector_repo
    global main_agent, _main_checkpointer_conn, tool_registry
    global document_vector_repo, document_repo

    from ai.embedding_client import build_embedding_client
    from ai.llm_task_name import LLMTaskName
    from storage.milvus.course_vector_repo import CourseVectorRepository
    from storage.milvus.document_vector_repo import DocumentVectorRepository
    from storage.mysql.base import MySQLRepository
    from storage.mysql.document_repo import DocumentRepository
    from storage.redis.feature_repo import RedisFeatureRepository

    # ── v1 单例 ──────────────────────────────────────────────────────
    ab_engine = ABTestEngine()
    metrics_collector = MetricsCollector()
    supervisor = SupervisorOrchestrator(ab_engine=ab_engine)
    mysql_repo = MySQLRepository()
    redis_repo = RedisFeatureRepository()
    course_vector_repo = CourseVectorRepository(build_embedding_client(task_name=LLMTaskName.COURSE_RECALL))

    # ── v2.0.0 知识库仓储（学生手册/个人成绩单） ─────────────────────
    document_vector_repo = DocumentVectorRepository(
        build_embedding_client(task_name=LLMTaskName.QUERY_KNOWLEDGE)
    )
    document_repo = DocumentRepository()

    # ── v2.0.0 ToolRegistry（必须在 build_main_agent 之前初始化） ─────
    from tools import (
        ToolRegistry,
        check_feasibility,
        code_interpreter,
        compute_weighted_grade,
        extract_profile,
        filter_hard_constraints,
        generate_reasons,
        get_current_time,
        image_generate,
        list_available_skills,
        mindmap_generator,
        query_knowledge,
        recommend_courses,
        rerank_courses,
        search_courses,
        semantic_filter_courses,
        web_search,
        writing_assistant,
    )

    tool_registry = ToolRegistry()
    tool_registry.register_many([
        list_available_skills,
        get_current_time,
        recommend_courses,
        extract_profile,
        search_courses,
        filter_hard_constraints,
        semantic_filter_courses,
        rerank_courses,
        check_feasibility,
        generate_reasons,
        writing_assistant,
        web_search,
        image_generate,
        code_interpreter,
        mindmap_generator,
        compute_weighted_grade,
        query_knowledge,
    ])
    # 注册子包 tool（documents/）
    try:
        from tools.documents import chunk_document, parse_document
        tool_registry.register_many([parse_document, chunk_document])
    except Exception:
        logger.warning("runtime.init.documents_tools_not_available")

    # ── v2.0.0 主 agent（deepagents 记忆 + 意图识别 + 渐进式 skill） ──
    from agent.main import build_main_agent

    # 主 agent 只暴露已实装且面向对话的工具。
    # 推荐原子工具（extract_profile 等 7 个）不暴露给主 agent，避免它逐个串行调用变慢；
    # 推荐统一走 recommend_courses 一键工具（mode=pipeline，内部并行）。
    _main_agent_allowed = [
        "list_available_skills",
        "get_current_time",
        "recommend_courses",
        "query_knowledge",
        "parse_document",
        "chunk_document",
    ]
    main_agent = await build_main_agent(tools=tool_registry.get_all(allowed=_main_agent_allowed))
    # 保存 sqlite conn 引用以便 shutdown 时关闭
    # AsyncSqliteSaver 内部管理连接池，无需手动关闭
    _main_checkpointer_conn = None

    logger.info(
        "runtime.init",
        supervisor=supervisor is not None,
        main_agent=main_agent is not None,
        tool_registry_tools=len(tool_registry.list_tools()),
        document_vector_repo=document_vector_repo is not None,
    )


def shutdown() -> None:
    """清理运行时资源。在 lifespan 关闭时调用。"""
    global _main_checkpointer_conn

    if _main_checkpointer_conn is not None:
        try:
            _main_checkpointer_conn.close()
            logger.info("runtime.shutdown.checkpointer_closed")
        except Exception:
            logger.exception("runtime.shutdown.checkpointer_close_error")
        _main_checkpointer_conn = None

    logger.info("runtime.shutdown")