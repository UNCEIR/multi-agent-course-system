# -*- coding: utf-8 -*-
"""chat_session_repo 真实 SQL 测试（SQLite 内存引擎）。

覆盖 FakeRepo mock 无法发现的问题：IN :contents 列表参数展开（expanding bindparam）。
SQLite 参数绑定行为与 MySQL 一致（同为 DBAPI 位置/命名绑定，expanding 由 SQLAlchemy 处理）。
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, text

from storage.mysql.chat_session_repo import ChatSessionRepository

DDL = """
CREATE TABLE chat_memory_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id VARCHAR(64) NOT NULL,
    agent_name VARCHAR(64) NOT NULL DEFAULT 'main_agent',
    kind VARCHAR(16) NOT NULL DEFAULT 'fact',
    content TEXT NOT NULL,
    content_hash CHAR(32) NOT NULL,
    source_session_id VARCHAR(64) NOT NULL DEFAULT '',
    expires_at DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, agent_name, kind, content_hash)
)
"""


@pytest.fixture
def sqlite_repo():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(DDL))
    repo = ChatSessionRepository()
    repo.ping = lambda: True
    repo._engine = engine
    return repo


def _seed(repo):
    with repo._engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO chat_memory_entries (user_id, kind, content, content_hash) VALUES "
                "(:uid, 'fact', :c1, 'h1'), (:uid, 'fact', :c2, 'h2'), (:uid, 'preference', :c3, 'h3')"
            ),
            {"uid": "u1", "c1": "同义条目 0", "c2": "同义条目 1", "c3": "偏好安静"},
        )


@pytest.mark.unit
def test_delete_memory_entries_expanding_list(sqlite_repo):
    """IN :contents 传列表：expanding bindparam 展开，真实执行不抛错且删除精确命中。"""
    _seed(sqlite_repo)
    repo = sqlite_repo
    repo.delete_memory_entries("u1", ["同义条目 0", "同义条目 1"])
    with repo._engine.connect() as conn:
        rows = conn.execute(text("SELECT content FROM chat_memory_entries WHERE user_id = 'u1'")).mappings().all()
    remaining = [r["content"] for r in rows]
    assert remaining == ["偏好安静"]


@pytest.mark.unit
def test_delete_memory_entries_empty_list_noop(sqlite_repo):
    _seed(sqlite_repo)
    sqlite_repo.delete_memory_entries("u1", [])
    with sqlite_repo._engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) AS c FROM chat_memory_entries")).mappings().first()["c"]
    assert count == 3


@pytest.mark.unit
def test_replace_memory_entries_delete_path_atomic(sqlite_repo):
    """原子替换（删除路径）：单事务删除旧内容（upsert 为空时仅删）。"""
    _seed(sqlite_repo)
    sqlite_repo.replace_memory_entries(
        "u1",
        delete_contents=["同义条目 0", "同义条目 1"],
        upsert_entries=[],
    )
    with sqlite_repo._engine.connect() as conn:
        rows = conn.execute(
            text("SELECT kind, content FROM chat_memory_entries WHERE user_id = 'u1'")
        ).mappings().all()
    by_content = {r["content"]: r["kind"] for r in rows}
    assert "同义条目 0" not in by_content and "同义条目 1" not in by_content
    assert "偏好安静" in by_content  # 无关条目不受影响


@pytest.mark.unit
def test_replace_memory_entries_upsert_params():
    """upsert 路径（MySQL ON DUPLICATE 语法，FakeConn 断言参数构造）：
    kind/content NFKC 归一 + md5 hash + source_session_id=consolidate。"""
    from unittest.mock import MagicMock

    repo = ChatSessionRepository()
    repo.ping = lambda: True
    engine = MagicMock()
    repo._engine = engine

    class _FakeResult:
        rowcount = 1

        def mappings(self):
            return self

        def all(self):
            return []

        def first(self):
            return None

    class _FakeConn:
        def __init__(self):
            self.executed = []

        def execute(self, sql, params=None):
            self.executed.append((str(sql), params))
            return _FakeResult()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    conn = _FakeConn()
    engine.begin.return_value = conn

    repo.replace_memory_entries(
        "u1",
        delete_contents=[],
        upsert_entries=[("fact", "偏好A课程"), ("fact", "偏好Ａ课程")],
    )
    upserts = [p for sql, p in conn.executed if p and "content" in p]
    assert len(upserts) == 2
    # NFKC 归一：全角Ａ → 半角 A，两行 hash 一致（MySQL 唯一键去重依据）
    assert upserts[0]["content"] == "偏好A课程"
    assert upserts[1]["content"] == "偏好A课程"
    assert upserts[0]["hash"] == upserts[1]["hash"]
    assert all(p["src"] == "consolidate" for p in upserts)


@pytest.mark.unit
def test_delete_memory_entries_nfkc_normalized(sqlite_repo):
    """删除前 NFKC 归一：全角字符内容也能精确命中半角存储值。"""
    _seed(sqlite_repo)
    with sqlite_repo._engine.begin() as conn:
        conn.execute(
            text("INSERT INTO chat_memory_entries (user_id, kind, content, content_hash) VALUES (:uid, 'fact', :c, 'h4')"),
            {"uid": "u1", "c": "偏好A课程"},
        )
    # 传入全角"Ａ"，NFKC 归一后应命中半角存储的"偏好A课程"
    sqlite_repo.delete_memory_entries("u1", ["偏好Ａ课程"])
    with sqlite_repo._engine.connect() as conn:
        hit = conn.execute(
            text("SELECT COUNT(*) AS c FROM chat_memory_entries WHERE content = '偏好A课程'")
        ).mappings().first()["c"]
        quiet = conn.execute(
            text("SELECT COUNT(*) AS c FROM chat_memory_entries WHERE content = '偏好安静'")
        ).mappings().first()["c"]
    assert hit == 0
    assert quiet == 1  # 无关条目不受影响

@pytest.mark.unit
def test_memory_entries_agent_name_isolation(sqlite_repo):
    """Phase 4 D6：同一用户不同 agent 的记忆点互相隔离（唯一键含 agent_name）。"""
    # SQLite 不支持 MySQL ON DUPLICATE，直接播种（唯一键含 agent_name 允许同内容跨 agent）
    with sqlite_repo._engine.begin() as conn:
        for agent, content in (("main_agent", "主 agent 偏好"), ("report_agent", "子 agent 偏好"), ("main_agent", "同义条目"), ("report_agent", "同义条目")):
            conn.execute(
                text(
                    "INSERT INTO chat_memory_entries (user_id, agent_name, kind, content, content_hash) "
                    "VALUES ('u1', :agent, 'fact', :content, :hash)"
                ),
                {"agent": agent, "content": content, "hash": __import__("hashlib").md5(content.encode("utf-8")).hexdigest()},
            )
    main_rows = sqlite_repo.list_memory_entries("u1", agent_name="main_agent")
    report_rows = sqlite_repo.list_memory_entries("u1", agent_name="report_agent")
    assert {r["content"] for r in main_rows} == {"主 agent 偏好", "同义条目"}
    assert {r["content"] for r in report_rows} == {"子 agent 偏好", "同义条目"}


# ── 记忆过期（TTL）：默认隐藏过期、include_expired 可见、delete_expired 物理清理 ──
@pytest.mark.unit
def test_expired_hidden_and_purged(sqlite_repo):
    """过期条目默认隐藏；include_expired 可见；delete_expired 物理清理（SQLite 引擎）。"""
    repo = sqlite_repo
    with repo._engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO chat_memory_entries (user_id, agent_name, kind, content, content_hash, source_session_id, expires_at) "
                "VALUES (:uid, 'main_agent', 'preference', :c1, 'e1', 's1', :exp1), "
                "(:uid, 'main_agent', 'fact', :c2, 'e2', 's1', NULL)"
            ),
            {"uid": "u2", "c1": "过期偏好", "exp1": "2000-01-01 00:00:00", "c2": "永不过期事实"},
        )
    # 默认读取：过期条目被隐藏
    active = repo.list_memory_entries("u2", agent_name="main_agent")
    assert [e["content"] for e in active] == ["永不过期事实"]
    # include_expired=True：能看到过期条目（供合并/审计）
    all_rows = repo.list_memory_entries("u2", agent_name="main_agent", include_expired=True)
    assert len(all_rows) == 2
    # 物理清理过期条目
    deleted = repo.delete_expired("u2", agent_name="main_agent")
    assert deleted == 1
    active_after = repo.list_memory_entries("u2", agent_name="main_agent", include_expired=True)
    assert [e["content"] for e in active_after] == ["永不过期事实"]

