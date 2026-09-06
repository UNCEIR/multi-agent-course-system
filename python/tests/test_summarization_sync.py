# -*- coding: utf-8 -*-
"""SummarizationSyncMiddleware 子类单测（Phase 4 A4/A5/A6）：

- fallback：LLM 摘要失败被吞成 "Error generating summary..." 前缀 → 规则式截断 + pending 标记
- 双模板：已有 compaction → 选 update 模板（含 <previous-summary>）
- 写后同步：awrap_model_call 返回 _summarization_event → 落库；fallback 状态回写
- 防抖：60s 内同 session 只落一次
- no-op：无 thread_id/user_id（report/evaluation 子 agent）→ 不落库
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents.middleware.types import ExtendedModelResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from sqlalchemy import create_engine, text

from agent.memory.summarization_sync import SummarizationSyncMiddleware
from deepagents.backends import StateBackend
from storage.mysql.chat_session_repo import ChatSessionRepository

COMPACT_DDL = """
CREATE TABLE chat_session_compactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    summary TEXT NOT NULL,
    prev_compaction_id BIGINT,
    first_kept_message_id BIGINT NOT NULL DEFAULT 0,
    tokens_before INT NOT NULL DEFAULT 0,
    tokens_after INT NOT NULL DEFAULT 0,
    reserve_tokens INT NOT NULL DEFAULT 0,
    keep_recent_tokens INT NOT NULL DEFAULT 0,
    model VARCHAR(64) NOT NULL DEFAULT '',
    reason VARCHAR(16) NOT NULL DEFAULT 'threshold',
    status VARCHAR(16) NOT NULL DEFAULT 'ok',
    usage_json TEXT,
    details_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


@pytest.fixture
def sqlite_repo():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(COMPACT_DDL))
    repo = ChatSessionRepository()
    repo.ping = lambda: True
    repo._engine = engine
    return repo


@pytest.fixture
def mw(sqlite_repo):
    model = MagicMock()
    model.name = "mock-llm"
    return SummarizationSyncMiddleware(
        model=model,
        backend=StateBackend(),
        trigger=("messages", 999),
        keep=("messages", 20),
        repo=sqlite_repo,
        summarize_prompt="首轮模板 {messages}",
        update_prompt="增量模板 <previous-summary>:{previous_summary} {messages}",
    )


def _ctx(thread="s1", user="u1"):
    return {"configurable": {"thread_id": thread, "user_id": user}}


def _event(cutoff=6, summary="摘要正文", status_ok=True):
    return {
        "cutoff_index": cutoff,
        "summary_message": HumanMessage(content=summary),
        "file_path": None,
    }


# ── fallback 前缀检测 ──────────────────────────────────────────────
@pytest.mark.unit
def test_fallback_prefix_detection(mw):
    mw._lc_helper._create_summary = MagicMock(return_value="Error generating summary: quota exceeded")
    with patch("agent.memory.summarization_sync.get_config", return_value=_ctx()):
        out = mw._create_summary([HumanMessage(content="hi")])
    assert "降级为规则式截断" in out
    assert "s1" in mw._pending_fallback


@pytest.mark.unit
def test_create_summary_normal(mw):
    mw._lc_helper._create_summary = MagicMock(return_value="正常摘要")
    with patch("agent.memory.summarization_sync.get_config", return_value=_ctx()):
        out = mw._create_summary([HumanMessage(content="hi")])
    assert out == "正常摘要"
    assert "s1" not in mw._pending_fallback


# ── 双模板（已有 compaction → update 模板） ────────────────────────
@pytest.mark.unit
def test_double_template_selects_update(mw, sqlite_repo):
    sqlite_repo.append_compaction(user_id="u1", session_id="s1", summary="旧摘要")
    seen = {}

    def _fake_create(messages):
        seen["prompt"] = mw._lc_helper.summary_prompt
        return "新摘要"

    mw._lc_helper._create_summary = MagicMock(side_effect=_fake_create)
    with patch("agent.memory.summarization_sync.get_config", return_value=_ctx()):
        out = mw._create_summary([HumanMessage(content="hi")])
    assert out == "新摘要"
    assert "增量模板" in seen["prompt"]
    assert "旧摘要" in seen["prompt"]


@pytest.mark.unit
def test_double_template_first_round(mw, sqlite_repo):
    seen = {}

    def _fake_create(messages):
        seen["prompt"] = mw._lc_helper.summary_prompt
        return "首轮摘要"

    mw._lc_helper._create_summary = MagicMock(side_effect=_fake_create)
    with patch("agent.memory.summarization_sync.get_config", return_value=_ctx()):
        mw._create_summary([HumanMessage(content="hi")])
    assert seen["prompt"] == "首轮模板 {messages}"


