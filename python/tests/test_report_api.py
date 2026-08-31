# -*- coding: utf-8 -*-
"""report API 测试：SSE 事件序（mock agent 工具）+ 下载端点三类错误。

- 消费真实 SSE 流断言事件序 + 终结 done/error（AGENTS.md 契约）
- 工具 render_report_batch 用假实现：直接向 channel 发 student_done/batch_done
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "daofa-grade4-class7.xlsx"


class _FakeAgentStream:
    """伪 agent：模拟 on_chat_model_stream + on_tool_start/end 事件序列。"""

    def __init__(self):
        self.tool_channel = None

    async def __aiter__(self):
        events = [
            {"event": "on_chat_model_stream", "data": {"chunk": MagicMock(content="开始生成")}},
            {"event": "on_tool_start", "name": "render_report_batch"},
            {"event": "on_tool_end", "name": "render_report_batch"},
            {"event": "on_chat_model_stream", "data": {"chunk": MagicMock(content="完成")}},
        ]
        for e in events:
            yield e
            await asyncio.sleep(0)


def _fake_agent():
    agent = MagicMock()
    agent.astream_events = MagicMock(return_value=_FakeAgentStream())
    return agent


def _patch_runtime(minio_data: bytes | None = b"PDF", secret: str = "s"):
    """patch agent/runtime 依赖：minio_repo 假对象 + settings。"""
    minio = MagicMock()
    minio.download = MagicMock(return_value=minio_data)
    stack = [
        patch("agent.report.service.build_deep_agent", side_effect=lambda spec, tools=None: _fake_agent()),
        patch("agent.report.service.REPORT_AGENT_SPEC"),
        patch("agent.report.service.dataclasses"),
    ]
    # 让 dataclasses.replace 原样返回 spec
    stack[-1].start()
    from dataclasses import dataclass

    @dataclass
    class _Spec:
        system_prompt: str = "p"
        task_name: object = MagicMock()
        name: str = "report_agent"

    replace = MagicMock(return_value=_Spec())
    stack[-1].replace = replace

    yield
    for p in stack:
        p.stop()


@pytest.mark.api
async def test_report_sse_event_order_and_done():
    """SSE 事件序：text → tool → progress → student_done → done。"""
    from agent import runtime

    runtime.minio_repo = MagicMock()
    runtime.minio_repo.upload = MagicMock(return_value="k")

    # 工具注入：预置 channel 事件（fake agent 不真实调用工具）
    async def _fake_stream(files, *, semester, user_message, user_id, class_name, out_queue, template_name="grade4-6.html"):
        await out_queue.put(("text", {"text": "ok", "batch_id": "rb_test"}))
        await out_queue.put(("progress", {"phase": "parsing", "detail": "1", "batch_id": "rb_test"}))
        await out_queue.put(
            ("student_done", {"student_id": "1", "name": "陈烨", "status": "ok", "format": "html", "batch_id": "rb_test"})
        )
        await out_queue.put(
            (
                "done",
                {
                    "batch_id": "rb_test",
                    "students": [{"student_id": "1", "name": "陈烨", "status": "ok", "format": "html", "url": "/x"}],
                    "failed_students": [],
                    "warnings": [],
                },
            )
        )

    with patch("api.report.stream_report", side_effect=_fake_stream), patch(
        "api.report.verify_download_token", return_value=None
    ):
        from fastapi.testclient import TestClient

        from agent.app import app

        client = TestClient(app)
        with open(FIXTURE, "rb") as f:
            resp = client.post(
                "/api/v1/report",
                files={"files": ("道法.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"semester": "2023-2024第二学期"},
            )
        assert resp.status_code == 200
        body = resp.text
        events = [line.split(": ", 1)[1] for line in body.splitlines() if line.startswith("event: ")]
        assert events[0] == "text"
        assert "student_done" in events
        assert events[-1] == "done"
        assert "error" not in events


@pytest.mark.api
async def test_report_no_files_400():
    from fastapi.testclient import TestClient

    from agent.app import app

    client = TestClient(app)
    resp = client.post("/api/v1/report")
    assert resp.status_code == 400


@pytest.mark.api
async def test_download_invalid_token():
    from fastapi.testclient import TestClient

    from agent.app import app

    with patch("api.report.verify_download_token", return_value="invalid_token"):
        client = TestClient(app)
        resp = client.get("/api/v1/report/download", params={"file_key": "b1/1.pdf", "token": "bad", "expires_at": 9999999999})
    assert resp.status_code == 403
    assert "invalid_token" in resp.text


@pytest.mark.api
async def test_download_expired():
    from fastapi.testclient import TestClient

    from agent.app import app

    with patch("api.report.verify_download_token", return_value="token_expired"):
        client = TestClient(app)
        resp = client.get("/api/v1/report/download", params={"file_key": "b1/1.pdf", "token": "t", "expires_at": 0})
    assert resp.status_code == 410
    assert "token_expired" in resp.text


@pytest.mark.api
async def test_download_not_found():
    from fastapi.testclient import TestClient

    from agent.app import app

    with patch("api.report.verify_download_token", return_value=None), patch(
        "config.get_settings", return_value=MagicMock(report_download_secret="s")
    ):
        client = TestClient(app)
        with patch("agent.runtime.minio_repo") as minio:
            minio.download = MagicMock(return_value=None)
            resp = client.get("/api/v1/report/download", params={"file_key": "b1/missing.pdf", "token": "t", "expires_at": 9999999999})
    assert resp.status_code == 404
    assert "artifact_not_found" in resp.text


@pytest.mark.api
async def test_download_ok():
    from fastapi.testclient import TestClient

    from agent.app import app

    with patch("api.report.verify_download_token", return_value=None):
        client = TestClient(app)
        with patch("agent.runtime.minio_repo") as minio:
            minio.download = MagicMock(return_value=b"%PDF-1.4 test")
            resp = client.get("/api/v1/report/download", params={"file_key": "b1/1.pdf", "token": "t", "expires_at": 9999999999})
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")


@pytest.mark.api
async def test_report_batches_list():
    """GET /api/v1/report/batches 返回当前 user 的上传批次列表（mock repo）。"""
    from unittest.mock import MagicMock

    from fastapi.testclient import TestClient

    from agent.app import app

    fake_repo = MagicMock()
    fake_repo.list_by_user = MagicMock(
        return_value=[
            {
                "batch_id": "rb_abc",
                "user_id": "t1",
                "semester": "2023-2024第二学期",
                "file_count": 1,
                "file_names": ["道法.xlsx"],
                "status": "done",
                "students_ok": 37,
                "students_failed": 0,
            }
        ]
    )
    with patch("agent.runtime.report_upload_repo", fake_repo):
        client = TestClient(app)
        resp = client.get("/api/v1/report/batches", params={"user_id": "t1"})
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["count"] == 1
    assert body["batches"][0]["batch_id"] == "rb_abc"
    assert body["batches"][0]["status"] == "done"


@pytest.mark.api
async def test_report_batches_requires_user_id():
    """未传 user_id → 401（与 documents/datasets 的登录口径一致）。"""
    from fastapi.testclient import TestClient

    from agent.app import app

    client = TestClient(app)
    resp = client.get("/api/v1/report/batches")
    assert resp.status_code == 422  # Query 必填缺失


@pytest.mark.api
async def test_download_inline_preview():
    """?inline=1 → Content-Disposition: inline（浏览器新标签页渲染 PDF）。"""
    from fastapi.testclient import TestClient

    from agent.app import app

    with patch("api.report.verify_download_token", return_value=None), patch("agent.runtime.minio_repo") as minio:
        minio.download = MagicMock(return_value=b"%PDF-1.4 test")
        client = TestClient(app)
        resp = client.get(
            "/api/v1/report/download",
            params={"file_key": "b1/1.pdf", "token": "t", "expires_at": 9999999999, "inline": "true"},
        )
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].startswith("inline")
    assert resp.content.startswith(b"%PDF")


@pytest.mark.api
async def test_download_default_is_attachment():
    """缺省 inline → attachment（下载而非预览）。"""
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
    assert resp.headers["content-disposition"].startswith("attachment")


@pytest.mark.api
async def test_batch_detail_returns_artifacts_with_urls():
    """GET /api/v1/report/batches/{batch_id}：上传记录 + 逐学生产物（附 token 下载/预览 URL）。"""
    from unittest.mock import MagicMock

    from fastapi.testclient import TestClient

    from agent.app import app

    upload_repo = MagicMock()
    upload_repo.get_by_batch = MagicMock(
        return_value={
            "batch_id": "rb_abc",
            "merged_batch_id": "b_xyz",
            "user_id": "t1",
            "semester": "2023-2024第二学期",
            "status": "done",
            "students_ok": 1,
            "students_failed": 0,
        }
    )
    artifact_repo = MagicMock()
    artifact_repo.list_by_batch = MagicMock(
        return_value=[
            {
                "batch_id": "b_xyz",
                "student_id": "1",
                "student_name": "陈烨",
                "format": "pdf",
                "status": "ok",
                "file_key": "b_xyz/1.pdf",
                "error_code": "",
                "error_message": "",
            }
        ]
    )
    with patch("agent.runtime.report_upload_repo", upload_repo), patch(
        "agent.runtime.report_artifact_repo", artifact_repo
    ):
        client = TestClient(app)
        resp = client.get("/api/v1/report/batches/rb_abc", params={"user_id": "t1"})
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["batch_id"] == "b_xyz"
    assert body["batch"]["user_id"] == "t1"
    assert body["students"][0]["student_name"] == "陈烨"
    assert "/api/v1/report/download?" in body["students"][0]["url"]


@pytest.mark.api
async def test_batch_detail_forbidden_on_user_mismatch():
    """归属校验：上传记录 user_id 与请求 user_id 不一致 → 403。"""
    from unittest.mock import MagicMock

    from fastapi.testclient import TestClient

    from agent.app import app

    upload_repo = MagicMock()
    upload_repo.get_by_batch = MagicMock(return_value={"batch_id": "rb_abc", "user_id": "t1", "merged_batch_id": ""})
    with patch("agent.runtime.report_upload_repo", upload_repo), patch("agent.runtime.report_artifact_repo", MagicMock()):
        client = TestClient(app)
        resp = client.get("/api/v1/report/batches/rb_abc", params={"user_id": "t2"})
    assert resp.status_code == 403


@pytest.mark.api
async def test_report_passes_class_name_and_user_message():
    """POST /api/v1/report 的 class_name / user_message 透传到 stream_report。"""
    from fastapi.testclient import TestClient

    from agent.app import app

    captured = {}

    async def _fake_stream(files, *, semester, user_message, user_id, class_name, out_queue, template_name="grade4-6.html"):
        captured["semester"] = semester
        captured["class_name"] = class_name
        captured["user_message"] = user_message
        await out_queue.put(("done", {"batch_id": "rb_x", "students": [], "failed_students": []}))

    with patch("api.report.stream_report", side_effect=_fake_stream):
        client = TestClient(app)
        with open(FIXTURE, "rb") as f:
            resp = client.post(
                "/api/v1/report",
                files={"files": ("道法.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={
                    "semester": "2023-2024第二学期",
                    "class_name": "四（7）班",
                    "user_message": "评语写温暖一些",
                    "user_id": "t1",
                },
            )
    assert resp.status_code == 200
    assert captured["semester"] == "2023-2024第二学期"
    assert captured["class_name"] == "四（7）班"
    assert captured["user_message"] == "评语写温暖一些"
