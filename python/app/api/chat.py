"""v2 主 Agent 统一会话路由 — Phase 3 实现

当前状态：路由骨架预留。

Phase 3 实现目标：
  POST /chat
    请求：application/json
      message: str
      session_id: str
      user_id: str
    响应：SSE 流式
      event: token       — 普通 token
      event: tool_call   — 工具调用事件（tool_name, args）
      event: tool_result — 工具返回事件（tool_name, result）
      event: final       — 最终回答

  实现参考：
    router = APIRouter()

    @router.post("/chat")
    async def chat(message: str, session_id: str, user_id: str):
        # 委派主 deep agent
        ...
        return StreamingResponse(...)

架构决策：
  - 调用 agent/ 下的主 deep agent（deepagents harness）
  - 会话管理（compaction / checkpointing）在 agent/ 层实现，此文件不处理
  - 路由（意图识别 → tool/subagent）由主 agent LLM 推理，不在此文件硬编码
"""
from fastapi import APIRouter

router = APIRouter()