"""运行时单例容器。

管理所有全局单例（supervisor/repos/ab_engine/metrics/tool_registry）的生命周期。
ToolRegistry 在 build_main_agent 之前初始化，确保主 agent 能从注册中心获取工具。
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
mysql_repo: Any = None
redis_repo: Any = None
course_vector_repo: Any = None

# v2.0.0 主 agent 单例
main_agent: Any = None

# v2.0.0 ToolRegistry 单例
tool_registry: Any = None

# v2.0.0 知识库（学生手册/个人成绩单）仓储
document_vector_repo: Any = None
document_repo: Any = None


async def init() -> None:
    """初始化所有运行时单例。在 lifespan 启动时调用。"""
    global ab_engine, metrics_collector, supervisor
    global mysql_repo, redis_repo, course_vector_repo
    global main_agent, tool_registry
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
    # 主 agent 工具白名单由 MAIN_AGENT_SPEC.allowed_tools 声明（specs.py），
    # factory 在 tools=None 时从 registry 按白名单取；此处不传 tools。
    from agent.main import build_main_agent

    main_agent = await build_main_agent()

    logger.info(
        "runtime.init",
        supervisor=supervisor is not None,
        main_agent=main_agent is not None,
        tool_registry_tools=len(tool_registry.list_tools()),
        document_vector_repo=document_vector_repo is not None,
    )


def shutdown() -> None:
    """清理运行时资源。在 lifespan 关闭时调用。

    当前无外部连接需显式关闭：AsyncSqliteSaver 内部管理连接池，
    MySQL/Redis/Milvus/embedding 客户端由进程退出时回收。
    若未来引入需要显式关闭的资源（如长连接池），在此补充。
    """
    logger.info("runtime.shutdown")