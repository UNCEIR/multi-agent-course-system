# -*- coding: utf-8 -*-
"""report_artifacts 仓储测试（mock MySQLRepository 基座）。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from storage.mysql.report_artifact_repo import ReportArtifactRepository


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
    r = ReportArtifactRepository()
    r._engine = MagicMock()
    r.ping = MagicMock(return_value=True)
    r._engine.begin = MagicMock(return_value=_FakeConn())
    r._engine.connect = MagicMock(return_value=_FakeConn())
    return r


@pytest.mark.unit
def test_create_artifact(repo):
    repo.create_artifact(batch_id="b1", student_id="1", student_name="张三", format="pdf", status="ok", file_key="b1/1.pdf")
    repo._engine.begin.assert_called_once()


@pytest.mark.unit
def test_list_by_batch(repo):
    repo._engine.connect = MagicMock(return_value=_FakeConn([{"batch_id": "b1", "student_id": "1"}]))
    rows = repo.list_by_batch("b1")
    assert rows and rows[0]["batch_id"] == "b1"


@pytest.mark.unit
def test_ping_false_returns_empty(repo):
    repo.ping = MagicMock(return_value=False)
    assert repo.list_by_batch("b1") == []
    assert repo.list_latest_by_student("1") == []
    assert repo.get_by_batch_student("b1", "1") is None
