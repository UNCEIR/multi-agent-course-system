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
        files={"file": ("courses.csv", b"name,campus\nPython,University Town\n", "text/csv")},
        data={"dataset_name": "course_data", "chunk_strategy": "auto"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["chunks_count"] == 1
