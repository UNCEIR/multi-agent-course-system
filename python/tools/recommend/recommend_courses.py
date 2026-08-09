# -*- coding: utf-8 -*-
"""将 v1 Supervisor 推荐链路暴露为 deepagents tool。

工具内部消费统一流式入口（stream_recommend_unified：默认 ReAct → 兜底 Pipeline），
对外仍返回聚合后的完整 JSON 字符串，保持 deepagents 工具契约不变。

user_id 由系统统一注入（agent.main.context），不依赖 LLM 从对话猜测。
"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from agent import runtime
from agent.main.context import get_current_user_id
from models.schemas import RecommendationRequest


class RecommendCoursesInput(BaseModel):
    """recommend_courses 工具输入参数。"""
    query: str = Field(default="", description='用户偏好描述（如"不考试的公选课"）')
    num_items: int = Field(default=10, description="推荐课程数量", ge=1, le=50)
    mode: str = Field(default="pipeline", description="编排模式：pipeline（并行，快，默认）/ react（多轮决策，慢）")


async def stream_recommend_courses(
    query: str = "",
    num_items: int = 10,
    mode: str = "pipeline",
) -> AsyncGenerator[dict[str, Any], None]:
    """内部流式推荐生成器（默认并行 Pipeline，可选 ReAct）。

    yield 阶段事件（phase/course_start/text/course_end/done/error），
    供日志、指标埋点或前端 SSE 复用；与 /api/v1/recommend/stream 同源。
    user_id 从用户上下文读取，实现个性化（冷启动时为空）。
    """
    if runtime.supervisor is None:
        raise RuntimeError("recommendation supervisor 未初始化")
    request = RecommendationRequest(
        user_id=get_current_user_id(),
        query=query,
        prompt=query,
        num_items=num_items,
    )
    async for event in runtime.supervisor.stream_recommend_unified(request, mode=mode):
        yield event


@tool(args_schema=RecommendCoursesInput)
async def recommend_courses(
    query: str = "",
    num_items: int = 10,
    mode: str = "pipeline",
) -> str:
    """根据用户偏好推荐公选课程。

    包装 v1 SupervisorOrchestrator 推荐链路，支持：
    - 自然语言描述偏好（不考试、作业少、某校区等）
    - 冷启动（无历史数据时基于 query 关键词召回）
    - 硬约束过滤 + 语义重排 + 可行性分析
    - 默认并行 Pipeline（快）；mode="react" 时走 ReAct 编排

    Args:
        query: 用户偏好描述（如"不考试的公选课"）
        num_items: 推荐课程数量（默认 10）
        mode: 编排模式（pipeline 默认 / react 可选）

    Returns:
        推荐结果 JSON 字符串（课程列表 + 推荐理由 + 选课建议）
    """
    if runtime.supervisor is None:
        raise RuntimeError("recommendation supervisor 未初始化")

    done_payload: dict[str, Any] = {}
    async for event in stream_recommend_courses(
        query=query,
        num_items=num_items,
        mode=mode,
    ):
        if event["event"] == "done":
            done_payload = event["data"]
        elif event["event"] == "error":
            raise RuntimeError(
                f"推荐失败: {event['data'].get('code', '')} {event['data'].get('message', '')}"
            )

    if not done_payload:
        raise RuntimeError("推荐链路未产出结果")
    return json.dumps(done_payload, ensure_ascii=False)
