"""v2 主 Agent 统一会话路由。

- POST /api/v1/chat         同步返回（兼容后端调用）
- POST /api/v1/chat/stream  SSE 流式（前端主对话框，含 token/工具阶段/done/error）
"""

from __future__ import annotations

import json

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


class ChatResponse(BaseModel):
    reply: str = Field(..., description="助手回复文本")
    session_id: str = Field(..., description="当前会话 ID")
    messages_count: int = Field(..., description="当前消息数（含本轮，便于观察 compaction）")


@router.post("/api/v1/chat")
async def chat(req: ChatRequest) -> ChatResponse:
    """POST /api/v1/chat

    调用主 deep agent 处理用户消息，返回 AIMessage 文本。

    - 多轮对话：通过 thread_id=session_id 实现
    - 短期记忆：SummarizationMiddleware 自动 compaction
    - 长期记忆：MemoryMiddleware 加载 AGENTS.md，agent 用 edit_file 更新
    - 意图识别：SkillsMiddleware 注入 skill 索引，LLM 推理匹配
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
    with user_context(req.user_id):
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": req.message}]},
            config=config,
        )

    messages = result.get("messages", [])
    reply_text = ""
    if messages:
        last = messages[-1]
        if hasattr(last, "content"):
            reply_text = last.content or ""
        elif isinstance(last, dict):
            reply_text = last.get("content", "")

    logger.info(
        "chat.response",
        session_id=req.session_id,
        messages_count=len(messages),
        reply_length=len(reply_text),
    )

    return ChatResponse(
        reply=reply_text,
        session_id=req.session_id,
        messages_count=len(messages),
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
        try:
            with user_context(req.user_id):
                async for event in agent.astream_events(
                    {"messages": [{"role": "user", "content": req.message}]},
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
                            collected.append(str(token))
                            yield _sse("text", {"token": str(token), "session_id": req.session_id})
                    elif kind in ("on_tool_start", "on_tool_end"):
                        tool_name = event.get("name", "")
                        status = "start" if kind == "on_tool_start" else "end"
                        yield _sse("tool", {"tool": tool_name, "status": status, "session_id": req.session_id})

            reply = "".join(collected)
            messages_count = len(collected)
            yield _sse(
                "done",
                {"reply": reply, "messages_count": messages_count, "session_id": req.session_id},
            )
        except Exception as exc:
            logger.error("chat.stream_error", session_id=req.session_id, error=str(exc))
            yield _sse(
                "error",
                {"code": type(exc).__name__.upper(), "message": str(exc), "session_id": req.session_id},
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