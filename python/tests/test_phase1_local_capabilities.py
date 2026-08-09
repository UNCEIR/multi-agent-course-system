# -*- coding: utf-8 -*-
"""Phase 1 不依赖外部服务的能力验证。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.tools import tool


def test_parse_csv_and_chunk_document(tmp_path):
    from tools.documents import chunk_document, parse_document

    csv_path = tmp_path / "courses.csv"
    csv_path.write_text("name,campus\n算法,大学城\n", encoding="utf-8")

    text = parse_document.invoke({"file_path": str(csv_path), "file_type": "auto"})
    assert "算法 | 大学城" in text

    chunks = chunk_document.invoke(
        {"text": "第一段\n\n第二段", "chunk_size": 50, "chunk_overlap": 2, "strategy": "paragraph"}
    )
    assert [chunk["chunk_index"] for chunk in chunks] == [0]
    assert "第一段" in chunks[0]["text"]
    assert "第二段" in chunks[0]["text"]


def test_fixed_chunking_has_overlap():
    from tools.documents import chunk_document

    chunks = chunk_document.invoke(
        {"text": "abcdefghijklmnopqrstuvwxyz" * 5, "chunk_size": 50, "chunk_overlap": 5, "strategy": "fixed"}
    )
    assert chunks[0]["text"][-5:] == chunks[1]["text"][:5]


def test_registry_call_uses_circuit_breaker():
    from tools.registry import ToolRegistry

    registry = ToolRegistry(failure_threshold=2)

    @tool
    def echo(value: str) -> str:
        """Return the supplied value."""
        return value

    registry.register(echo)
    assert registry.call("echo", {"value": "ok"}) == "ok"
    assert registry.breaker_state("echo") == "closed"


@pytest.mark.asyncio
async def test_recommend_courses_delegates_to_v1_supervisor(monkeypatch):
    import importlib

    from agent.main.context import user_context
    from tools.recommend import recommend_courses

    module = importlib.import_module("tools.recommend.recommend_courses")
    supervisor = MagicMock()

    captured = {}

    async def fake_unified(request, mode="pipeline"):
        captured["user_id"] = request.user_id
        captured["mode"] = mode
        yield {"event": "phase", "data": {"phase": "start"}}
        yield {"event": "done", "data": {"courses": [], "selection_warnings": [], "experiment_group": "pipeline"}}

    supervisor.stream_recommend_unified = fake_unified
    monkeypatch.setattr(module.runtime, "supervisor", supervisor)

    with user_context("u1"):
        result = await recommend_courses.ainvoke({"query": "大学城 不考试", "num_items": 3})

    assert '"courses": []' in result
    assert '"experiment_group": "pipeline"' in result
    # user_id 从上下文注入到 RecommendationRequest
    assert captured["user_id"] == "u1"
    # 默认走 pipeline 模式（更快）
    assert captured["mode"] == "pipeline"
