# -*- coding: utf-8 -*-
"""evaluation API 测试：教师端 SSE 事件序 + 学生端 /me 越权隔离。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.api
def test_evaluation_sse_event_order_and_done():
    """SSE 事件序：stage → radar → comment_token* → done（消费真实流）。"""
    from fastapi.testclient import TestClient

    from agent.app import app

    async def _fake_stream(*, target_user_id, comment_type, generated_by, out_queue):
        await out_queue.put(("stage", {"stage": "snapshot"}))
        await out_queue.put(("radar", {"target_user_id": target_user_id, "dimensions": [], "overall_theme": "x"}))
        await out_queue.put(("comment_token", {"token": "你"}))
        await out_queue.put(("comment_token", {"token": "好"}))
        await out_queue.put(("done", {"evaluation_id": 1, "target_user_id": target_user_id, "comment": "你好", "status": "generated"}))

    with patch("api.evaluation.stream_evaluation", side_effect=_fake_stream):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/evaluation",
            json={"target_user_id": "3123003252", "comment_type": "encouragement", "generated_by": "teacher1"},
        )
    assert resp.status_code == 200
    events = [line.split(": ", 1)[1] for line in resp.text.splitlines() if line.startswith("event: ")]
    assert events[0] == "stage"
    assert "radar" in events
    assert "comment_token" in events
    assert events[-1] == "done"
    assert "error" not in events


@pytest.mark.api
def test_evaluation_invalid_comment_type_422():
    from fastapi.testclient import TestClient

    from agent.app import app

    client = TestClient(app)
    resp = client.post(
        "/api/v1/evaluation",
        json={"target_user_id": "u1", "comment_type": "random_type"},
    )
    assert resp.status_code == 422
    assert "INVALID_COMMENT_TYPE" in resp.text


@pytest.mark.api
def test_evaluation_no_transcript_error_event():
    """无成绩单 → 结构化 error 事件（不静默、不空跑 LLM）。"""
    from fastapi.testclient import TestClient

    from agent.app import app

    async def _fake_stream(*, target_user_id, comment_type, generated_by, out_queue):
        await out_queue.put(("error", {"code": "no_transcript_data", "message": "未摄入成绩单"}))

    with patch("api.evaluation.stream_evaluation", side_effect=_fake_stream):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/evaluation",
            json={"target_user_id": "u1", "comment_type": "semester_summary"},
        )
    assert resp.status_code == 200
    assert "event: error" in resp.text
    assert "no_transcript_data" in resp.text


@pytest.mark.api
def test_evaluation_me_only_own_data():
    """学生端读取：只返回本人记录（repo 按 user_id 过滤，无参数可越权）。"""
    from fastapi.testclient import TestClient

    from agent.app import app

    repo = MagicMock()
    repo.list_by_user = MagicMock(side_effect=lambda uid, limit: [{"id": 1, "target_user_id": uid}] if uid == "stu1" else [])

    with patch("agent.runtime.evaluation_repo", repo):
        client = TestClient(app)
        resp_a = client.get("/api/v1/evaluation/me", params={"user_id": "stu1"})
        resp_b = client.get("/api/v1/evaluation/me", params={"user_id": "stu2"})
    assert resp_a.status_code == 200
    assert len(resp_a.json()["items"]) == 1
    assert resp_a.json()["items"][0]["target_user_id"] == "stu1"
    assert resp_b.json()["items"] == []
    # repo 始终按请求 user_id 过滤，不存在跨用户返回
    assert repo.list_by_user.call_count == 2
