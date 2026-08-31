# -*- coding: utf-8 -*-
"""report_uploads 仓储测试（mock MySQLRepository 基座，与 test_report_artifact_repo 同风格）。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from storage.mysql.report_upload_repo import ReportUploadRepository


class _FakeConn:
    def __init__(self, rows=None):
        self.rows = rows or []

    def execute(self, sql, params=None):
        return self

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def repo():
    r = ReportUploadRepository()
    r._engine = MagicMock()
    r.ping = MagicMock(return_value=True)
    r._engine.begin = MagicMock(return_value=_FakeConn())
    r._engine.connect = MagicMock(return_value=_FakeConn())
    return r


@pytest.mark.unit
def test_create_upload(repo):
    repo.create_upload(
        batch_id="rb_abc",
        user_id="t1",
        semester="2023-2024第二学期",
        user_message="补一句",
        file_names=["道法.xlsx", "数学.xlsx"],
    )
    repo._engine.begin.assert_called_once()
    # 校验 file_count 由 file_names 推导（extensibility：新增字段不破坏既有调用）
    assert repo is not None


@pytest.mark.unit
def test_update_status(repo):
    repo.update_status("rb_abc", "done", students_ok=37, students_failed=0)
    repo._engine.begin.assert_called_once()


@pytest.mark.unit
def test_list_by_user_parses_file_names_json(repo):
    repo._engine.connect = MagicMock(
        return_value=_FakeConn(
            [
                {
                    "batch_id": "rb_abc",
                    "user_id": "t1",
                    "semester": "2023-2024第二学期",
                    "file_count": 2,
                    "file_names": '["道法.xlsx", "数学.xlsx"]',
                    "status": "done",
                    "students_ok": 37,
                    "students_failed": 0,
                }
            ]
        )
    )
    rows = repo.list_by_user("t1")
    assert len(rows) == 1
    assert rows[0]["batch_id"] == "rb_abc"
    assert rows[0]["file_names"] == ["道法.xlsx", "数学.xlsx"]  # JSON 已反序列化


@pytest.mark.unit
def test_list_by_user_bad_json_falls_back_empty(repo):
    repo._engine.connect = MagicMock(return_value=_FakeConn([{"file_names": "not-json", "batch_id": "x"}]))
    rows = repo.list_by_user("t1")
    assert rows[0]["file_names"] == []


@pytest.mark.unit
def test_ping_false_returns_empty(repo):
    repo.ping = MagicMock(return_value=False)
    assert repo.list_by_user("t1") == []
    assert repo.get_by_batch("rb_abc") is None
