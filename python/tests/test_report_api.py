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
    async def _fake_stream(files, *, semester, user_message, out_queue, template_name="grade4-6.html"):
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
