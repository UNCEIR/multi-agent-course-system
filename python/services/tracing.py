"""LangSmith tracing 配置激活。

在项目启动最早期（main.py 模块顶部，远早于任何 langchain 相关 import）调用
configure_langsmith_tracing()，把 settings.langchain_* 映射为标准 LANGCHAIN_* /
LANGSMITH_* 环境变量。之后所有走 langchain 回调机制的 LLM/Embedding 调用都会自动
上报到 LangSmith。

AOP 设计：三个单点覆盖全链路
  - 配置激活层（本文件）—— 启动时一次性写入 env
  - LLM 工厂（services/llm_client.py）—— 所有 ChatOpenAI 统一入口
  - Embedding 工厂（services/embedding_client.py）—— OpenAIEmbeddings + @traceable
后续新增 LLM 功能只要走工厂，零侵入即被监控。
"""

from __future__ import annotations

import os
from typing import Any

import structlog

from config import get_settings

logger = structlog.get_logger()

_NAMESPACES = ("LANGCHAIN", "LANGSMITH")


def _make_mapping(settings: Any) -> dict[str, str | None]:
    """把 settings.langchain_* 映射为双命名空间的环境变量名。"""
    return {
        "API_KEY": settings.langchain_api_key or None,
        "ENDPOINT": settings.langchain_endpoint or None,
        "PROJECT": settings.langchain_project or None,
        "TRACING_V2": "true" if settings.langchain_tracing_v2 else "false",
    }


def configure_langsmith_tracing() -> dict[str, str]:
    """把 settings.langchain_* 写入 LANGCHAIN_* 和 LANGSMITH_* 两套环境变量。

    os.environ.setdefault 语义：允许外部 CI/CD 或宿主机已设置的标准环境变量
    覆盖 .env 值。仅在 env 未设置时才写入 settings 的值。

    调用时机：必须在 import langchain / langchain_openai 之前（main.py 最顶部），
    避免 langsmith.utils.get_env_var 的 lru_cache 在 env 就位前冻结。
    """
    settings = get_settings()
    base = _make_mapping(settings)

    configured: dict[str, str] = {}
    for base_name, value in base.items():
        if value is None:
            continue
        stripped = str(value).strip()
        if base_name != "TRACING_V2" and not stripped:
            continue
        for ns in _NAMESPACES:
            env_name = f"{ns}_{base_name}"
            os.environ.setdefault(env_name, stripped)
            if env_name not in configured:
                configured[env_name] = stripped

    enabled = settings.langchain_tracing_v2 and bool(
        (settings.langchain_api_key or "").strip()
    )
    logger.info(
        "langsmith.tracing_configured",
        enabled=enabled,
        project=settings.langchain_project or None,
        endpoint=settings.langchain_endpoint or None,
        keys_set=list(configured.keys()),
    )
    return configured


def get_tracing_status() -> dict[str, Any]:
    """返回当前 tracing 状态，供 /health 暴露，便于诊断"为什么没有 trace"。

    不依赖 settings（读的是运行时 os.environ），反映真实生效状态。
    """
    api_key_set = bool(
        os.environ.get("LANGSMITH_API_KEY", "").strip()
        or os.environ.get("LANGCHAIN_API_KEY", "").strip()
    )
    tracing_v2 = os.environ.get("LANGSMITH_TRACING_V2", "").strip() or os.environ.get(
        "LANGCHAIN_TRACING_V2", ""
    ).strip()
    project = os.environ.get("LANGSMITH_PROJECT", "").strip() or os.environ.get(
        "LANGCHAIN_PROJECT", ""
    ).strip()
    endpoint = os.environ.get("LANGSMITH_ENDPOINT", "").strip() or os.environ.get(
        "LANGCHAIN_ENDPOINT", ""
    ).strip()

    return {
        "enabled": tracing_v2 == "true" and api_key_set,
        "tracing_v2": tracing_v2,
        "project": project or None,
        "endpoint": endpoint or None,
        "api_key_configured": api_key_set,
    }
