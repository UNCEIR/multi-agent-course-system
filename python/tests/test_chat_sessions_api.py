# -*- coding: utf-8 -*-
"""chat 会话管理 API 测试：列表 / 消息回显（越权隔离）/ 重命名 / 软删。"""

from __future__ import annotations

from unittest.mock import patch

import pytest


class _FakeRepo:
    def __init__(self):
        self.sessions = [
            {"session_id": "s1", "title": "", "message_count": 4, "display_title": "帮我选课"},
            {"session_id": "s2", "title": "写作训练", "message_count": 2, "display_title": "写作训练"},
        ]
        self.messages = [
            {"seq": 1, "role": "user", "content": "你好"},
            {"seq": 2, "role": "assistant", "content": "你好！"},
        ]
        self.owner = {"s1": "u1", "s2": "u1"}
        self.renamed = []
        self.closed = []

    def list_sessions_by_user(self, user_id, limit=100):
        return self.sessions if user_id == "u1" else []

    def session_owner(self, session_id):
        return self.owner.get(session_id)

    def list_messages(self, session_id, after_seq=0, limit=500):
        return self.messages

    def rename_session(self, session_id, user_id, title):
        if self.owner.get(session_id) == user_id:
            self.renamed.append((session_id, title))
            return True
        return False

    def close_session(self, session_id, user_id):
        if self.owner.get(session_id) == user_id:
            self.closed.append(session_id)
            return True
        return False


@pytest.fixture
def client_with_repo():
    """patch 覆盖整个请求期（TestClient 惰性执行端点）。"""
    from fastapi.testclient import TestClient

    from agent.app import app

    repo = _FakeRepo()
    with patch("agent.runtime.chat_session_repo", repo):
        yield TestClient(app), repo


@pytest.mark.api
def test_list_sessions_returns_user_sessions(client_with_repo):
    client, _ = client_with_repo
    resp = client.get("/api/v1/chat/sessions", params={"user_id": "u1"})
    assert resp.status_code == 200
    sessions = resp.json()["data"]["sessions"]
    assert len(sessions) == 2
    assert sessions[0]["display_title"] == "帮我选课"


@pytest.mark.api
def test_list_messages_owned_session(client_with_repo):
    client, _ = client_with_repo
    resp = client.get("/api/v1/chat/sessions/s1/messages", params={"user_id": "u1"})
    assert resp.status_code == 200
    assert resp.json()["data"]["session_id"] == "s1"
    assert len(resp.json()["data"]["messages"]) == 2


@pytest.mark.api
def test_list_messages_other_user_forbidden(client_with_repo):
    """越权隔离：非归属用户读消息 → 403。"""
    client, _ = client_with_repo
    resp = client.get("/api/v1/chat/sessions/s1/messages", params={"user_id": "u2"})
    assert resp.status_code == 403


@pytest.mark.api
def test_rename_session_ok_and_forbidden(client_with_repo):
    client, repo = client_with_repo
    ok = client.post("/api/v1/chat/sessions/s1/rename", params={"user_id": "u1"}, json={"title": "新标题"})
    assert ok.status_code == 200
    assert repo.renamed == [("s1", "新标题")]
    forbid = client.post("/api/v1/chat/sessions/s1/rename", params={"user_id": "u2"}, json={"title": "x"})
    assert forbid.status_code == 403


@pytest.mark.api
def test_close_session_ok_and_forbidden(client_with_repo):
    client, repo = client_with_repo
    ok = client.delete("/api/v1/chat/sessions/s1", params={"user_id": "u1"})
    assert ok.status_code == 200
    assert repo.closed == ["s1"]
    forbid = client.delete("/api/v1/chat/sessions/s1", params={"user_id": "u2"})
    assert forbid.status_code == 403