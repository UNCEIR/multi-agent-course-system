"""v2 主 Agent 统一会话路由。

- POST /api/v1/chat         同步返回（兼容后端调用）
- POST /api/v1/chat/stream  SSE 流式（前端主对话框，含 token/工具阶段/done/error）
"""

from __future__ import annotations

import asyncio
import json
import time

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from agent import runtime
from agent.main.context import user_context
from ai.llm_task_name import LLMTaskName
from services.sse_event_buffer import EventBuffer, parse_last_event_id, sse_with_id

logger = structlog.get_logger()
router = APIRouter()


_AGENT_RUN_NAMES = {"main_agent", "recommendation_agent", "report_agent", "evaluation_agent", "ppt_agent"}


def _is_agent_run_name(name: str) -> bool:
    """subagent 委派 run 识别（agent_tree 契约 E3）：已知 spec 名或名称含 agent 关键字。"""
    if not name:
        return False
    if name in _AGENT_RUN_NAMES:
        return True
    return "agent" in name.lower()


def _build_agent_tree(runs: list[dict]) -> list[dict]:
    """flat run 列表 → 树（契约：run_id/name/kind/status/args_summary/result_summary/latency_ms/children）。"""
    by_id: dict[str, dict] = {}
    for r in runs:
        by_id.setdefault(str(r["run_id"]), r)
    roots: list[dict] = []

    def _node(r: dict) -> dict:
        return {
            "run_id": str(r["run_id"]),
            "name": str(r.get("name", "")),
            "kind": "main" if str(r.get("name", "")) == "main_agent" else "subagent",
            "status": str(r.get("status", "running")),
            "args_summary": r.get("args_summary"),
            "result_summary": r.get("result_summary"),
            "latency_ms": r.get("latency_ms"),
            "children": [],
        }

    for r in runs:
        node = _node(r)
        parent_id = None
        for pid in r.get("parent_ids") or []:
            if str(pid) in by_id:
                parent_id = str(pid)
                break
        if parent_id and parent_id in by_id:
            by_id[parent_id].setdefault("_children", []).append(node)
        else:
            roots.append(node)

    def _attach(n: dict) -> None:
        n["children"] = by_id.get(n["run_id"], {}).get("_children", [])
        for ch in n["children"]:
            _attach(ch)

    for root in roots:
        _attach(root)
    return roots


def _inject_compaction_summary(repo, session_id: str) -> str | None:
    """续轮注入压缩摘要（A6 读路径）：chat.py messages 组装点为唯一入口。

    首轮无压缩记录 → None；有则返回 system 前缀消息内容（不落库，仅注入上下文）。
    """
    if repo is None:
        return None
    try:
        latest = repo.get_latest_compaction(session_id)
    except Exception:  # noqa: BLE001 —— 读库失败仅跳过注入，不阻塞对话
        return None
    if not latest or not latest.get("summary"):
        return None
    return f"会话历史摘要（自动压缩，供续聊上下文）：\n{latest['summary']}"


class ChatRequest(BaseModel):
    message: str = Field(..., description="用户消息", min_length=1, max_length=8192)
    session_id: str = Field(default="default", description="会话 ID，用于 thread_id 恢复和 compaction")
    user_id: str = Field(default="", description="用户 ID（预留，后续用于个性化）")
    images: list[str] = Field(default=[], description="图片附件（URL 或 data URL，上限 4）", max_length=4)


class ChatResponse(BaseModel):
    reply: str = Field(..., description="助手回复文本")
    session_id: str = Field(..., description="当前会话 ID")
    messages_count: int = Field(..., description="当前消息数（含本轮，便于观察 compaction）")
    usage: dict = Field(default={}, description="LLM token 消耗监控 {input_tokens, output_tokens}")
    latency_ms: float | None = Field(default=None, description="端点总耗时")


