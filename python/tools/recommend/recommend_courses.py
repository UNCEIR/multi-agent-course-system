# -*- coding: utf-8 -*-
"""recommend_courses tool — 包装 v1 推荐链路为 deepagents 可调用的 tool。

基于 v1 的 SupervisorOrchestrator 和 LangGraph subgraph 实现课程推荐。
Phase 1 Step 3 实装完整功能，当前为 stub 骨架。

Phase: 1 (stub — NotImplementedError)
"""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class RecommendCoursesInput(BaseModel):
    """recommend_courses 工具输入参数。"""
    user_id: str = Field(default="", description="用户 ID（可选，有则提供个性化推荐）")
    query: str = Field(default="", description='用户偏好描述（如"不考试的公选课"）')
    num_items: int = Field(default=10, description="推荐课程数量", ge=1, le=50)


@tool(args_schema=RecommendCoursesInput)
def recommend_courses(
    user_id: str = "",
    query: str = "",
    num_items: int = 10,
) -> str:
    """根据用户偏好推荐公选课程。

    包装 v1 SupervisorOrchestrator 推荐链路，支持：
    - 自然语言描述偏好（不考试、作业少、某校区等）
    - 冷启动（无历史数据时基于 query 关键词召回）
    - 硬约束过滤 + 语义重排 + 可行性分析

    Args:
        user_id: 用户 ID（可选，有则提供个性化推荐）
        query: 用户偏好描述（如"不考试的公选课"）
        num_items: 推荐课程数量（默认 10）

    Returns:
        推荐结果 JSON 字符串（课程列表 + 推荐理由 + 选课建议）
    """
    # Phase 1 Step 3 接入 v1 SupervisorOrchestrator
    raise NotImplementedError(
        f"recommend_courses: Phase 1 Step 3 接入 v1 推荐链路。\n"
        f"用户：{user_id}，查询：{query}，数量：{num_items}"
    )