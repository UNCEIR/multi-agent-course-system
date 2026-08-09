# -*- coding: utf-8 -*-
"""query_knowledge 工具测试（mock 仓储 + 用户上下文注入）。"""

from __future__ import annotations

import json

from unittest.mock import MagicMock, patch

import pytest

from agent.main.context import user_context


@pytest.fixture
def runtime_with_repo():
    import agent.runtime  # noqa: F401  确保 agent.runtime 模块属性存在

    repo = MagicMock()
    repo.embedding_client = MagicMock()
    repo.embedding_client.embed_text.return_value = [0.0] * 8
    doc_repo = MagicMock()
    doc_repo.get_chunk_contents.return_value = {}
    with patch("agent.runtime.document_vector_repo", repo), patch("agent.runtime.document_repo", doc_repo):
        yield repo, doc_repo


@pytest.mark.asyncio
async def test_query_knowledge_public_question(runtime_with_repo):
    from tools.knowledge.query_knowledge import query_knowledge

    repo, doc_repo = runtime_with_repo
    repo.search.return_value = [
        {
            "chunk_id": "handbook:0",
            "source_doc_name": "广东工业大学2025年学生手册.pdf",
            "page_number": 12,
            "section": "奖学金评定办法",
            "user_id": "public",
            "distance": 0.1,
        }
    ]
    doc_repo.get_chunk_contents.return_value = {
        "handbook:0": {"content": "综合测评成绩为奖学金评定依据。", "page_number": 12}
    }

    with user_context("u123"):
        result = await query_knowledge.ainvoke({"query": "奖学金怎么评", "top_k": 5})

    payload = json.loads(result)
    assert payload["matches"][0]["user_scope"] == "public"
    assert payload["matches"][0]["page_number"] == 12
    assert "综合测评" in payload["matches"][0]["content"]
    repo.search.assert_called_once()
    _, kwargs = repo.search.call_args
    # user_id 从上下文注入，检索 public + 当前用户分区
    assert kwargs["user_ids"] == ["public", "u123"]


@pytest.mark.asyncio
async def test_query_knowledge_personal_question_only_own_partition(runtime_with_repo):
    from tools.knowledge.query_knowledge import query_knowledge

    repo, _ = runtime_with_repo
    repo.search.return_value = []

    with user_context("u456"):
        result = await query_knowledge.ainvoke({"query": "我修过哪些课", "top_k": 5})

    payload = json.loads(result)
    assert payload["matches"] == []
    _, kwargs = repo.search.call_args
    # 仅本人分区 + 公开分区，不泄露他人
    assert kwargs["user_ids"] == ["public", "u456"]


@pytest.mark.asyncio
async def test_query_knowledge_anonymous_only_public(runtime_with_repo):
    from tools.knowledge.query_knowledge import query_knowledge

    repo, _ = runtime_with_repo
    repo.search.return_value = []

    # 未登录（无 user_context）只检索公开分区
    result = await query_knowledge.ainvoke({"query": "宿舍规定", "top_k": 5})

    json.loads(result)
    _, kwargs = repo.search.call_args
    assert kwargs["user_ids"] == ["public"]


@pytest.mark.asyncio
async def test_query_knowledge_repo_unavailable():
    import agent.runtime  # noqa: F401

    from tools.knowledge.query_knowledge import query_knowledge

    with patch("agent.runtime.document_vector_repo", None):
        result = await query_knowledge.ainvoke({"query": "任何问题"})

    payload = json.loads(result)
    assert "error" in payload
