# -*- coding: utf-8 -*-
"""Backend 工厂 — CompositeBackend 按路径前缀路由。

- default: StateBackend() — 临时文件、conversation_history 走 LangGraph state
- /skills/: FilesystemBackend — 真实 python/skills/ 目录
- /memories/: FilesystemBackend — 真实 python/memories/ 目录
"""

from __future__ import annotations

from pathlib import Path

from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend

from config import get_settings


def build_agent_backend() -> CompositeBackend:
    """构建任意业务 agent 的 CompositeBackend。

    skills/memories 走真实文件系统，其余走 state（conversation_history 等）。
    """
    s = get_settings()
    python_root = Path(__file__).resolve().parents[2]  # <repo_root>/python or /app

    memory_dir = s.memory_dir or str(python_root / "memories")
    skills_dir = s.skills_dir or str(python_root / "skills")

    return CompositeBackend(
        default=StateBackend(),
        routes={
            "/skills/": FilesystemBackend(root_dir=skills_dir),
            "/memories/": FilesystemBackend(root_dir=memory_dir),
        },
    )


def build_main_backend() -> CompositeBackend:
    """兼容旧调用点；新业务 agent 统一使用 build_agent_backend。"""
    return build_agent_backend()
