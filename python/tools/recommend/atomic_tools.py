# -*- coding: utf-8 -*-
"""推荐原子工具集 — 7 个独立 @tool，供 SKILL 驱动的主 agent 编排调用。

与 v1 ReAct 内部编排（ReactToolExecutor）不同，这些工具是注册到 ToolRegistry 的
独立 LangChain @tool，由 deepagents 主 agent 读 SKILL.md 后自行按步骤调用。

状态传递：profile 用结构化 JSON，courses 用 course_id 列表（工具内部从 MySQL 还原
完整对象，避免把 150 门课塞进 LLM 上下文）。user_id 从 agent.main.context 注入。
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from agent.main.context import get_current_user_id


class ExtractProfileInput(BaseModel):
    """extract_profile 工具输入参数。"""
    prompt: str = Field(..., description="学生选课需求自然语言描述", min_length=1, max_length=2000)


class SearchCoursesInput(BaseModel):
    """search_courses 工具输入参数。"""
    strategy: str = Field(default="wide", description="召回策略：wide=宽召回（无画像）/ refined=精召回（需画像）")
    profile_json: str = Field(default="", description="extract_profile 输出的画像 JSON（refined 策略必填）")
    query: str = Field(default="", description="选课需求文本")


class FilterHardConstraintsInput(BaseModel):
    """filter_hard_constraints 工具输入参数。"""
    profile_json: str = Field(..., description="学生画像 JSON（含 hard_constraints）")
    course_ids: list[str] = Field(..., description="候选课程 course_id 列表")


class SemanticFilterCoursesInput(BaseModel):
    """semantic_filter_courses 工具输入参数。"""
    profile_json: str = Field(..., description="学生画像 JSON")
    course_ids: list[str] = Field(..., description="候选课程 course_id 列表")
    target_count: int = Field(default=40, description="目标保留数量", ge=1, le=100)


class RerankCoursesInput(BaseModel):
    """rerank_courses 工具输入参数。"""
    profile_json: str = Field(default="", description="学生画像 JSON（可为空，空则规则重排）")
    course_ids: list[str] = Field(..., description="候选课程 course_id 列表")
    num_items: int = Field(default=10, description="返回课程数量", ge=1, le=50)


class CheckFeasibilityInput(BaseModel):
    """check_feasibility 工具输入参数。"""
    course_ids: list[str] = Field(..., description="候选课程 course_id 列表")
    context_json: str = Field(default="{}", description="上下文 JSON（时间冲突等）")


class GenerateReasonsInput(BaseModel):
    """generate_reasons 工具输入参数。"""
    profile_json: str = Field(default="", description="学生画像 JSON")
    course_ids: list[str] = Field(..., description="最终课程 course_id 列表")
    warnings_json: str = Field(default="[]", description="风险/警告 JSON 列表")


def _hydrate_courses(course_ids: list[str]) -> list[Any]:
    """按 course_id 列表从 MySQL 还原完整课程对象（保持列表顺序）。"""
    if not course_ids:
        return []
    from storage.mysql.course_repo import CourseRepository

    return CourseRepository().fetch_courses_by_ids(course_ids)


def _load_profile(profile_json: str) -> Any | None:
    if not profile_json:
        return None
    from models.schemas import StudentProfile

    try:
        return StudentProfile(**json.loads(profile_json))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


@tool(args_schema=ExtractProfileInput)
async def extract_profile(prompt: str) -> str:
    """提取学生画像与硬约束（结构化 JSON）。

    调用 v1 StudentProfileAgent，从自然语言需求中抽取兴趣、校区、时间、
    考试偏好等，并识别硬约束（校区/类别/不考试等）。
    """
    from agent import runtime

    user_id = get_current_user_id()
    if runtime.supervisor is None:
        return json.dumps({"error": "supervisor 未初始化"}, ensure_ascii=False)
    result = await runtime.supervisor.student_profile_agent.run(
        user_id=user_id,
        prompt=prompt,
        context={},
    )
    profile = getattr(result, "profile", None)
    if profile is None:
        return json.dumps({"error": "画像提取失败"}, ensure_ascii=False)
    return json.dumps(profile.model_dump(mode="json"), ensure_ascii=False)


@tool(args_schema=SearchCoursesInput)
async def search_courses(strategy: str = "wide", profile_json: str = "", query: str = "") -> str:
    """召回候选课程（返回 course_id 列表 JSON）。

    wide=基于 query 宽召回；refined=基于画像精召回。返回 ["course_id", ...]。
    """
    from agent import runtime

    if runtime.supervisor is None:
        return json.dumps({"course_ids": [], "error": "supervisor 未初始化"}, ensure_ascii=False)
    profile = _load_profile(profile_json)
    sp = profile if strategy == "refined" else None
    result = await runtime.supervisor.course_recall_agent.run(
        student_profile=sp,
        prompt=query,
        context={},
        num_items=20,
    )
    courses = getattr(result, "courses", [])
    return json.dumps(
        {"course_ids": [c.course_id for c in courses], "count": len(courses)},
        ensure_ascii=False,
    )


@tool(args_schema=FilterHardConstraintsInput)
async def filter_hard_constraints(profile_json: str, course_ids: list[str]) -> str:
    """硬约束确定性过滤（不可跳过）。返回过滤后 course_id 列表与 warnings。"""
    from agent import runtime

    profile = _load_profile(profile_json)
    courses = _hydrate_courses(course_ids)
    if profile is None or not courses:
        return json.dumps({"course_ids": course_ids, "warnings": []}, ensure_ascii=False)
    filtered, _hc_filtered, hc_warnings = runtime.supervisor.hard_constraint_filter.filter(
        courses, profile.hard_constraints
    )
    return json.dumps(
        {
            "course_ids": [c.course_id for c in filtered],
            "removed_count": len(course_ids) - len(filtered),
            "warnings": hc_warnings,
        },
        ensure_ascii=False,
    )


@tool(args_schema=SemanticFilterCoursesInput)
async def semantic_filter_courses(profile_json: str, course_ids: list[str], target_count: int = 40) -> str:
    """LLM 语义初筛候选课程（可选）。返回初筛后 course_id 列表。"""
    import asyncio

    from agent import runtime

    profile = _load_profile(profile_json)
    courses = _hydrate_courses(course_ids)
    if profile is None or not courses:
        return json.dumps({"course_ids": course_ids}, ensure_ascii=False)
    try:
        # _llm_semantic_filter 不在 BaseAgent 的 wait_for 覆盖内，此处补超时
        filtered = await asyncio.wait_for(
            runtime.supervisor._llm_semantic_filter(courses, profile, target_count=target_count),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        return json.dumps({"course_ids": course_ids, "skipped": "timeout"}, ensure_ascii=False)
    return json.dumps(
        {"course_ids": [c.course_id for c in filtered], "count": len(filtered)},
        ensure_ascii=False,
    )


@tool(args_schema=RerankCoursesInput)
async def rerank_courses(profile_json: str, course_ids: list[str], num_items: int = 10) -> str:
    """按画像偏好 + Milvus 语义融合重排。返回排序后 course_id 列表。"""
    from agent import runtime

    profile = _load_profile(profile_json)
    courses = _hydrate_courses(course_ids)
    if not courses:
        return json.dumps({"course_ids": []}, ensure_ascii=False)
    result = await runtime.supervisor.course_rerank_agent.run(
        student_profile=profile,
        candidates=courses,
        num_items=num_items,
    )
    ranked = getattr(result, "courses", courses)
    return json.dumps(
        {"course_ids": [c.course_id for c in ranked][:num_items], "strategy": getattr(result, "rerank_strategy", "")},
        ensure_ascii=False,
    )


@tool(args_schema=CheckFeasibilityInput)
async def check_feasibility(course_ids: list[str], context_json: str = "{}") -> str:
    """容量/时间冲突/风险检查。返回可用 course_id 列表与 warnings。"""
    from agent import runtime

    courses = _hydrate_courses(course_ids)
    if not courses:
        return json.dumps({"course_ids": [], "warnings": []}, ensure_ascii=False)
    try:
        context = json.loads(context_json) if context_json else {}
    except json.JSONDecodeError:
        context = {}
    result = await runtime.supervisor.course_feasibility_agent.run(
        student_profile=None,
        courses=courses,
        context=context,
    )
    available = getattr(result, "available_courses", [])
    warnings = getattr(result, "selection_warnings", [])
    return json.dumps(
        {"course_ids": list(available), "warnings": warnings},
        ensure_ascii=False,
    )


@tool(args_schema=GenerateReasonsInput)
async def generate_reasons(profile_json: str, course_ids: list[str], warnings_json: str = "[]") -> str:
    """为最终课程生成推荐理由（含引用来源）。返回 reasons JSON。"""
    from agent import runtime

    profile = _load_profile(profile_json)
    courses = _hydrate_courses(course_ids)
    if not courses:
        return json.dumps({"reasons": []}, ensure_ascii=False)
    try:
        warnings = json.loads(warnings_json) if warnings_json else []
    except json.JSONDecodeError:
        warnings = []
    result = await runtime.supervisor.recommendation_reason_agent.run(
        student_profile=profile,
        courses=courses,
        warnings=warnings,
    )
    return json.dumps({"reasons": getattr(result, "reasons", [])}, ensure_ascii=False)
