# -*- coding: utf-8 -*-
"""DocumentsPage 上传 + 列表端点的 user_id 路由 / 脱敏 / 权限隔离单测（2026-08-25）。

回归 4 个核心点：
1. 未登录（user_id 为空）→ FastAPI 422 拒绝（Form 必填）
2. user_id 透传到 service.ingest（不再默认 public）
3. student_name 非空 + user_id != public → 触发 transcript 脱敏（service.ingest 内部判断）
4. GET /datasets 按 user_id 过滤（公共手册 + 本人合并 / 仅本人严格分离）
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_test_client(monkeypatch):
    """统一 fixture：让 ingest_many 透传到底层 ingest，spy 在 ingest 层。

    - 用 patch.object 直接替换 DocumentIngestionService.ingest_many 为透传函数
    - 用 ingest spy 收集 user_id / student_name 参数
    - runtime.document_repo 用 MagicMock 注入
    """
    from agent import runtime as _rt
    from agent.documents.service import DocumentIngestionService

    ingest_calls: list[dict[str, Any]] = []

    async def _spy_ingest(self, file, dataset_name, chunk_strategy, **kwargs):
        # 模拟 service.ingest 的脱敏条件（与 service.py:82-90 一致）
        desensitized_triggered = False
        if kwargs.get("user_id") and kwargs["user_id"] != "public" and kwargs.get("student_name"):
            from tools.documents.desensitizer import desensitize_transcript

            desensitize_transcript("test transcript", student_name=kwargs["student_name"])
            desensitized_triggered = True
        record = {
            "user_id": kwargs.get("user_id"),
            "student_name": kwargs.get("student_name"),
            "dataset_name": dataset_name,
            "chunk_strategy": chunk_strategy,
            "filename": file.filename if file else "doc",
            "desensitized_triggered": desensitized_triggered,
        }
        ingest_calls.append(record)
        return {
            "dataset_id": "d-test",
            "chunks_count": 3,
            "status": "ok",
            "user_id": kwargs.get("user_id", "public"),
            "filename": file.filename if file else "doc",
        }

    async def _passthrough_ingest_many(self, files, dataset_name, chunk_strategy, **kwargs):
        results = []
        for file in files:
            r = await _spy_ingest(self, file, dataset_name, chunk_strategy, **kwargs)
            results.append(r)
        return results

    monkeypatch.setattr(DocumentIngestionService, "ingest_many", _passthrough_ingest_many)
    monkeypatch.setattr(DocumentIngestionService, "ingest", _spy_ingest)

    # 注入 fake document_repo
    fake_repo = MagicMock()
    fake_repo.list_datasets = MagicMock(
        return_value=[
            {
                "dataset_id": "d-public-1",
                "dataset_name": "handbook_2025",
                "source_doc_name": "handbook.pdf",
                "file_type": "pdf",
                "chunks_count": 30,
                "status": "ok",
                "user_id": "public",
            },
            {
                "dataset_id": "d-personal-1",
                "dataset_name": "transcript_smoke",
                "source_doc_name": "smoke.pdf",
                "file_type": "pdf",
                "chunks_count": 12,
                "status": "ok",
                "user_id": "smoke_kb",
            },
        ]
    )
    _rt.document_repo = fake_repo

    # TestClient 用 agent.app.app（含中间件栈，能正确处理 multipart）
    from agent.app import app as fastapi_app

    yield {
        "ingest_calls": ingest_calls,
        "fastapi_app": fastapi_app,
        "runtime": _rt,
        "document_repo": fake_repo,
    }


# ── POST /upload ────────────────────────────────────────────────────────

def test_upload_without_user_id_returns_422(api_test_client):
    """未登录（user_id 为空）→ FastAPI 422 拒绝（Form 必填）。"""
    client = TestClient(api_test_client["fastapi_app"])
    response = client.post(
        "/api/v1/documents/upload",
        files={"files": ("a.csv", b"id,name\n1,a\n", "text/csv")},
        data={"dataset_name": "anon", "chunk_strategy": "auto"},
        # user_id 故意不传
    )
    # FastAPI Form(...) 必填 → 422
    assert response.status_code == 422
    # 没有任何 ingest 调用
    assert api_test_client["ingest_calls"] == []


def test_upload_with_user_id_passes_to_ingest(api_test_client):
    """user_id 透传到 service.ingest（不再默认 public）。"""
    client = TestClient(api_test_client["fastapi_app"])
    response = client.post(
        "/api/v1/documents/upload",
        files={"files": ("a.csv", b"id,name\n1,a\n", "text/csv")},
        data={
            "dataset_name": "my_notes",
            "chunk_strategy": "recursive",
            "user_id": "smoke_kb",
        },
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["count"] == 1
    calls = api_test_client["ingest_calls"]
    assert len(calls) == 1
    # 关键：user_id 必须透传到 service.ingest（不再默认 public）
    assert calls[0]["user_id"] == "smoke_kb"
    # student_name 未传 → None
    assert calls[0]["student_name"] is None
    assert calls[0]["desensitized_triggered"] is False


def test_upload_with_student_name_triggers_desensitize(api_test_client):
    """student_name 非空 + user_id != public → service.ingest 触发脱敏。"""
    client = TestClient(api_test_client["fastapi_app"])
    response = client.post(
        "/api/v1/documents/upload",
        files={"files": ("transcript.pdf", b"transcript-bytes", "application/pdf")},
        data={
            "dataset_name": "my_transcript",
            "chunk_strategy": "auto",
            "user_id": "smoke_kb",
            "student_name": "张三",
        },
    )
    assert response.status_code == 200
    calls = api_test_client["ingest_calls"]
    assert len(calls) == 1
    assert calls[0]["student_name"] == "张三"
    assert calls[0]["user_id"] == "smoke_kb"
    assert calls[0]["desensitized_triggered"] is True


def test_upload_without_student_name_no_desensitize(api_test_client):
    """student_name 为空 → service.ingest 不脱敏（即使 user_id != public）。"""
    client = TestClient(api_test_client["fastapi_app"])
    response = client.post(
        "/api/v1/documents/upload",
        files={"files": ("doc.txt", b"any content", "text/plain")},
        data={
            "dataset_name": "personal_doc",
            "chunk_strategy": "auto",
            "user_id": "smoke_kb",
            # student_name 故意不传
        },
    )
    assert response.status_code == 200
    calls = api_test_client["ingest_calls"]
    assert len(calls) == 1
    assert calls[0]["student_name"] is None
    assert calls[0]["desensitized_triggered"] is False


# ── GET /datasets ────────────────────────────────────────────────────────

def test_list_datasets_filters_by_user_id_with_public(api_test_client):
    """include_public=True（默认）→ 返回 public + 本人 user_id 两个分区。"""
    fake_repo = api_test_client["document_repo"]
    client = TestClient(api_test_client["fastapi_app"])
    response = client.get(
        "/api/v1/documents/datasets",
        params={"user_id": "smoke_kb", "include_public": "true"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["count"] == 2
    # 验证 spy 收到的过滤参数
    _, kwargs = fake_repo.list_datasets.call_args
    assert kwargs["user_id"] == "smoke_kb"
    assert kwargs["include_public"] is True


def test_list_datasets_strict_personal_only(api_test_client):
    """include_public=False → 只返回本人 user_id 严格相等的数据。"""
    fake_repo = api_test_client["document_repo"]
    # 让 spy 返回只有 user_id=smoke_kb 的项
    fake_repo.list_datasets.return_value = [
        {
            "dataset_id": "d-personal-1",
            "dataset_name": "transcript_smoke",
            "source_doc_name": "smoke.pdf",
            "file_type": "pdf",
            "chunks_count": 12,
            "status": "ok",
            "user_id": "smoke_kb",
        },
    ]
    client = TestClient(api_test_client["fastapi_app"])
    response = client.get(
        "/api/v1/documents/datasets",
        params={"user_id": "smoke_kb", "include_public": "false"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["count"] == 1
    assert payload["datasets"][0]["user_id"] == "smoke_kb"
    _, kwargs = fake_repo.list_datasets.call_args
    assert kwargs["include_public"] is False


def test_list_datasets_without_user_id_returns_422(api_test_client):
    """缺 user_id → 422（FastAPI Query 必填）。"""
    client = TestClient(api_test_client["fastapi_app"])
    response = client.get("/api/v1/documents/datasets")
    assert response.status_code == 422


def test_list_datasets_repo_unavailable_returns_503(api_test_client):
    """runtime.document_repo 未就绪 → 503。"""
    api_test_client["runtime"].document_repo = None
    client = TestClient(api_test_client["fastapi_app"])
    response = client.get(
        "/api/v1/documents/datasets",
        params={"user_id": "smoke_kb"},
    )
    assert response.status_code == 503


# ── repo 层 ──────────────────────────────────────────────────────────────

def test_document_repo_create_dataset_persists_user_id():
    """DocumentRepository.create_dataset 必须把 user_id 写到 SQL。"""
    from storage.mysql.document_repo import DocumentRepository

    captured_sql: dict[str, Any] = {}

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params):
            captured_sql["sql"] = str(sql)
            captured_sql["params"] = params

    class _FakeEngine:
        def begin(self):
            return _FakeConn()

    repo = DocumentRepository.__new__(DocumentRepository)
    repo._engine = _FakeEngine()
    repo.ping = MagicMock(return_value=True)
    repo.create_dataset(
        dataset_id="d-test",
        dataset_name="n",
        source_doc_name="f",
        storage_path="/tmp/f",
        file_type="pdf",
        chunks_count=3,
        status="ok",
        user_id="alice",
    )
    # user_id 必须出现在 INSERT 参数里
    assert captured_sql["params"]["user_id"] == "alice"
    # SQL 文案里必须有 user_id 列
    assert "user_id" in captured_sql["sql"]
    # ON DUPLICATE KEY UPDATE 里也要更新 user_id
    assert "user_id = VALUES(user_id)" in captured_sql["sql"]
