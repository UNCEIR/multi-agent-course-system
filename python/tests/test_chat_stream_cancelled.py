# -*- coding: utf-8 -*-
"""chat/stream 客户端断开（CancelledError）行为单测。

回归：客户端断开 / uvicorn cancel scope 传播到 `_generate` 时不应再把栈帧穿透
到 deepagents / langgraph / langsmith / tenacity 整条链路在 stderr 喷一整页 traceback。

修复点（2026-08-25）：
1. `api/chat.py` `chat_stream._generate` 增加 `except asyncio.CancelledError` 分支，
   info 级日志 + 不 yield 任何事件（流已被 cancel，yield 送不出去）。
2. `api/chat.py` `chat_stream._generate` finally 块的 `await persist_turn` 改为
   `asyncio.create_task(persist_turn)`（fire-and-forget），
   与本文件 L259 已有 `asyncio.create_task(maybe_extract(...))` 同模式。
3. `agent/recommend/supervisor.py` `stream_recommend` 增加
   `except asyncio.CancelledError` 分支，yield 一个 `error{CANCELLED}` 事件
   后 re-raise，让 SSE 流对客户端有明确收敛信号。
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_chat_generate_swallows_cancelled_and_schedules_persist():
    """chat_stream._generate 被 CancelledError 中断时不应抛异常到 stderr，
    且会触发 fire-and-forget persist_turn（不 await）。"""
    from api.chat import chat_stream
    from fastapi.testclient import TestClient

    from agent.app import app

    # 模拟 main_agent.astream_events：先 yield 2 个 token，然后模拟被 cancel
    async def _astream_events_then_cancel(*args, **kwargs):
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": MagicMock(content="你好")},
        }
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": MagicMock(content="世界")},
        }
        # 模拟 uvicorn 客户端断开：asyncio.CancelledError 沿 await 抛出
        await asyncio.sleep(0)
        raise asyncio.CancelledError()

    agent = MagicMock()
    agent.astream_events = _astream_events_then_cancel

    # FakeRepo：仅检测 persist_turn 调用（fire-and-forget 通过 asyncio.create_task）
    persist_calls: list[dict[str, Any]] = []

    async def _fake_persist(repo, **kwargs):
        persist_calls.append(kwargs)
        # 模拟慢操作；如果真的被 await，测试会变慢；fire-and-forget 立即返回
        await asyncio.sleep(0.5)

    class _FakeRepo:
        def session_lock(self, sid):
            class _L:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    return False

            return _L()

        def get_or_create_session(self, sid, uid):
            return {"message_count": 0}

        def get_extract_state(self, sid):
            return {"last_extracted_seq": 0, "last_failure_at": 0}

        def count_unextracted(self, sid):
            return 0

    with (
        patch("agent.runtime.main_agent", agent),
        patch("agent.runtime.chat_session_repo", _FakeRepo()),
        patch("agent.memory.injector.inject_memory_entries", new=AsyncMock(return_value=None)),
        patch("agent.memory.persistence.persist_turn", new=_fake_persist),
        patch("agent.memory.extractor.maybe_extract", new=AsyncMock(return_value=False)),
    ):
        client = TestClient(app)
        # 用 stream=True + iter_lines 消费 SSE；中途 break 等同客户端断开
        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={"message": "hi", "session_id": "s-cancel", "user_id": "u-cancel"},
        ) as resp:
            assert resp.status_code == 200
            # 读取前几个 SSE 事件后立刻关闭（模拟 client disconnect）
            chunks = []
            for line in resp.iter_lines():
                chunks.append(line)
                if len(chunks) >= 4:  # 收到一两条 token 后断开
                    break

    # 关键断言 1：测试不该因为 CancelledError 抛任何 fail
    # （TestClient 在 stream=True break 时正常返回，不会传播 server-side cancel）
    # 关键断言 2：fire-and-forget persist 在 finally 调度
    # 因为 create_task 是异步的，给 loop 一个 tick 让它启动
    await asyncio.sleep(0.05)
    # 验证 persist 被调了至少一次（_generate finally 块触发）
    assert len(persist_calls) >= 1, (
        "finally 块应至少调度一次 fire-and-forget persist_turn；"
        f"实际调用次数: {len(persist_calls)}"
    )
    # 验证 fire-and-forget 调用传入的 user_msg + assistant 内容正确（避免 finally
    # 块拿不到 collected 或 reply_so_far 拼错）
    assert persist_calls[0]["user_msg"] == "hi"
    assert persist_calls[0]["assistant_msgs"][0]["content"] == "你好世界"


@pytest.mark.asyncio
async def test_supervisor_stream_recommend_emits_cancelled_error_event():
    """supervisor.stream_recommend 在 gather 被取消时，yield error{CANCELLED}
    后 re-raise，让上层 SSE 流有结构化收敛信号。

    async generator 协议：第一次 __anext__ 取出 error{CANCELLED} 事件，
    第二次 __anext__ 抛出 CancelledError。"""
    from agent.recommend.supervisor import SupervisorOrchestrator
    from agent.recommend.agents.student_profile_agent import StudentProfileResult
    from agent.recommend.agents.course_recall_agent import CourseRecallResult
    from agent.recommend.agents.course_rerank_agent import CourseRerankResult
    from agent.recommend.agents.course_feasibility_agent import CourseFeasibilityResult
    from models.schemas import RecommendationRequest

    class _CancelAgent:
        """模拟 gather 内部被 cancel 的 agent。"""
        async def run(self, **kwargs):
            await asyncio.sleep(0.01)
            raise asyncio.CancelledError()

    class _StubAgent:
        def __init__(self, result):
            self._r = result

        async def run(self, **kwargs):
            return self._r

    orchestrator = SupervisorOrchestrator(
        student_profile_agent=_CancelAgent(),
        course_recall_agent=_StubAgent(
            CourseRecallResult(success=True, courses=[], recall_strategies=[])
        ),
        course_rerank_agent=_StubAgent(
            CourseRerankResult(success=True, courses=[], rerank_strategy="")
        ),
        course_feasibility_agent=_StubAgent(
            CourseFeasibilityResult(success=True, available_courses=[])
        ),
        recommendation_reason_agent=_StubAgent(None),
    )

    req = RecommendationRequest(user_id="S-cancel", num_items=3, prompt="p")

    events: list[dict[str, Any]] = []
    gen = orchestrator.stream_recommend(req)
    with pytest.raises(asyncio.CancelledError):
        async for event in gen:
            events.append(event)
            if event["event"] == "error" and event["data"].get("code") == "CANCELLED":
                # 收到结构化 cancelled 事件，继续 next() 取下一个值会触发 raise
                continue

    # 断言：必须至少收到一个 error{CANCELLED} 事件
    cancel_events = [
        e for e in events if e["event"] == "error" and e["data"].get("code") == "CANCELLED"
    ]
    assert len(cancel_events) == 1, (
        f"应发出 1 个 error{{code=CANCELLED}} 事件，实际 {len(events)} 个事件"
    )
    # 断言：携带 phase + request_id（便于前端 / 监控对账）
    assert cancel_events[0]["data"].get("phase") == "phase1"
    assert "request_id" in cancel_events[0]["data"]
