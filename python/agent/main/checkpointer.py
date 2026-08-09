# -*- coding: utf-8 -*-
"""Checkpointer 工厂 — AsyncSqliteSaver（本地 sqlite 持久，支持 async）。

生命周期挂 runtime（启动建、关闭关）。Phase 3 切 RedisSaver。

注意：AsyncSqliteSaver 创建需要 async 上下文，因此 build_checkpointer 是 async 函数。
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import structlog
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from config import get_settings

logger = structlog.get_logger()


async def build_checkpointer() -> AsyncSqliteSaver:
    """构建 AsyncSqliteSaver checkpointer。

    使用 settings.checkpoint_sqlite_path 指定的路径（默认 <repo_root>/python/.checkpoint.db）。
    异步友好，支持 agent.ainvoke() 调用。
    """
    s = get_settings()
    path = s.checkpoint_sqlite_path
    if not path:
        # 默认：Python 包根目录下的 .checkpoint.db。
        python_root = Path(__file__).resolve().parents[2]
        path = str(python_root / ".checkpoint.db")
    conn = await aiosqlite.connect(path)
    logger.info("build_checkpointer", path=path)
    return AsyncSqliteSaver(conn)
