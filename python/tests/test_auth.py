# -*- coding: utf-8 -*-
"""轻量认证测试：密码 hash / token 签发校验 / 注册登录接口。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from auth.tokens import issue_token, verify_token
from storage.mysql.user_repo import UserRepository, hash_password, new_salt


class _FakeRow(dict):
    def __init__(self, **kw):
        super().__init__(kw)


class _FakeResult:
    def __init__(self, rows=None, first_row=None):
        self.rows = rows or []
        self.first_row = first_row

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
        self.executed.append((str(sql), params))
        return self.result

    def mappings(self):
        return self.result

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _mock_settings():
    s = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    s.auth_token_secret = "test-secret"
    s.auth_token_ttl_seconds = 3600
    return s


@pytest.fixture
def mock_settings():
    with patch("auth.tokens.get_settings", return_value=_mock_settings()):
        yield


def test_hash_password_deterministic_with_salt():
    salt = new_salt()
    assert len(salt) == 32
    h1 = hash_password("secret123", salt)
    h2 = hash_password("secret123", salt)
    assert h1 == h2
    assert h1 != hash_password("secret123", new_salt())


def test_issue_and_verify_token(mock_settings):
    token = issue_token("u1001", "student")
    payload = verify_token(token)
    assert payload == {"user_id": "u1001", "role": "student"}


def test_verify_token_rejects_tampered(mock_settings):
    token = issue_token("u1001", "student")
    tampered = token[:-2] + ("ab" if token[-2:] != "ab" else "cd")
    assert verify_token(tampered) is None


def test_verify_token_rejects_expired(mock_settings):
    with patch("auth.tokens.time.time", return_value=10_000_000):
        token = issue_token("u1001", "student")
    with patch("auth.tokens.time.time", return_value=10_000_000 + 7200):
        assert verify_token(token) is None


def test_user_repo_verify_password_flow():
    """user_repo：注册（SQL 参数含 hash/salt）→ 登录校验（正确/错误密码）。"""
    from unittest.mock import MagicMock

    repo = UserRepository()
    repo.ping = MagicMock(return_value=True)
    engine = MagicMock()
    repo._engine = engine

    # 注册：begin 事务，断言写入参数
    conn = MagicMock()
    conn.execute.return_value = MagicMock()
    engine.begin.return_value.__enter__ = MagicMock(return_value=conn)
    engine.begin.return_value.__exit__ = MagicMock(return_value=False)
    ok = repo.create_user(user_id="u1001", name="张三", role="student", password="secret123")
    assert ok is True
    inserted = conn.execute.call_args[0][1]
    assert inserted["uid"] == "u1001"
    assert inserted["role"] == "student"
    assert inserted["hash"] and inserted["salt"]

    # get_user：返回带 salt/hash 的行
    row = _FakeRow(
        user_id="u1001", name="张三", role="student",
        password_hash=hash_password("secret123", inserted["salt"]), salt=inserted["salt"],
    )
    repo._engine.connect = MagicMock(return_value=_FakeConn(_FakeResult(first_row=row)))

    user = repo.verify_password("u1001", "secret123")
    assert user == {"user_id": "u1001", "name": "张三", "role": "student"}
    assert repo.verify_password("u1001", "wrong-password") is None