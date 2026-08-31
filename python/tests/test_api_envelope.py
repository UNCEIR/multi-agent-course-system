# -*- coding: utf-8 -*-
"""统一响应信封（BaseResult）测试。

契约：
- 非流式 /api/v1/* JSON 响应 → {code, success, data, msg}
- 错误（4xx/5xx）→ code=HTTP 状态码、success=false、msg=detail
- SSE 流式（text/event-stream）与二进制下载保持原样，不被封装
- /health（非 /api/v1）不被封装
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.api
def test_success_json_is_enveloped():
    """成功 JSON 接口 → {code:200, success:true, data:<原负载>, msg:操作成功}。"""
    from fastapi.testclient import TestClient

    from agent.app import app

    client = TestClient(app)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["success"] is True
    assert body["msg"] == "操作成功"
    assert isinstance(body["data"], dict)


@pytest.mark.api
def test_error_response_is_enveloped_with_http_code():
    """4xx/5xx → {code:<HTTP>, success:false, data:null, msg:<detail>}（表现指定接口失败特性）。"""
    from fastapi.testclient import TestClient

    from agent.app import app

    client = TestClient(app)
    # 缺少必填 user_id → FastAPI 422 校验错误 → 信封
    resp = client.get("/api/v1/report/batches")
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == 422
    assert body["success"] is False
    assert body["data"] is None
    assert body["msg"]


@pytest.mark.api
def test_http_exception_is_enveloped_with_code():
    """业务 HTTPException（403）→ 信封 code=403、msg=详情。"""
    from fastapi.testclient import TestClient

    from agent.app import app

    upload_repo = MagicMock()
    upload_repo.get_by_batch = MagicMock(return_value={"batch_id": "rb_1", "user_id": "t1", "merged_batch_id": ""})
    with patch("agent.runtime.report_upload_repo", upload_repo), patch("agent.runtime.report_artifact_repo", MagicMock()):
        client = TestClient(app)
        resp = client.get("/api/v1/report/batches/rb_1", params={"user_id": "t2"})
    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == 403
    assert body["success"] is False
    assert "无权查看" in body["msg"]


@pytest.mark.api
async def test_sse_stream_is_not_enveloped():
    """SSE 流式响应（text/event-stream）保持原始事件协议，不套信封。"""
    from fastapi.testclient import TestClient

    from agent.app import app

    async def _fake_stream(files, *, semester, user_message, user_id, class_name, out_queue, template_name="grade4-6.html"):
        await out_queue.put(("done", {"batch_id": "rb_x", "students": [], "failed_students": []}))

    with patch("api.report.stream_report", side_effect=_fake_stream):
        client = TestClient(app)
        resp = client.post("/api/v1/report", files={"files": ("道法.xlsx", b"x", "application/octet-stream")})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert "event:" in resp.text  # 原始 SSE 帧
    assert '"code"' not in resp.text  # 未被封装


@pytest.mark.api
def test_binary_download_is_not_enveloped():
    """二进制下载（application/pdf）保持原样，不套信封。"""
    from fastapi.testclient import TestClient

    from agent.app import app

    with patch("api.report.verify_download_token", return_value=None), patch("agent.runtime.minio_repo") as minio:
        minio.download = MagicMock(return_value=b"%PDF-1.4 test")
        client = TestClient(app)
        resp = client.get(
            "/api/v1/report/download",
            params={"file_key": "b1/1.pdf", "token": "t", "expires_at": 9999999999},
        )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


@pytest.mark.api
def test_health_probe_not_enveloped():
    """/health（非 /api/v1，运维探活）保持原始结构。"""
    from fastapi.testclient import TestClient

    from agent.app import app

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "code" not in body  # 未封装
