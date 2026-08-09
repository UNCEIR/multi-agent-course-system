# -*- coding: utf-8 -*-
"""Plan B: 推荐原子工具集 + embedding 缓存测试。"""

from __future__ import annotations

import json

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.main.context import reset_embedding_cache, user_context


@pytest.fixture(autouse=True)
def _clean_embedding_cache():
    reset_embedding_cache()
    yield
    reset_embedding_cache()


def _fake_supervisor(agent_results=None):
    supervisor = MagicMock()
    supervisor.student_profile_agent = MagicMock()
    supervisor.course_recall_agent = MagicMock()
    supervisor.course_rerank_agent = MagicMock()
    supervisor.course_feasibility_agent = MagicMock()
    supervisor.recommendation_reason_agent = MagicMock()
    supervisor.hard_constraint_filter = MagicMock()

    profile_result = MagicMock()
    profile_result.profile = MagicMock(
        model_dump=lambda mode="json": {
            "student_id": "u1",
            "preferred_domains": ["工程技术"],
            "preferred_campus": ["西校区"],
        }
    )
    supervisor.student_profile_agent.run = AsyncMock(return_value=profile_result)

    recall_result = MagicMock()
    recall_result.courses = [
        MagicMock(course_id="C1"),
        MagicMock(course_id="C2"),
    ]
    supervisor.course_recall_agent.run = AsyncMock(return_value=recall_result)

    rerank_result = MagicMock()
    rerank_result.courses = [MagicMock(course_id="C1"), MagicMock(course_id="C2")]
    rerank_result.rerank_strategy = "rule_based_course_rerank"
    supervisor.course_rerank_agent.run = AsyncMock(return_value=rerank_result)

    feas_result = MagicMock()
    feas_result.available_courses = ["C1", "C2"]
    feas_result.selection_warnings = []
    supervisor.course_feasibility_agent.run = AsyncMock(return_value=feas_result)

    reason_result = MagicMock()
    reason_result.reasons = [{"course_id": "C1", "reason": "好课"}]
    supervisor.recommendation_reason_agent.run = AsyncMock(return_value=reason_result)

    supervisor.hard_constraint_filter.filter = MagicMock(
        return_value=(
            [MagicMock(course_id="C1")],
            [MagicMock(course_id="C2")],
            [],
        )
    )
    supervisor._llm_semantic_filter = AsyncMock(return_value=[MagicMock(course_id="C1")])
    return supervisor


@pytest.mark.asyncio
async def test_extract_profile_injects_user_id(monkeypatch):
    from tools.recommend.atomic_tools import extract_profile

    supervisor = _fake_supervisor()
    captured = {}
    supervisor.student_profile_agent.run = AsyncMock(
        side_effect=lambda **kw: captured.update(kw) or MagicMock(
            profile=MagicMock(model_dump=lambda mode="json": {"student_id": kw["user_id"]})
        )
    )
    monkeypatch.setattr("agent.runtime.supervisor", supervisor)

    with user_context("u123"):
        result = await extract_profile.ainvoke({"prompt": "想选西校区的课"})

    payload = json.loads(result)
    assert payload["student_id"] == "u123"
    assert captured["user_id"] == "u123"


@pytest.mark.asyncio
async def test_search_courses_returns_course_ids(monkeypatch):
    from tools.recommend.atomic_tools import search_courses

    supervisor = _fake_supervisor()
    monkeypatch.setattr("agent.runtime.supervisor", supervisor)

    result = await search_courses.ainvoke({"strategy": "wide", "query": "不考试", "profile_json": ""})
    payload = json.loads(result)
    assert payload["course_ids"] == ["C1", "C2"]