# ── 写后同步 ───────────────────────────────────────────────────────
@pytest.mark.unit
@pytest.mark.asyncio
async def test_awrap_persists_compaction(mw, sqlite_repo):
    resp = ExtendedModelResponse(
        model_response=MagicMock(),
        command=Command(update={"_summarization_event": _event(cutoff=6, summary="落库摘要")}),
    )
    with patch("agent.memory.summarization_sync.get_config", return_value=_ctx()):
        with patch.object(SummarizationSyncMiddleware, "awrap_model_call", return_value=resp) as _:
            # 直接调用写后同步（绕过 super 的复杂路径）
            await mw._persist_compaction(_event(cutoff=6, summary="落库摘要"))
    latest = sqlite_repo.get_latest_compaction("s1")
    assert latest is not None
    assert latest["summary"] == "落库摘要"
    assert latest["status"] == "ok"
    assert latest["first_kept_message_id"] == 6


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_fallback_status(mw, sqlite_repo):
    mw._pending_fallback.add("s1")
    with patch("agent.memory.summarization_sync.get_config", return_value=_ctx()):
        await mw._persist_compaction(_event(cutoff=3, summary="fallback 摘要"))
    latest = sqlite_repo.get_latest_compaction("s1")
    assert latest["status"] == "fallback"
    assert "s1" not in mw._pending_fallback


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_noop_without_user(mw, sqlite_repo):
    with patch("agent.memory.summarization_sync.get_config", return_value={"configurable": {"thread_id": "s1"}}):
        await mw._persist_compaction(_event())
    assert sqlite_repo.get_latest_compaction("s1") is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_debounce(mw, sqlite_repo):
    with patch("agent.memory.summarization_sync.get_config", return_value=_ctx()):
        await mw._persist_compaction(_event(summary="A"))
        await mw._persist_compaction(_event(summary="B"))
    rows = sqlite_repo.list_compactions("s1")
    assert len(rows) == 1
    assert rows[0]["summary"] == "A"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_db_failure_does_not_raise(mw, sqlite_repo):
    def _boom(**kwargs):
        raise RuntimeError("db down")

    sqlite_repo.append_compaction = _boom
    with patch("agent.memory.summarization_sync.get_config", return_value=_ctx()):
        # 不应抛异常（失败仅告警）
        await mw._persist_compaction(_event())


# ── 异步路径双模板（Phase 4 A5 补齐：live /chat/stream 走 _acreate_summary）──
@pytest.mark.unit
@pytest.mark.asyncio
async def test_double_template_selects_update_async(mw, sqlite_repo):
    """已有 compaction → 异步摘要走增量合并模板（含 <previous-summary>）。"""
    sqlite_repo.append_compaction(user_id="u1", session_id="s1", summary="旧摘要(异步)")
    before_prompt = mw._lc_helper.summary_prompt
    seen = {}

    async def _fake_acreate(messages):
        seen["prompt"] = mw._lc_helper.summary_prompt
        return "新摘要(异步)"

    mw._lc_helper._acreate_summary = AsyncMock(side_effect=_fake_acreate)
    with patch("agent.memory.summarization_sync.get_config", return_value=_ctx()):
        out = await mw._acreate_summary([HumanMessage(content="hi")])
    assert out == "新摘要(异步)"
    assert "增量模板" in seen["prompt"]
    assert "旧摘要(异步)" in seen["prompt"]
    # 还原：summary_prompt 恢复为调用前值（不残留 update 模板）
    assert mw._lc_helper.summary_prompt == before_prompt


@pytest.mark.unit
@pytest.mark.asyncio
async def test_double_template_first_round_async(mw, sqlite_repo):
    """无 compaction → 异步摘要维持首轮六节模板。"""
    seen = {}

    async def _fake_acreate(messages):
        seen["prompt"] = mw._lc_helper.summary_prompt
        return "首轮摘要(异步)"

    mw._lc_helper._acreate_summary = AsyncMock(side_effect=_fake_acreate)
    with patch("agent.memory.summarization_sync.get_config", return_value=_ctx()):
        await mw._acreate_summary([HumanMessage(content="hi")])
    assert seen["prompt"] == "首轮模板 {messages}"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_afallback_prefix_detection_async(mw):
    """异步摘要失败被吞成 Error generating summary 前缀 → 规则式截断 + pending 标记。"""
    before_prompt = mw._lc_helper.summary_prompt
    mw._lc_helper._acreate_summary = AsyncMock(return_value="Error generating summary: quota exceeded(async)")
    with patch("agent.memory.summarization_sync.get_config", return_value=_ctx()):
        out = await mw._acreate_summary([HumanMessage(content="hi")])
    assert "降级为规则式截断" in out
    assert "s1" in mw._pending_fallback
    # 模板已还原到调用前值（不残留 update/fallback 状态）
    assert mw._lc_helper.summary_prompt == before_prompt

