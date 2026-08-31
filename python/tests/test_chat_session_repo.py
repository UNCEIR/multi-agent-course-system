# -*- coding: utf-8 -*-
"""chat 会话仓储测试：复合键、原子自增 seq、content_hash 去重、提取水位。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from storage.mysql.chat_session_repo import ChatSessionRepository


class _FakeRow(dict):
    """dict 子类，模拟 SQLAlchemy RowMapping（支持 dict(row) 与下标访问）。"""

    def __init__(self, **kw):
        super().__init__(kw)

    def get(self, k, d=None):
        return super().get(k, d)


class _FakeResult:
    def __init__(self, rows=None, first_row=None, rowcount=1):
        self.rows = rows or []
        self.first_row = first_row
        self.rowcount = rowcount

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.first_row


class _FakeConn:
    def __init__(self, result=None):
        self.result = result or _FakeResult()
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((str(sql)[:60], params))
        return self.result

    def mappings(self):
        return self.result

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def repo():
    r = ChatSessionRepository()
    r._engine = MagicMock()
    r.ping = MagicMock(return_value=True)
    conn = _FakeConn()
    r._engine.begin = MagicMock(return_value=conn)
    r._engine.connect = MagicMock(return_value=conn)
    return r


@pytest.mark.unit
def test_get_or_create_new_session(repo):
    row = _FakeRow(session_id="s1", user_id="u1", message_count=3, last_extracted_seq=1, status="active")
    repo._engine.begin = MagicMock(return_value=_FakeConn(_FakeResult(first_row=row)))
    result = repo.get_or_create_session("s1", "u1")
    assert result["message_count"] == 3


@pytest.mark.unit
def test_get_or_create_rejects_other_user(repo):
    """(session_id, user_id) 复合键：他人 user 命中 → 新开会话（防串会话）。"""
    row = _FakeRow(session_id="s1", user_id="OTHER", message_count=99, last_extracted_seq=0, status="active")
    repo._engine.begin = MagicMock(return_value=_FakeConn(_FakeResult(first_row=row)))
    result = repo.get_or_create_session("s1", "u1")
    assert result["message_count"] == 0  # 新会话


@pytest.mark.unit
def test_append_message_atomic_seq(repo):
    """事务内原子自增：seq = message_count + 1，且更新 count。"""
    repo._engine.begin = MagicMock(return_value=_FakeConn(_FakeResult(first_row=_FakeRow(message_count=5))))
    seq = repo.append_message("s1", "u1", "user", "你好")
    assert seq == 6


@pytest.mark.unit
def test_upsert_memory_dedup_by_hash(repo):
    """同内容（NFKC 归一后）→ 同一 content_hash（唯一键去重依据）。"""
    repo.upsert_memory_entry("u1", "fact", "用户喜欢Ａ课程", "s1")
    repo.upsert_memory_entry("u1", "fact", "用户喜欢A课程", "s1")  # 全角 A → NFKC
    calls = repo._engine.begin.return_value.executed
    hashes = [c[1]["hash"] for c in calls if c[1] and "hash" in c[1]]
    assert len(hashes) == 2
    assert hashes[0] == hashes[1]


@pytest.mark.unit
def test_count_unextracted(repo):
    row = _FakeRow(message_count=25, last_extracted_seq=5, last_failure_at=0)
    repo._engine.connect = MagicMock(return_value=_FakeConn(_FakeResult(first_row=row)))
    assert repo.count_unextracted("s1") == 20


@pytest.mark.unit
def test_ping_false_graceful(repo):
    repo.ping = MagicMock(return_value=False)
    assert repo.list_messages("s1") == []
    assert repo.list_memory_entries("u1") == []


@pytest.mark.unit
def test_list_sessions_by_user_returns_rows(repo):
    """按用户列会话：返回 active 会话（含 display_title 由 SQL 子查询决定）。"""
    row = _FakeRow(
        session_id="s1", title="", message_count=4,
        created_at=None, updated_at=None, display_title="帮我选课",
    )
    repo._engine.connect = MagicMock(return_value=_FakeConn(_FakeResult(rows=[row])))
    sessions = repo.list_sessions_by_user("u1")
    assert sessions[0]["session_id"] == "s1"
    assert sessions[0]["display_title"] == "帮我选课"


@pytest.mark.unit
def test_session_owner_returns_owner(repo):
    row = _FakeRow(user_id="u1")
    repo._engine.connect = MagicMock(return_value=_FakeConn(_FakeResult(first_row=row)))
    assert repo.session_owner("s1") == "u1"


@pytest.mark.unit
def test_rename_session_updates(repo):
    repo._engine.begin = MagicMock(return_value=_FakeConn())
    ok = repo.rename_session("s1", "u1", "新标题")
    assert ok is True
    assert "新标题" in str(repo._engine.begin.return_value.executed)


@pytest.mark.unit
def test_close_session_sets_closed(repo):
    repo._engine.begin = MagicMock(return_value=_FakeConn())
    ok = repo.close_session("s1", "u1")
    assert ok is True
    assert "status = 'closed'" in str(repo._engine.begin.return_value.executed)
    assert repo.count_unextracted("s1") == 0