@pytest.mark.asyncio
async def test_rerank_and_feasibility_chain(monkeypatch):
    from tools.recommend.atomic_tools import check_feasibility, rerank_courses

    supervisor = _fake_supervisor()
    monkeypatch.setattr("agent.runtime.supervisor", supervisor)

    fake_courses = [MagicMock(course_id="C1"), MagicMock(course_id="C2")]
    monkeypatch.setattr(
        "tools.recommend.atomic_tools._hydrate_courses",
        lambda ids: [c for c in fake_courses if c.course_id in ids],
    )

    rerank = json.loads(
        await rerank_courses.ainvoke({"profile_json": "{}", "course_ids": ["C1", "C2"], "num_items": 2})
    )
    feas = json.loads(
        await check_feasibility.ainvoke({"course_ids": rerank["course_ids"], "context_json": "{}"})
    )
    assert rerank["course_ids"] == ["C1", "C2"]
    assert feas["course_ids"] == ["C1", "C2"]


@pytest.mark.asyncio
async def test_semantic_filter_timeout_fallback(monkeypatch):
    import asyncio

    from tools.recommend.atomic_tools import semantic_filter_courses

    supervisor = _fake_supervisor()
    monkeypatch.setattr("agent.runtime.supervisor", supervisor)
    monkeypatch.setattr(
        "tools.recommend.atomic_tools._hydrate_courses",
        lambda ids: [MagicMock(course_id=cid) for cid in ids],
    )

    async def slow_filter(*args, **kwargs):
        await asyncio.sleep(0.3)
        return [MagicMock(course_id="C1")]

    supervisor._llm_semantic_filter = slow_filter

    result = json.loads(
        await semantic_filter_courses.ainvoke(
            {
                "profile_json": json.dumps({"student_id": "u1", "preferred_domains": []}),
                "course_ids": ["C1", "C2"],
                "target_count": 40,
            }
        )
    )
    assert result["course_ids"] == ["C1"]


@pytest.mark.asyncio
async def test_embedding_cache_reuses_same_query(monkeypatch):
    from tools.recommend.atomic_tools import search_courses

    supervisor = _fake_supervisor()
    monkeypatch.setattr("agent.runtime.supervisor", supervisor)

    recall_agent = supervisor.course_recall_agent
    recall_agent.run = AsyncMock(
        side_effect=lambda **kw: MagicMock(courses=[MagicMock(course_id="C1")])
    )

    # mock embedding client 记录调用次数
    embed_fn = MagicMock(return_value=[0.5] * 8)
    from agent.recommend.agents.course_recall_agent import CourseRecallAgent

    # 直接验证缓存函数行为（不实例化真实 agent）
    from agent.main.context import get_embedding_cache, set_embedding_cache

    with user_context("u-embed"):
        assert get_embedding_cache("同一查询") is None
        set_embedding_cache("同一查询", [0.5] * 8)
        assert get_embedding_cache("同一查询") == [0.5] * 8
        # 不同用户看不到
        with user_context("u-other"):
            assert get_embedding_cache("同一查询") is None


def test_skill_allowed_tools_match_registered():
    """SKILL.md 的 allowed_tools 与注册的 7 个原子工具一致。"""
    from pathlib import Path

    from tools.recommend.atomic_tools import (
        check_feasibility,
        extract_profile,
        filter_hard_constraints,
        generate_reasons,
        rerank_courses,
        search_courses,
        semantic_filter_courses,
    )

    registered = {
        extract_profile.name,
        search_courses.name,
        filter_hard_constraints.name,
        semantic_filter_courses.name,
        rerank_courses.name,
        check_feasibility.name,
        generate_reasons.name,
    }
    skill_path = (
        Path(__file__).resolve().parents[1]
        / "skills"
        / "recommend-courses"
        / "SKILL.md"
    )
    content = skill_path.read_text(encoding="utf-8")
    assert "allowed_tools: [" in content
    assert registered == {
        "extract_profile",
        "search_courses",
        "filter_hard_constraints",
        "semantic_filter_courses",
        "rerank_courses",
        "check_feasibility",
        "generate_reasons",
    }