@router.post("/api/v1/chat")
async def chat(req: ChatRequest) -> ChatResponse:
    """POST /api/v1/chat

    调用主 deep agent 处理用户消息，返回 AIMessage 文本。

    - 多轮对话：通过 thread_id=session_id 实现
    - 短期记忆：SummarizationMiddleware 自动 compaction
    - 长期记忆：chat_memory_entries（user 分区）+ 首轮注入；AGENTS.md 仅系统级
    - 写纪律：每轮消息逐条落 chat_messages（匿名跳过，尽力而为）
    - 跨会话恢复：SqliteSaver 按 thread_id 恢复 checkpoint
    """
    logger.info(
        "chat.request",
        session_id=req.session_id,
        user_id=req.user_id or "anonymous",
        message_length=len(req.message),
    )

    agent = runtime.main_agent
    if agent is None:
        logger.error("chat.main_agent_not_initialized")
        raise RuntimeError("main_agent 未初始化，请检查 runtime.init() 是否调用")

    config: RunnableConfig = {
        "configurable": {"thread_id": req.session_id, "user_id": req.user_id},
        "run_name": LLMTaskName.MAIN_AGENT_ROUTER.value,
    }
    from agent.memory.injector import inject_memory_entries
    from agent.memory.persistence import persist_turn

    repo = getattr(runtime, "chat_session_repo", None)
    memory_prefix = None
    if repo is not None:
        memory_prefix = await inject_memory_entries(repo, session_id=req.session_id, user_id=req.user_id)

    messages: list[dict] = []
    if memory_prefix:
        messages.append({"role": "user", "content": memory_prefix})
    compaction_prefix = _inject_compaction_summary(repo, req.session_id)
    if compaction_prefix:
        messages.append({"role": "system", "content": compaction_prefix})
    image_paths = await _save_images(req.session_id, req.images)
    if image_paths:
        messages.append(
            {
                "role": "user",
                "content": "用户上传了图片附件（本地路径，可直接作为 image_recognize 的 image_url 入参）："
                + json.dumps(image_paths, ensure_ascii=False)
                + "。如需分析图片内容，请调用 image_recognize 工具。",
            }
        )
    messages.append({"role": "user", "content": req.message})

    with user_context(req.user_id):
        result = await agent.ainvoke(
            {"messages": messages},
            config=config,
        )

    all_messages = result.get("messages", [])
    reply_text = ""
    if all_messages:
        last = all_messages[-1]
        if hasattr(last, "content"):
            reply_text = last.content or ""
        elif isinstance(last, dict):
            reply_text = last.get("content", "")

    # 写纪律：本轮落库（匿名跳过）；提取阈值触发（后台）
    if repo is not None and req.user_id:
        await persist_turn(repo, session_id=req.session_id, user_id=req.user_id, user_msg=req.message, assistant_msgs=[last] if all_messages else None)
        from agent.memory.extractor import maybe_extract

        asyncio.create_task(maybe_extract(repo, session_id=req.session_id, user_id=req.user_id, user_text=req.message))

    logger.info(
        "chat.response",
        session_id=req.session_id,
        messages_count=len(all_messages),
        reply_length=len(reply_text),
    )

    usage: dict = {}
    if all_messages:
        last_msg = all_messages[-1]
        um = getattr(last_msg, "usage_metadata", None) or {}
        if um:
            usage = {
                "input_tokens": int(um.get("input_tokens", 0) or 0),
                "output_tokens": int(um.get("output_tokens", 0) or 0),
            }

    return ChatResponse(
        reply=reply_text,
        session_id=req.session_id,
        messages_count=len(all_messages),
        usage=usage,
    )


