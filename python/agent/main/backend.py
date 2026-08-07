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


def build_main_backend() -> CompositeBackend:
    """构建主 agent 的 CompositeBackend。

    skills/memories 走真实文件系统，其余走 state（conversation_history 等）。
    """
    s = get_settings()
    repo_root = Path(__file__).resolve().parent.parent.parent.parent  # <repo_root>

    memory_dir = s.memory_dir or str(repo_root / "python" / "memories")
    skills_dir = s.skills_dir or str(repo_root / "python" / "skills")

    return CompositeBackend(
        default=StateBackend(),
        routes={
            "/skills/": FilesystemBackend(root_dir=skills_dir),
            "/memories/": FilesystemBackend(root_dir=memory_dir),
        },
    )