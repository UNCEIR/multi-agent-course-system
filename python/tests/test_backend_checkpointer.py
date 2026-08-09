# -*- coding: utf-8 -*-
"""Backend 与异步 SQLite checkpointer 工厂测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_settings(tmp_path):
    settings = MagicMock()
    settings.memory_dir = ""
    settings.skills_dir = ""
    settings.checkpoint_sqlite_path = str(tmp_path / "checkpoint.db")
    with patch("agent.main.backend.get_settings", return_value=settings), patch(
        "agent.main.checkpointer.get_settings", return_value=settings
    ):
        yield settings


def test_build_main_backend_returns_composite_backend(mock_settings):
    from deepagents.backends import CompositeBackend

    from agent.main.backend import build_agent_backend, build_main_backend

    assert isinstance(build_agent_backend(), CompositeBackend)
    assert isinstance(build_main_backend(), CompositeBackend)


@pytest.mark.asyncio
async def test_build_checkpointer_returns_async_sqlite_saver(mock_settings, tmp_path):
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    from agent.main.checkpointer import build_checkpointer

    mock_settings.checkpoint_sqlite_path = str(tmp_path / "async.db")
    checkpointer = await build_checkpointer()
    assert isinstance(checkpointer, AsyncSqliteSaver)
    await checkpointer.conn.close()
