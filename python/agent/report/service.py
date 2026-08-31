# -*- coding: utf-8 -*-
"""report 编排门面 — deep agent 壳（A-shell）+ 进度 channel 合流。

四决策点循环由 REPORT_AGENT_SPEC 的 system_prompt 驱动（LLM 编排）：
  ① 信息完备性（文件缺失 → 澄清）
  ② inspect_score_excels（确定性摘要工具）
  ③ 年级分类（LLM 决策，规则兜底在 render_report_batch 内校验）
  ④ 异常处置（摘要告警不得静默）
工具内部进度经 asyncio.Queue 与 agent 事件流合流 → SSE 事件。

事件协议（api 层转发）：
  text / tool / progress / student_done / student_error / batch_done → done
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import logging
import time
import uuid
from pathlib import Path

from agent.main.specs import REPORT_AGENT_SPEC
from tools.report.render_report_batch import (
    report_class_ctx,
    report_files_ctx,
    report_progress_ctx,
    report_template_ctx,
    report_user_message_ctx,
)

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / ".documents" / "report_uploads"


async def save_uploads(files: list) -> tuple[list[str], str]:
    """文件落盘 → (file_keys, batch_id)。"""
    batch_id = f"rb_{uuid.uuid4().hex[:8]}"
    target = UPLOAD_DIR / batch_id
    target.mkdir(parents=True, exist_ok=True)
    keys: list[str] = []
    for f in files:
        dest = target / f.filename
        content = await f.read()
        dest.write_bytes(content)
        keys.append(str(dest))
    return keys, batch_id


def _record_upload(runtime, *, batch_id: str, user_id: str, semester: str, user_message: str, file_keys: list[str]) -> None:
    """上传批次落库（processing 态，输入侧元数据）。仓储不可用只告警，不阻塞生成。"""
    repo = getattr(runtime, "report_upload_repo", None)
    if repo is None:
        logger.warning("report_upload_repo not initialized, skip upload record batch=%s", batch_id)
        return
    try:
        repo.create_upload(
            batch_id=batch_id,
            user_id=user_id,
            semester=semester,
            user_message=user_message,
            file_names=[Path(f).name for f in file_keys],
            status="processing",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("report upload record failed batch=%s error=%s", batch_id, exc)


def _update_upload_status(
    runtime,
    *,
    batch_id: str,
    status: str,
    error_message: str = "",
    students_ok: int = 0,
    students_failed: int = 0,
    merged_batch_id: str = "",
) -> None:
    """推进 report_uploads 状态机：done（回填成功/失败份数 + 工具合并批次）| error（记录原因）。"""
    repo = getattr(runtime, "report_upload_repo", None)
    if repo is None:
        return
    try:
        repo.update_status(
            batch_id,
            status,
            error_message=error_message,
            students_ok=students_ok,
            students_failed=students_failed,
            merged_batch_id=merged_batch_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("report upload status update failed batch=%s error=%s", batch_id, exc)




def _system_prompt(file_keys: list[str], semester: str, user_message: str) -> str:
    """注入文件上下文 + 分类决策指令（四决策点循环的编排提示）。"""
    return (
        REPORT_AGENT_SPEC.system_prompt
        + "\n\n"
        + "## 本次报告生成任务\n"
        + f"已上传成绩单文件（file_keys，调用工具时无需再传）：{json.dumps(file_keys, ensure_ascii=False)}\n"
        + f"学期：{semester or '未知（可留空）'}\n"
        + (f"用户补充说明：{user_message}\n" if user_message else "")
        + "## 执行流程（严格按序）\n"
        + "1. 先调用 inspect_score_excels 查看文件摘要。\n"
        + "2. 根据摘要判断年级分类：category=1 表示一二三年级（无道法成绩表）；category=2 表示四五六年级（有道法成绩表）。"
        " 若摘要不足以判断且用户未提供年级信息，向用户澄清（不要硬猜）。\n"
        + "3. 调用 render_report_batch(category, semester) 生成全部学生成绩单。\n"
        + "4. 汇总结果：成功学生列表、失败学生及原因、警告清单。异常信息不得静默吞掉。\n"
        + "## 纪律\n"
        + "- 数值统计交给确定性工具，绝不心算；不编造任何成绩。\n"
        + "- 一次请求只生成一批，不要重复调用 render_report_batch。"
    )


async def stream_report(
    files: list,
    *,
    semester: str = "",
    user_message: str = "",
    user_id: str = "",
    class_name: str = "",
    out_queue: asyncio.Queue,
    template_name: str = "grade4-6.html",
) -> None:
    """跑完整 report 场景：落盘 → 建 agent → 双流合流 → 事件进 out_queue。"""
    from agent import runtime
    from agent.main.factory import build_deep_agent

    file_keys, batch_id = await save_uploads(files)
    if not file_keys:
        await _emit(out_queue, "error", {"code": "NO_FILES", "message": "未收到任何文件"})
        return

    # 输入侧落库：上传批次元数据（processing 态）——与知识库 document_records 分表
    _record_upload(runtime, batch_id=batch_id, user_id=user_id, semester=semester, user_message=user_message, file_keys=file_keys)

    # 工具进度专用 channel（与 SSE 出队分离，避免双消费者竞态）
    channel_q: asyncio.Queue = asyncio.Queue()

    # 注入请求上下文（工具经 ContextVar 读取，避免 LLM 猜文件路径）
    token_files = report_files_ctx.set(file_keys)
    token_queue = report_progress_ctx.set(channel_q)
    token_tpl = report_template_ctx.set(template_name)
    token_class = report_class_ctx.set(class_name)
    token_um = report_user_message_ctx.set(user_message)
    try:
        spec = dataclasses.replace(
            REPORT_AGENT_SPEC,
            system_prompt=_system_prompt(file_keys, semester, user_message),
        )
        agent = await build_deep_agent(spec)

        config = {"configurable": {"thread_id": f"report:{batch_id}", "user_id": "report"}, "run_name": spec.task_name.value}
        # 整批死线（兜底）：单次 LLM 调用已由 build_chat_openai 的 request_timeout 兜住，
        # 这里再给整批加全局超时，杜绝任何上游异常导致 SSE 无限等待。
        from config import get_settings as _get_settings

        deadline = float(getattr(_get_settings(), "report_stream_timeout_seconds", 600.0))
        result = await asyncio.wait_for(
            _run_agent(agent, config, channel_q, out_queue, batch_id),
            timeout=deadline,
        )
        if result is not None:
            _update_upload_status(
                runtime,
                batch_id=batch_id,
                status="done",
                students_ok=len(result.get("students", [])),
                students_failed=len(result.get("failed_students", [])),
                merged_batch_id=result.get("batch_id", ""),
            )
    except asyncio.TimeoutError:
        logger.warning("report stream timed out after %.0fs batch=%s", deadline, batch_id)
        _update_upload_status(runtime, batch_id=batch_id, status="error", error_message=f"stream_timeout_{deadline:.0f}s")
        await _emit(
            out_queue,
            "error",
            {
                "code": "STREAM_TIMEOUT",
                "message": f"报告生成超过 {deadline:.0f}s 未完成（可能上游 LLM 异常），请重试或减小批次",
                "batch_id": batch_id,
            },
        )
    except asyncio.CancelledError:
        logger.info("report stream cancelled batch=%s", batch_id)
        _update_upload_status(runtime, batch_id=batch_id, status="error", error_message="cancelled")
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("report stream failed batch=%s", batch_id)
        _update_upload_status(runtime, batch_id=batch_id, status="error", error_message=str(exc)[:500])
        await _emit(out_queue, "error", {"code": type(exc).__name__.upper(), "message": str(exc)})
    finally:
        report_files_ctx.reset(token_files)
        report_progress_ctx.reset(token_queue)
        report_template_ctx.reset(token_tpl)
        report_class_ctx.reset(token_class)
        report_user_message_ctx.reset(token_um)


def _drain_channel(channel_q: asyncio.Queue, out_queue: asyncio.Queue) -> dict | None:
    """把 channel 中现有事件转发到 SSE 队列；命中 batch_done 返回其结果（不转发）。

    事件原样透传（不含 service 外壳 batch_id——对账以工具结果的 batch_id 为准）。
    """
    batch_result = None
    while not channel_q.empty():
        event, data = channel_q.get_nowait()
        if event == "batch_done":
            batch_result = data
            continue
        if event in ("student_done", "student_error", "progress"):
            try:
                out_queue.put_nowait((event, data))
            except Exception:  # noqa: BLE001
                pass
    return batch_result


async def _run_agent(agent, config: dict, channel_q: asyncio.Queue, out_queue: asyncio.Queue, batch_id: str) -> dict | None:
    """agent astream_events 与工具进度 channel 合流。

    2026-08-31 修复：render_report_batch 是单个长运行工具（分钟级），期间 langgraph
    astream_events 不产生任何事件——原实现只在"每个 agent 事件后"转发 channel，导致
    工具进度（student_done/progress）全部堵住、前端冻结数分钟、用户误判卡死而取消。
    改为后台常驻 drainer 持续转发，工具进度实时到达 SSE（兼作连接心跳）。
    """
    events = agent.astream_events(
        {"messages": [{"role": "user", "content": "请生成这批学生的成绩单。"}]},
        config=config,
        version="v1",
    )
    holder: dict = {"batch_result": None}

    async def _drain_forever() -> None:
        """后台持续把 channel 事件转发到 SSE；batch_done 记入 holder（不转发）。"""
        while True:
            try:
                event, data = await channel_q.get()
            except asyncio.CancelledError:
                return
            if event == "batch_done":
                holder["batch_result"] = data
            elif event in ("student_done", "student_error", "progress"):
                try:
                    out_queue.put_nowait((event, data))
                except Exception:  # noqa: BLE001
                    pass

    drainer = asyncio.create_task(_drain_forever())
    try:
        async for ev in events:
            kind = ev.get("event")
            if kind == "on_chat_model_stream":
                chunk = ev.get("data", {}).get("chunk")
                token = ""
                if chunk is not None:
                    token = getattr(chunk, "content", None) or ""
                    if isinstance(token, list):
                        token = "".join(i.get("text", "") for i in token if isinstance(i, dict))
                if token:
                    await _emit(out_queue, "text", {"text": str(token), "batch_id": batch_id})
            elif kind in ("on_tool_start", "on_tool_end"):
                tool_name = ev.get("name", "")
                await _emit(out_queue, "tool", {"tool": tool_name, "status": "start" if kind == "on_tool_start" else "end", "batch_id": batch_id})
    finally:
        drainer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await drainer

    # agent 结束：兜底再清一次 channel（batch_done 可能晚于最后事件到达）
    if holder["batch_result"] is None:
        holder["batch_result"] = _drain_channel(channel_q, out_queue)
    batch_result = holder["batch_result"]

    if batch_result is None:
        await _emit(out_queue, "error", {"code": "NO_BATCH_RESULT", "message": "工具未返回批量结果", "batch_id": batch_id})
        return None

    await _emit(
        out_queue,
        "done",
        {
            # 对账以工具结果 batch_id 为准（与 report_artifacts 落库一致）
            "batch_id": batch_result.get("batch_id", batch_id),
            "students": _with_download_urls(batch_result.get("students", [])),
            "failed_students": batch_result.get("failed_students", []),
            "warnings": batch_result.get("warnings", []),
            "summary": batch_result.get("summary", {}),
        },
    )
    return batch_result


def _with_download_urls(students: list[dict]) -> list[dict]:
    """为成功学生生成 token 下载链接（HMAC，24h）。"""
    out = []
    for s in students:
        if s.get("status") == "ok" and s.get("file_key"):
            s["url"] = make_download_url(s["file_key"])
        out.append(s)
    return out


# ── token 下载链接（HMAC）───────────────────────────────────────────────
def make_download_url(file_key: str) -> str:
    import hmac
    import hashlib
    from datetime import datetime, timedelta, timezone
    from config import get_settings

    settings = get_settings()
    secret = settings.report_download_secret.encode()
    expires = datetime.now(timezone.utc) + timedelta(hours=settings.report_download_ttl_hours)
    exp = int(expires.timestamp())
    token = hmac.new(secret, f"{file_key}:{exp}".encode(), hashlib.sha256).hexdigest()
    return f"/api/v1/report/download?file_key={file_key}&token={token}&expires_at={exp}"


def verify_download_token(file_key: str, token: str, expires_at: int) -> str | None:
    """校验下载 token；返回 None=合法，否则返回错误码。"""
    import hmac
    import hashlib
    import time as _time
    from config import get_settings

    secret = get_settings().report_download_secret
    if not secret:
        return "download_disabled"
    # 先判过期（过期链接优先提示重新生成，签名校验在后避免误报 invalid）
    if _time.time() > expires_at:
        return "token_expired"
    expected = hmac.new(secret.encode(), f"{file_key}:{expires_at}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, token):
        return "invalid_token"
    return None


async def _emit(out_queue: asyncio.Queue, event: str, data: dict) -> None:
    with contextlib.suppress(Exception):
        out_queue.put_nowait((event, data))
