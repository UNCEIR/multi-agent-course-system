# -*- coding: utf-8 -*-
"""report 上传批次落库生命周期测试（service 层，2026-08-31）。

验证业务闭环：stream_report 在落盘后立即写 report_uploads（processing），
工具产出 batch_done 后推进 done（回填成功/失败份数），异常推进 error。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class _FakeAgentStream:
    """伪 agent：模拟 tool start/end 事件（channel 由 fake builder 预填充）。"""

    async def __aiter__(self):
        yield {"event": "on_tool_start", "name": "render_report_batch"}
        yield {"event": "on_tool_end", "name": "render_report_batch"}
        await asyncio.sleep(0)


def _make_fake_builder(with_result: bool = True):
    """返回 (builder, channel_holder)。builder 在 build_deep_agent 时向 channel 预填充事件。"""

    def _builder(spec, tools=None):
        from tools.report.render_report_batch import report_progress_ctx

        q = report_progress_ctx.get()
        if q is not None and with_result:
            q.put_nowait(("student_done", {"student_id": "1", "name": "陈烨", "status": "ok", "format": "html"}))
            q.put_nowait(
                (
                    "batch_done",
                    {
                        "batch_id": "b_tool",
                        "students": [
                            {"student_id": "1", "name": "陈烨", "status": "ok", "format": "html", "file_key": "b_tool/1.html"}
                        ],
                        "failed_students": [],
                        "warnings": [],
                    },
                )
            )
        agent = MagicMock()
        agent.astream_events = MagicMock(return_value=_FakeAgentStream())
        return agent

    return _builder


async def _run_stream(user_id: str = "t1", files=None, with_result: bool = True) -> tuple[asyncio.Queue, MagicMock]:
    """跑一次 stream_report，返回 (out_queue, fake_repo)。"""
    from agent.report.service import stream_report

    fake_repo = MagicMock()
    fake_files = files if files is not None else [MagicMock(filename="道法.xlsx")]

    async def _fake_save_uploads(_files):
        return [str(Path("道法.xlsx"))], "rb_test"

    with patch("agent.main.factory.build_deep_agent", side_effect=_make_fake_builder(with_result=with_result)), patch(
        "agent.report.service.save_uploads", side_effect=_fake_save_uploads
    ), patch("agent.runtime.report_upload_repo", fake_repo):
        q: asyncio.Queue = asyncio.Queue()
        await stream_report(fake_files, semester="2023-2024第二学期", user_message="补一句", user_id=user_id, out_queue=q)
    return q, fake_repo


def _drain(q: asyncio.Queue) -> list[tuple[str, dict]]:
    events = []
    while not q.empty():
        events.append(q.get_nowait())
    return events


@pytest.mark.unit
async def test_stream_report_records_upload_processing_then_done():
    """业务闭环：上传批次先写 processing，工具产出后推进 done 并回填份数。"""
    q, fake_repo = await _run_stream(user_id="t1")

    # 1) 落盘后立即记录 processing（输入侧落库）
    create_call = fake_repo.create_upload.call_args
    assert create_call is not None
    kwargs = create_call.kwargs
    assert kwargs["batch_id"] == "rb_test"
    assert kwargs["user_id"] == "t1"
    assert kwargs["semester"] == "2023-2024第二学期"
    assert kwargs["user_message"] == "补一句"
    assert kwargs["file_names"] == ["道法.xlsx"]
    assert kwargs["status"] == "processing"

    # 2) done 事件 + 状态机推进 done（回填 1 成功 / 0 失败）
    events = _drain(q)
    assert any(e == "done" for e, _ in events)
    update_call = fake_repo.update_status.call_args
    assert update_call is not None
    assert update_call.args[0] == "rb_test"
    assert update_call.args[1] == "done"
    assert update_call.kwargs["students_ok"] == 1
    assert update_call.kwargs["students_failed"] == 0
    # done 时回填工具合并批次 b_tool（详情端点反查依据）
    assert update_call.kwargs["merged_batch_id"] == "b_tool"


@pytest.mark.unit
async def test_stream_report_no_files_no_upload_record():
    """未收到文件：只发 error 事件，不写 report_uploads。"""
    from agent.report.service import stream_report

    fake_repo = MagicMock()
    with patch("agent.runtime.report_upload_repo", fake_repo):
        q: asyncio.Queue = asyncio.Queue()
        await stream_report([], user_id="t1", out_queue=q)
    fake_repo.create_upload.assert_not_called()
    events = _drain(q)
    assert any(e == "error" for e, _ in events)


@pytest.mark.unit
async def test_stream_report_error_path_marks_upload_error():
    """工具管线抛错：推进 error 并落 error_message。"""

    class _BrokenStream:
        async def __aiter__(self):
            yield {"event": "on_tool_start", "name": "render_report_batch"}
            raise RuntimeError("boom")

    def _broken_builder(spec, tools=None):
        agent = MagicMock()
        agent.astream_events = MagicMock(return_value=_BrokenStream())
        return agent

    from agent.report.service import stream_report

    fake_repo = MagicMock()

    async def _fake_save_uploads(_files):
        return [str(Path("道法.xlsx"))], "rb_test"

    with patch("agent.main.factory.build_deep_agent", side_effect=_broken_builder), patch(
        "agent.report.service.save_uploads", side_effect=_fake_save_uploads
    ), patch("agent.runtime.report_upload_repo", fake_repo):
        q: asyncio.Queue = asyncio.Queue()
        await stream_report([MagicMock(filename="道法.xlsx")], user_id="t1", out_queue=q)

    update_call = fake_repo.update_status.call_args
    assert update_call is not None
    assert update_call.args[1] == "error"
    assert "boom" in update_call.kwargs.get("error_message", "")
    events = _drain(q)
    assert any(e == "error" for e, _ in events)


@pytest.mark.unit
async def test_stream_report_repo_unavailable_does_not_block():
    """仓储未初始化/不可用：告警跳过，不阻塞报告生成。"""
    from agent.report.service import stream_report

    async def _fake_save_uploads(_files):
        return [str(Path("道法.xlsx"))], "rb_test"

    with patch("agent.runtime.report_upload_repo", None), patch(
        "agent.report.service.save_uploads", side_effect=_fake_save_uploads
    ), patch("agent.main.factory.build_deep_agent", side_effect=_make_fake_builder(with_result=True)):
        q: asyncio.Queue = asyncio.Queue()
        await stream_report(
            [MagicMock(filename="道法.xlsx")],
            user_id="t1",
            out_queue=q,
        )
    # 仓储不可用不阻塞生成：工具正常产出 → done 事件照常到达
    events = _drain(q)
    assert any(e == "done" for e, _ in events)


@pytest.mark.unit
async def test_stream_report_global_timeout_emits_error():
    """整批死线：_run_agent 卡死超过 report_stream_timeout_seconds → 发 STREAM_TIMEOUT error + 状态 error。"""
    from unittest.mock import MagicMock

    from agent.report.service import stream_report

    fake_repo = MagicMock()
    settings = MagicMock()
    settings.report_stream_timeout_seconds = 0.2

    async def _fake_save_uploads(_files):
        return [str(Path("道法.xlsx"))], "rb_timeout"

    async def _hang_agent(*_a, **_kw):
        await asyncio.sleep(30)

    with patch("agent.main.factory.build_deep_agent", side_effect=lambda spec, tools=None: MagicMock()), patch(
        "agent.report.service.save_uploads", side_effect=_fake_save_uploads
    ), patch("agent.report.service._run_agent", side_effect=_hang_agent), patch(
        "config.get_settings", return_value=settings
    ), patch("agent.runtime.report_upload_repo", fake_repo):
        q: asyncio.Queue = asyncio.Queue()
        await stream_report([MagicMock(filename="道法.xlsx")], user_id="t1", out_queue=q)

    events = _drain(q)
    errs = [d for e, d in events if e == "error"]
    assert errs and errs[0]["code"] == "STREAM_TIMEOUT"
    update_call = fake_repo.update_status.call_args
    assert update_call is not None
    assert update_call.args[1] == "error"


@pytest.mark.unit
async def test_progress_forwarded_live_during_long_tool():
    """长工具调用（render_report_batch 分钟级）期间，student_done 必须实时到达 SSE，
    而不是等 agent 流结束才一次性转发（否则前端冻结、用户误判卡死）。"""
    from agent.report.service import _run_agent

    channel_q: asyncio.Queue = asyncio.Queue()
    out_queue: asyncio.Queue = asyncio.Queue()

    class _SlowStream:
        async def __aiter__(self):
            yield {"event": "on_tool_start", "name": "render_report_batch"}
            # 长工具：先产生一个学生完成进度，再模拟工具仍在运行
            channel_q.put_nowait(("student_done", {"student_id": "1", "name": "陈烨", "status": "ok", "format": "html"}))
            await asyncio.sleep(0.3)  # 模拟工具还在跑（期间不应有 agent 事件）
            channel_q.put_nowait(
                (
                    "batch_done",
                    {
                        "batch_id": "b_live",
                        "students": [
                            {"student_id": "1", "name": "陈烨", "status": "ok", "format": "html", "file_key": "b_live/1.html"}
                        ],
                        "failed_students": [],
                        "warnings": [],
                    },
                )
            )
            yield {"event": "on_tool_end", "name": "render_report_batch"}

    agent = MagicMock()
    agent.astream_events = MagicMock(return_value=_SlowStream())

    task = asyncio.create_task(_run_agent(agent, {}, channel_q, out_queue, "rb_live"))
    # 工具仍在运行（0.3s sleep 未结束）时，student_done 应已被实时转发
    await asyncio.sleep(0.1)
    got = _drain(out_queue)
    assert any(e == "student_done" for e, _ in got), "长工具调用期间进度未实时转发（前端会冻结）"

    result = await asyncio.wait_for(task, timeout=5)
    assert result is not None and result.get("batch_id") == "b_live"
    got = _drain(out_queue)
    assert any(e == "done" for e, _ in got)
