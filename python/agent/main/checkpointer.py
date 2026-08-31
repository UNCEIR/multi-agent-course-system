# -*- coding: utf-8 -*-
"""Checkpointer 工厂 — 默认 AsyncSqliteSaver（本地 sqlite 持久，支持 async）。

生命周期挂 runtime（启动建、关闭关）。

backend 策略（决策 20，2026-08-16）：
- settings.checkpoint_backend = "sqlite"（默认）：AsyncSqliteSaver，单实例语义最强
- settings.checkpoint_backend = "redis"：仅当 python-api 实例数 > 1（滚动/水平扩容）时
  才允许启用 langgraph-checkpoint-redis；本仓库默认单实例，保持 sqlite。
  依赖未安装时显式 RuntimeError，避免静默回退造成会话恢复假象。

注意：AsyncSqliteSaver 创建需要 async 上下文，因此 build_checkpointer 是 async 函数。
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import structlog
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from config import get_settings

logger = structlog.get_logger()


async def build_checkpointer():
    """按 settings.checkpoint_backend 构建 checkpointer（默认 sqlite）。"""
    s = get_settings()
    backend = (s.checkpoint_backend or "sqlite").strip().lower()
    if backend == "redis":
        return await _build_redis_checkpointer(s)
    return await _build_sqlite_checkpointer(s)


async def _build_sqlite_checkpointer(s):
    path = s.checkpoint_sqlite_path
    if not path:
        # 默认：Python 包根目录下的 .checkpoint.db。
        python_root = Path(__file__).resolve().parents[2]
        path = str(python_root / ".checkpoint.db")
    conn = await aiosqlite.connect(path)
    logger.info("build_checkpointer", backend="sqlite", path=path)
    return AsyncSqliteSaver(conn)


async def _build_redis_checkpointer(s):
    """RedisSaver 分支（决策 20 条件：实例数 > 1 时才启用）。

    依赖 langgraph-checkpoint-redis 未安装 → 显式报错，不静默回退 sqlite。
    """
    try:
        from langgraph.checkpoint.redis.aio import AsyncRedisSaver
    except ImportError:
        raise RuntimeError(
            "checkpoint_backend=redis 但未安装 langgraph-checkpoint-redis。"
            "仅当 python-api 实例数 > 1（滚动/水平扩容）时启用（决策 20）；"
            "单实例请保持 checkpoint_backend=sqlite。"
        )
    logger.info("build_checkpointer", backend="redis")
    return AsyncRedisSaver.from_conn_string(s.redis_url)
