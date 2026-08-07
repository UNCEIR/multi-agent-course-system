"""v2 主 Agent 统一会话路由 — 实装 POST /api/v1/chat。

使用 deepagents 主 agent（build_main_agent）实现多轮对话、记忆管理、意图识别。
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agent import runtime

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
    agent = runtime.main_agent
    if agent is None:
        raise RuntimeError("main_agent 未初始化，请检查 runtime.init() 是否调用")

    config = {"configurable": {"thread_id": req.session_id}}
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

    return ChatResponse(
        reply=reply_text,
        session_id=req.session_id,
        messages_count=len(messages),
    )