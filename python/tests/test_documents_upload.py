# -*- coding: utf-8 -*-
"""文档上传本地闭环测试。"""

from __future__ import annotations

from fastapi import UploadFile
from io import BytesIO

import pytest


@pytest.mark.asyncio
async def test_document_ingestion_service_csv(tmp_path):
    from agent.documents.service import DocumentIngestionService

    upload = UploadFile(
        filename="courses.csv",
        file=BytesIO(b"name,campus\nPython,University Town\n"),
    )
    result = await DocumentIngestionService(tmp_path).ingest(
        upload,
        dataset_name="course_data",
        chunk_strategy="auto",
    )

    assert result["status"] == "ok"
    assert result["chunks_count"] == 1
    assert "Python | University Town" in result["chunks"][0]["text"]
    assert (tmp_path / result["dataset_id"] / "courses.csv").is_file()


def test_documents_router_registered():
    from agent.app import app

    paths = {route.path for route in app.routes}
    assert "/api/v1/documents/upload" in paths


def test_documents_upload_endpoint(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import api.documents as documents_api
    from agent.app import app
    from agent.documents.service import DocumentIngestionService

    monkeypatch.setattr(documents_api, "service", DocumentIngestionService(tmp_path))
    response = TestClient(app).post(
        "/api/v1/documents/upload",
        files={"files": ("courses.csv", b"name,campus\nPython,University Town\n", "text/csv")},
        data={"dataset_name": "course_data", "chunk_strategy": "auto", "user_id": "public"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["count"] == 1
    assert payload["datasets"][0]["status"] == "ok"
    assert payload["datasets"][0]["chunks_count"] >= 1


def test_documents_upload_writes_to_milvus(tmp_path, monkeypatch):
    """回归 2026-08-25 bug：DocumentsPage 上传链路默认 vector_repo=None，
    导致 ingest() L92 的 upsert_chunks 从未被调用，知识库永远查不到。

    本测试用 monkeypatch 替换 DocumentVectorRepository.upsert_chunks 为 spy，
    验证 endpoint 调用后真实触发了 Milvus 写入。
    """
    from fastapi.testclient import TestClient

    import api.documents as documents_api
    from agent.app import app
    from agent.documents.service import DocumentIngestionService

    svc = DocumentIngestionService(tmp_path)
    # 用 spy 替换 document_vector_repo.upsert_chunks
    upsert_calls: list[list[dict]] = []

    class _FakeEmbedding:
        def embed_texts(self, texts):
            return [[0.0] * 8 for _ in texts]

    class _FakeVectorRepo:
        embedding_client = _FakeEmbedding()

        def upsert_chunks(self, chunks):
            upsert_calls.append(chunks)
            return len(chunks)

    svc.vector_repo = _FakeVectorRepo()
    svc.embedding_client = _FakeEmbedding()
    # 不替换 document_repo —— 单测 tmp_path 走 .documents，写到本地不需要 MySQL
    monkeypatch.setattr(documents_api, "service", svc)

    response = TestClient(app).post(
        "/api/v1/documents/upload",
        files={"files": ("courses.csv", b"id,name\n1,alpha\n2,bravo\n", "text/csv")},
        data={"dataset_name": "milvus_write_test", "chunk_strategy": "auto", "user_id": "public"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["datasets"][0]["status"] == "ok"
    # 关键断言：upsert_chunks 必须被真实调用过至少 1 次（之前 bug 时是 0 次）
    assert len(upsert_calls) >= 1, (
        "DocumentVectorRepository.upsert_chunks 未被调用——这是 2026-08-25 bug 回归！"
    )
    # 写入的 chunk 必须带 user_id（默认 public，方便 query_knowledge 检索）
    first_chunk = upsert_calls[0][0]
    assert "chunk_id" in first_chunk
    assert "content" in first_chunk
    assert first_chunk.get("user_id") in {"public", "PUBLIC_USER"}


# ── 路 5（2026-08-25）：单/批统一为 files 列表 ────────────────────────────

def test_documents_upload_batch_5_files(tmp_path, monkeypatch):
    """5 个小 CSV 一次上传，count=5，全部 success，dataset_id 互不相同。"""
    from fastapi.testclient import TestClient

    import api.documents as documents_api
    from agent.app import app
    from agent.documents.service import DocumentIngestionService

    monkeypatch.setattr(documents_api, "service", DocumentIngestionService(tmp_path))
    files = [
        ("courses.csv", f"id,name\n{i},Course{i}\n".encode(), "text/csv") for i in range(5)
    ]
    response = TestClient(app).post(
        "/api/v1/documents/upload",
        files=[("files", f) for f in files],
        data={"dataset_name": "batch5", "chunk_strategy": "auto", "user_id": "public"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["count"] == 5
    dataset_ids = [d["dataset_id"] for d in payload["datasets"]]
    assert all(d["status"] == "ok" for d in payload["datasets"])
    assert len(set(dataset_ids)) == 5  # 互不相同


def test_documents_upload_batch_exceeds_5_files(tmp_path, monkeypatch):
    """6 个文件上传 → FastAPI max_length=5 拦截，422 Unprocessable Entity。"""
    from fastapi.testclient import TestClient

    import api.documents as documents_api
    from agent.app import app
    from agent.documents.service import DocumentIngestionService

    monkeypatch.setattr(documents_api, "service", DocumentIngestionService(tmp_path))
    files = [
        ("f.csv", b"id,name\n1,a\n", "text/csv") for _ in range(6)
    ]
    response = TestClient(app).post(
        "/api/v1/documents/upload",
        files=[("files", f) for f in files],
        data={"dataset_name": "batch6", "chunk_strategy": "auto"},
    )

    # FastAPI 对 File(max_length=5) 越界返回 422
    assert response.status_code == 422


def test_documents_upload_batch_one_bad_file_others_succeed(tmp_path, monkeypatch):
    """1 个文件触发解析错误 + 2 个好文件 → 只有坏文件 status=error，其余 ok。

    用 monkeypatch 替换 DocumentIngestionService.ingest，在文件名含 "bad"
    的调用时抛 RuntimeError；其它文件名走原始 ingest。这样可确定性触发
    ingest_many 的 "任一文件失败不影响其它文件" 语义。"""
    from fastapi.testclient import TestClient

    import api.documents as documents_api
    from agent.app import app
    from agent.documents.service import DocumentIngestionService

    real_ingest = DocumentIngestionService.ingest

    async def _selective_ingest(self, file, *args, **kwargs):
        if file.filename and "bad" in file.filename:
            raise RuntimeError("simulated parse failure")
        return await real_ingest(self, file, *args, **kwargs)

    monkeypatch.setattr(
        DocumentIngestionService, "ingest", _selective_ingest
    )
    monkeypatch.setattr(documents_api, "service", DocumentIngestionService(tmp_path))
    files = [
        ("good1.csv", b"id,name\n1,a\n", "text/csv"),
        ("bad_file.csv", b"id,name\n2,bad\n", "text/csv"),
        ("good2.csv", b"id,name\n3,c\n", "text/csv"),
    ]
    response = TestClient(app).post(
        "/api/v1/documents/upload",
        files=[("files", f) for f in files],
        data={"dataset_name": "mixed", "chunk_strategy": "auto", "user_id": "public"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["count"] == 3
    statuses = [d["status"] for d in payload["datasets"]]
    assert statuses.count("ok") == 2  # good1 / good2
    assert statuses.count("error") == 1  # bad_file
    err = next(d for d in payload["datasets"] if d["status"] == "error")
    assert err.get("dataset_id") is None
    assert err["filename"] == "bad_file.csv"
    assert "simulated parse failure" in err["message"]