@router.post("/api/v1/chat/stream")
async def chat_stream(req: ChatRequest, raw: Request):
    """SSE 流式主 agent 会话。

    事件协议：
    - event: text    → LLM token 增量（data: {token, session_id}）
    - event: tool    → 工具调用阶段（data: {tool, status: start|end, session_id}）
    - event: done    → 结束（data: {reply, messages_count, session_id}）
    - event: error   → 结构化错误（data: {code, message, session_id}）

    路 2 升级：每条事件携带 `id:` 字段（按 session_id 单调递增），
    客户端可通过 `Last-Event-ID` HTTP header 续传。
    """
    agent = runtime.main_agent
    if agent is None:
        raise RuntimeError("main_agent 未初始化，请检查 runtime.init() 是否调用")

    buf = EventBuffer(thread_id=f"chat:{req.session_id}")
    last_event_id = parse_last_event_id(raw.headers.get("Last-Event-ID"))

    async def _generate():
        # 续传：先回放 last_event_id 之后的事件
        for buffered in await buf.replay_from(last_event_id):
            yield sse_with_id(buffered.event, buffered.payload, buffered.event_id)
        config: RunnableConfig = {
            "configurable": {"thread_id": req.session_id, "user_id": req.user_id},
            "run_name": LLMTaskName.MAIN_AGENT_ROUTER.value,
        }
        collected: list[str] = []
        repo = getattr(runtime, "chat_session_repo", None)
        persisted = False
        usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
        first_token_at: float | None = None
        t0 = time.monotonic()
        agent_runs: list[dict] = []
        try:
            from agent.memory.injector import inject_memory_entries

            memory_prefix = None
            if repo is not None:
                memory_prefix = await inject_memory_entries(repo, session_id=req.session_id, user_id=req.user_id)
            messages: list[dict] = []
            if memory_prefix:
                messages.append({"role": "user", "content": memory_prefix})
            compaction_prefix = _inject_compaction_summary(repo, req.session_id)
            if compaction_prefix:
                messages.append({"role": "system", "content": compaction_prefix})
            image_paths = await _save_images(req.session_id, req.images)
            if image_paths:
                messages.append(
                    {
                        "role": "user",
                        "content": "用户上传了图片附件（本地路径，可直接作为 image_recognize 的 image_url 入参）："
                        + json.dumps(image_paths, ensure_ascii=False)
                        + "。如需分析图片内容，请调用 image_recognize 工具。",
                    }
                )
            messages.append({"role": "user", "content": req.message})
            with user_context(req.user_id):
                async for event in agent.astream_events(
                    {"messages": messages},
                    config=config,
                    version="v1",
                ):
                    kind = event.get("event")
                    if kind == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        token = ""
                        if chunk is not None:
                            token = getattr(chunk, "content", None) or ""
                            if isinstance(token, list):
                                token = "".join(
                                    item.get("text", "") for item in token if isinstance(item, dict)
                                )
                        if token:
                            if first_token_at is None:
                                first_token_at = time.monotonic()
                            collected.append(str(token))
                            payload_obj = {"token": str(token), "session_id": req.session_id}
                            payload = json.dumps(payload_obj, ensure_ascii=False)
                            event_id = await buf.append("text", payload)
                            yield sse_with_id("text", payload, event_id)
                    elif kind == "on_chat_model_end":
                        # LLM usage 监控回传（多轮工具循环聚合）
                        output = event.get("data", {}).get("output")
                        um = getattr(output, "usage_metadata", None) or {}
                        usage["input_tokens"] += int(um.get("input_tokens", 0) or 0)
                        usage["output_tokens"] += int(um.get("output_tokens", 0) or 0)
                    elif kind == "on_chain_start":
                        name = event.get("name", "") or ""
                        run_id = event.get("run_id")
                        if name and run_id and _is_agent_run_name(name):
                            agent_runs.append(
                                {
                                    "run_id": str(run_id),
                                    "name": name,
                                    "parent_ids": list(event.get("parent_ids") or []),
                                    "status": "running",
                                }
                            )
                    elif kind == "on_chain_end":
                        run_id = event.get("run_id")
                        for _r in agent_runs:
                            if _r["run_id"] == str(run_id):
                                _r["status"] = "completed"
                    elif kind == "on_chain_error":
                        run_id = event.get("run_id")
                        for _r in agent_runs:
                            if _r["run_id"] == str(run_id):
                                _r["status"] = "error"
                    elif kind in ("on_tool_start", "on_tool_end"):
                        tool_name = event.get("name", "")
                        status = "start" if kind == "on_tool_start" else "end"
                        payload_obj: dict = {"tool": tool_name, "status": status, "session_id": req.session_id}
                        # start 事件附带 args：供 runner 解析 dispatch_module.intent 等
                        # 参数化工具的入参（v1 events API 的 data.input 是 kwargs dict）。
                        # 解析失败回退空 dict，绝不阻塞流。
                        if status == "start":
                            try:
                                data_input = (event.get("data") or {}).get("input")
                                if isinstance(data_input, dict):
                                    payload_obj["args"] = data_input
                            except Exception:  # noqa: BLE001
                                payload_obj["args"] = {}
                        payload = json.dumps(payload_obj, ensure_ascii=False)
                        event_id = await buf.append("tool", payload)
                        yield sse_with_id("tool", payload, event_id)

            reply = "".join(collected)
            messages_count = len(collected)
            # 写纪律：done 前落库（含工具消息：从最终 state 取）
            if repo is not None and req.user_id:
                from agent.memory.persistence import persist_turn

                await persist_turn(
                    repo,
                    session_id=req.session_id,
                    user_id=req.user_id,
                    user_msg=req.message,
                    assistant_msgs=[{"content": reply, "role": "assistant"}],
                    usage_metadata=usage,
                )
                persisted = True
                from agent.memory.extractor import maybe_extract

                asyncio.create_task(maybe_extract(repo, session_id=req.session_id, user_id=req.user_id, user_text=req.message))
            _metrics = getattr(runtime, "metrics_collector", None)
            if _metrics is not None:
                _metrics.record_agent_call("main_agent", True, (time.monotonic() - t0) * 1000)
            done_payload_obj = {
                "reply": reply,
                "messages_count": messages_count,
                "session_id": req.session_id,
                "usage": usage,
                "latency_ms": round((time.monotonic() - t0) * 1000, 1),
                "ttft_ms": round((first_token_at - t0) * 1000, 1) if first_token_at else None,
                "agent_tree": _build_agent_tree(agent_runs),  # Phase 4 E3：委派树契约
                "last_event_id": None,  # 客户端可在 done 事件里读到当前 stream 的最终 event_id（用于重连）
            }
            done_payload = json.dumps(done_payload_obj, ensure_ascii=False)
            done_event_id = await buf.append("done", done_payload)
            done_payload_obj["last_event_id"] = done_event_id
            done_payload = json.dumps(done_payload_obj, ensure_ascii=False)
            yield sse_with_id("done", done_payload, done_event_id)
        except asyncio.CancelledError:
            # 客户端断开 / 用户主动 abort（uvicorn cancel scope）：
            # 不要让 CancelledError 串透 deepagents / langgraph / langsmith 整条栈
            # 在 stderr 喷一整页 traceback。StreamResponse 在被 cancel 后 yield 也送不出去，
            # 所以这里只打 info 级日志，不再 yield error 事件。
            logger.info(
                "chat.stream_cancelled session_id=%s user_id=%s tokens=%d",
                req.session_id,
                req.user_id or "anonymous",
                len(collected),
            )
        except Exception as exc:
            logger.error("chat.stream_error", session_id=req.session_id, error=str(exc))
            _metrics = getattr(runtime, "metrics_collector", None)
            if _metrics is not None:
                _metrics.record_agent_call("main_agent", False, (time.monotonic() - t0) * 1000, str(exc))
            err_payload_obj = {"code": getattr(exc, "code", type(exc).__name__.upper()), "message": str(exc), "session_id": req.session_id}
            err_payload = json.dumps(err_payload_obj, ensure_ascii=False)
            err_event_id = await buf.append("error", err_payload)
            yield sse_with_id("error", err_payload, err_event_id)
        finally:
            # 客户端断开也尽力落库（写纪律的 finally 兜底）。
            # 注意：在 CancelledError 链下 `await` 自身会被打断，把 persist_turn 改成
            # fire-and-forget（asyncio.create_task）才不会因为 disconnect 漏消息。
            # 与 L259 的 `asyncio.create_task(maybe_extract(...))` 同样模式。
            if (
                repo is not None
                and req.user_id
                and not persisted
                and collected
            ):
                from agent.memory.persistence import persist_turn

                reply_so_far = "".join(collected)
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None  # 极小概率：finally 在 loop 关闭后跑
                if loop is not None:
                    asyncio.create_task(
                        persist_turn(
                            repo,
                            session_id=req.session_id,
                            user_id=req.user_id,
                            user_msg=req.message,
                            assistant_msgs=[{"content": reply_so_far, "role": "assistant"}],
                            usage_metadata=usage,
                        )
                    )
                    logger.info(
                        "chat.persist_fire_and_forget session_id=%s tokens=%d",
                        req.session_id,
                        len(collected),
                    )

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _save_images(session_id: str, images: list[str]) -> list[str]:
    """图片附件落盘（data URL/URL → 本地路径），供 image_recognize 读取。

    返回本地路径列表；失败项跳过（尽力而为，不阻塞对话）。
    """
    if not images:
        return []
    import base64
    import uuid
    from pathlib import Path

    from config import get_settings

    out_dir = Path(__file__).resolve().parent.parent / ".documents" / "chat_images" / session_id
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for i, item in enumerate(images[:4]):
        try:
            if item.startswith("data:"):
                _, payload = item.split(",", 1)
                data = base64.b64decode(payload)
                path = out_dir / f"{i}_{uuid.uuid4().hex[:6]}.png"
            else:
                import httpx as _httpx

                resp = _httpx.get(item, verify=get_settings().httpx_verify_ssl, timeout=30)
                resp.raise_for_status()
                data = resp.content
                path = out_dir / f"{i}_{uuid.uuid4().hex[:6]}.png"
            path.write_bytes(data)
            saved.append(str(path))
        except Exception:  # noqa: BLE001
            continue
    return saved


