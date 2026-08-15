"""v2 主 Agent 统一会话路由。

- POST /api/v1/chat         同步返回（兼容后端调用）
- POST /api/v1/chat/stream  SSE 流式（前端主对话框，含 token/工具阶段/done/error）
"""

from __future__ import annotations

import asyncio
import json
import time

import structlog
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from agent import runtime
from agent.main.context import user_context
from ai.llm_task_name import LLMTaskName

logger = structlog.get_logger()
router = APIRouter()


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

        asyncio.create_task(maybe_extract(repo, session_id=req.session_id, user_id=req.user_id))

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
async def chat_stream(req: ChatRequest):
    """SSE 流式主 agent 会话。

    事件协议：
    - event: text    → LLM token 增量（data: {token, session_id}）
    - event: tool    → 工具调用阶段（data: {tool, status: start|end, session_id}）
    - event: done    → 结束（data: {reply, messages_count, session_id}）
    - event: error   → 结构化错误（data: {code, message, session_id}）
    """
    agent = runtime.main_agent
    if agent is None:
        raise RuntimeError("main_agent 未初始化，请检查 runtime.init() 是否调用")

    async def _generate():
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
        try:
            from agent.memory.injector import inject_memory_entries

            memory_prefix = None
            if repo is not None:
                memory_prefix = await inject_memory_entries(repo, session_id=req.session_id, user_id=req.user_id)
            messages: list[dict] = []
            if memory_prefix:
                messages.append({"role": "user", "content": memory_prefix})
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
                            yield _sse("text", {"token": str(token), "session_id": req.session_id})
                    elif kind == "on_chat_model_end":
                        # LLM usage 监控回传（多轮工具循环聚合）
                        output = event.get("data", {}).get("output")
                        um = getattr(output, "usage_metadata", None) or {}
                        usage["input_tokens"] += int(um.get("input_tokens", 0) or 0)
                        usage["output_tokens"] += int(um.get("output_tokens", 0) or 0)
                    elif kind in ("on_tool_start", "on_tool_end"):
                        tool_name = event.get("name", "")
                        status = "start" if kind == "on_tool_start" else "end"
                        yield _sse("tool", {"tool": tool_name, "status": status, "session_id": req.session_id})

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
                )
                persisted = True
                from agent.memory.extractor import maybe_extract

                asyncio.create_task(maybe_extract(repo, session_id=req.session_id, user_id=req.user_id))
            yield _sse(
                "done",
                {
                    "reply": reply,
                    "messages_count": messages_count,
                    "session_id": req.session_id,
                    "usage": usage,
                    "latency_ms": round((time.monotonic() - t0) * 1000, 1),
                    "ttft_ms": round((first_token_at - t0) * 1000, 1) if first_token_at else None,
                },
            )
        except Exception as exc:
            logger.error("chat.stream_error", session_id=req.session_id, error=str(exc))
            yield _sse(
                "error",
                {"code": type(exc).__name__.upper(), "message": str(exc), "session_id": req.session_id},
            )
        finally:
            # 客户端断开也尽力落库（写纪律的 finally 兜底）
            if repo is not None and req.user_id and not persisted:
                try:
                    from agent.memory.persistence import persist_turn

                    await persist_turn(
                        repo,
                        session_id=req.session_id,
                        user_id=req.user_id,
                        user_msg=req.message,
                        assistant_msgs=[{"content": "".join(collected), "role": "assistant"}],
                    )
                except Exception:  # noqa: BLE001
                    pass

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