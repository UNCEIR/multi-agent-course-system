"""
LangGraph state graph for the public elective course recommendation pipeline.

  [start] -> init
          -> {student_profile, course_recall}      (parallel)
          -> semantic_filter
          -> {course_rerank, course_feasibility}   (parallel)
          -> filter
          -> recommendation_reason
          -> aggregate -> [end]
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from agent.recommend.agents import (
    CourseFeasibilityAgent,
    CourseRecallAgent,
    CourseRerankAgent,
    RecommendationReasonAgent,
    StudentProfileAgent,
)
from models.schemas import Course, StudentProfile
from ai import LLMTaskName, build_chat_openai
from experiment.ab_test import ABTestEngine


class PipelineState(TypedDict, total=False):
    request_id: str
    user_id: str
    scene: str
    num_items: int
    prompt: str
    context: dict[str, Any]
    experiment_group: str

    student_profile: StudentProfile | None
    raw_courses: list[Course]
    ranked_courses: list[Course]
    available_ids: set[str]
    final_courses: list[Course]
    recommendation_reasons: list[dict[str, str]]
    selection_warnings: list[dict[str, Any]]
    priority_advice: dict[str, Any]

    agent_results: dict[str, Any]
    total_latency_ms: float
    _start_time: float


student_profile_agent = StudentProfileAgent()
course_recall_agent = CourseRecallAgent()
course_rerank_agent = CourseRerankAgent()
course_feasibility_agent = CourseFeasibilityAgent()
recommendation_reason_agent = RecommendationReasonAgent()
ab_engine = ABTestEngine()


async def init_node(state: PipelineState) -> PipelineState:
    state["request_id"] = str(uuid.uuid4())
    state["_start_time"] = time.perf_counter()
    state["agent_results"] = {}
    exp = ab_engine.assign(state["user_id"], "react_vs_pipeline")
    state["experiment_group"] = exp.get("group", "control")
    return state


async def student_profile_node(state: PipelineState) -> PipelineState:
    result = await student_profile_agent.run(
        user_id=state["user_id"],
        prompt=state.get("prompt", ""),
        context=state.get("context", {}),
    )
    state["student_profile"] = getattr(result, "profile", None)
    state["agent_results"]["student_profile"] = result
    return state


async def course_recall_node(state: PipelineState) -> PipelineState:
    result = await course_recall_agent.run(
        student_profile=state.get("student_profile"),
        prompt=state.get("prompt", ""),
        context=state.get("context", {}),
        num_items=state.get("num_items", 10) * 2,
    )
    state["raw_courses"] = getattr(result, "courses", [])
    state["agent_results"]["course_recall"] = result
    return state


async def parallel_phase1(state: PipelineState) -> PipelineState:
    profile_state, recall_state = await asyncio.gather(
        student_profile_node(dict(state)),
        course_recall_node(dict(state)),
    )
    state.update(profile_state)
    state.update(recall_state)
    return state


async def course_rerank_node(state: PipelineState) -> PipelineState:
    result = await course_rerank_agent.run(
        student_profile=state.get("student_profile"),
        candidates=state.get("raw_courses", []),
        num_items=state.get("num_items", 10),
    )
    state["ranked_courses"] = getattr(result, "courses", state.get("raw_courses", []))
    state["agent_results"]["course_rerank"] = result
    return state


async def course_feasibility_node(state: PipelineState) -> PipelineState:
    result = await course_feasibility_agent.run(
        student_profile=state.get("student_profile"),
        courses=state.get("raw_courses", []),
        context=state.get("context", {}),
    )
    state["available_ids"] = set(getattr(result, "available_courses", []))
    state["selection_warnings"] = getattr(result, "selection_warnings", [])
    priority_advice = getattr(result, "priority_advice", {})
    state["priority_advice"] = {cid: pa.model_dump() for cid, pa in priority_advice.items()}
    state["agent_results"]["course_feasibility"] = result
    return state


async def parallel_phase2(state: PipelineState) -> PipelineState:
    rerank_state, feasibility_state = await asyncio.gather(
        course_rerank_node(dict(state)),
        course_feasibility_node(dict(state)),
    )
    state.update(rerank_state)
    state.update(feasibility_state)
    return state


async def filter_node(state: PipelineState) -> PipelineState:
    ranked = state.get("ranked_courses", [])
    available = state.get("available_ids", set())
    num = state.get("num_items", 10)
    state["final_courses"] = [course for course in ranked if course.course_id in available][:num]
    return state


async def recommendation_reason_node(state: PipelineState) -> PipelineState:
    result = await recommendation_reason_agent.run(
        student_profile=state.get("student_profile"),
        courses=state.get("final_courses", []),
        warnings=state.get("selection_warnings", []),
    )
    state["recommendation_reasons"] = getattr(result, "reasons", [])
    state["agent_results"]["recommendation_reason"] = result
    return state


async def semantic_filter_node(state: PipelineState) -> PipelineState:
    courses = state.get("raw_courses", [])
    profile = state.get("student_profile")
    MAX_SEMANTIC_INPUT = 200
    if len(courses) > MAX_SEMANTIC_INPUT:
        courses = sorted(courses, key=lambda x: x.score, reverse=True)[:MAX_SEMANTIC_INPUT]
    if not profile or len(courses) <= 40:
        return state
    course_data = []
    for c in courses:
        desc = (c.description or "")[:80]
        tags_str = ", ".join(c.tags[:5]) if c.tags else ""
        course_data.append({
            "id": c.course_id,
            "name": c.course_name,
            "domain": c.domain,
            "category": c.course_category,
            "campus": c.campus,
            "desc": desc,
            "tags": tags_str,
            "difficulty": c.difficulty,
            "has_exam": c.has_exam,
            "popularity": c.popularity_level,
        })
    profile_data = {
        "interests": profile.interests,
        "preferred_domains": profile.preferred_domains,
        "preferred_campus": profile.preferred_campus,
        "exam_preference": profile.exam_preference,
        "workload_preference": profile.workload_preference,
        "difficulty_preference": profile.difficulty_preference,
        "grade": profile.grade,
    }
    system_prompt = (
        "你是课程语义匹配专家。根据学生画像从候选课程中选出 40 门真正相关的。"
        "判断标准：课程名称+描述+标签是否真实匹配学生的兴趣和偏好（不是只看 domain 字段）。"
        "返回 JSON 数组：[\"course_id_1\", \"course_id_2\", ...]"
    )
    user_prompt = json.dumps({"student": profile_data, "candidates": course_data}, ensure_ascii=False)
    try:
        llm = build_chat_openai(temperature=0, max_tokens=2048, task_name=LLMTaskName.GRAPH_SEMANTIC_FILTER)
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        raw = (response.content or "").strip()
        if not raw:
            return state
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        ids = json.loads(raw)
        if isinstance(ids, list) and ids:
            id_set = {str(i) for i in ids}
            filtered = [c for c in courses if c.course_id in id_set]
            if filtered:
                state["raw_courses"] = filtered[:40]
    except Exception:
        pass
    return state


async def aggregate_node(state: PipelineState) -> PipelineState:
    state["total_latency_ms"] = (time.perf_counter() - state.get("_start_time", 0)) * 1000
    return state


def build_recommendation_graph() -> StateGraph:
    graph = StateGraph(PipelineState)
    graph.add_node("init", init_node)
    graph.add_node("parallel_phase1", parallel_phase1)
    graph.add_node("semantic_filter", semantic_filter_node)
    graph.add_node("parallel_phase2", parallel_phase2)
    graph.add_node("filter", filter_node)
    graph.add_node("recommendation_reason", recommendation_reason_node)
    graph.add_node("aggregate", aggregate_node)

    graph.set_entry_point("init")
    graph.add_edge("init", "parallel_phase1")
    graph.add_edge("parallel_phase1", "semantic_filter")
    graph.add_edge("semantic_filter", "parallel_phase2")
    graph.add_edge("parallel_phase2", "filter")
    graph.add_edge("filter", "recommendation_reason")
    graph.add_edge("recommendation_reason", "aggregate")
    graph.add_edge("aggregate", END)
    return graph.compile()