# ── 会话管理（Phase 3.5）：历史会话列表 / 消息回显 / 重命名 / 软删 ──────

class RenameSessionRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)


@router.get("/api/v1/chat/sessions")
async def list_sessions(user_id: str):
    """按 user_id 列出活跃会话（title 空时取首条 user 消息作显示名）。"""
    repo = getattr(runtime, "chat_session_repo", None)
    if repo is None:
        return {"sessions": []}
    return {"sessions": repo.list_sessions_by_user(user_id)}


@router.get("/api/v1/chat/sessions/{session_id}/messages")
async def list_session_messages(session_id: str, user_id: str):
    """回显会话历史消息（归属校验：仅本人可读）。"""
    repo = getattr(runtime, "chat_session_repo", None)
    if repo is None:
        return {"messages": []}
    owner = repo.session_owner(session_id)
    if owner is not None and owner != user_id:
        raise HTTPException(status_code=403, detail="无权访问该会话")
    return {"session_id": session_id, "messages": repo.list_messages(session_id, limit=500)}


@router.post("/api/v1/chat/sessions/{session_id}/rename")
async def rename_session(session_id: str, req: RenameSessionRequest, user_id: str):
    """重命名会话（归属校验）。"""
    repo = getattr(runtime, "chat_session_repo", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="会话仓储不可用")
    owner = repo.session_owner(session_id)
    if owner is not None and owner != user_id:
        raise HTTPException(status_code=403, detail="无权操作该会话")
    ok = repo.rename_session(session_id, user_id, req.title)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在或无权操作")
    return {"status": "ok"}


@router.delete("/api/v1/chat/sessions/{session_id}")
async def close_session(session_id: str, user_id: str):
    """软删会话（status=closed，保留记忆提取水位）。"""
    repo = getattr(runtime, "chat_session_repo", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="会话仓储不可用")
    owner = repo.session_owner(session_id)
    if owner is not None and owner != user_id:
        raise HTTPException(status_code=403, detail="无权操作该会话")
    ok = repo.close_session(session_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在或无权操作")
    return {"status": "ok"}