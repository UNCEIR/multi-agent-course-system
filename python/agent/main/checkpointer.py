# -*- coding: utf-8 -*-
"""Checkpointer 工厂 — SqliteSaver（本地 sqlite 持久）。

生命周期挂 runtime（启动建、关闭关）。Phase 3 切 RedisSaver。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from config import get_settings


def build_checkpointer() -> SqliteSaver:
    """构建 SqliteSaver checkpointer。

    使用 settings.checkpoint_sqlite_path 指定的路径（默认 <repo_root>/python/.checkpoint.db）。
    线程安全：check_same_thread=False。
    """
    s = get_settings()
    path = s.checkpoint_sqlite_path
    if not path:
        # 默认：<repo_root>/python/.checkpoint.db
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        path = str(repo_root / "python" / ".checkpoint.db")
    conn = sqlite3.connect(path, check_same_thread=False)
    return SqliteSaver(conn)