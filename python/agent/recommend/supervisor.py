"""
公选课推荐 Supervisor 编排器

用户输入自然语言选课需求后，Supervisor 负责并行调度专业 Agent：

Phase 1:   学生画像 Agent 与课程召回 Agent 并行
Phase 1.5: HardConstraintFilter 确定性硬约束过滤（违反即移除，不参与重排）
Phase 2:   课程重排 Agent 与选课可行性 Agent 并行
Phase 3:   推荐理由 Agent 串行生成可解释建议
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, AsyncGenerator, TYPE_CHECKING

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from models.schemas import Course, RecommendationRequest, RecommendationResponse, StudentProfile
from agent.recommend.hard_constraint_filter import HardConstraintFilter, has_active_constraints
from ai import LLMTaskName, build_chat_openai
from experiment.ab_test import ABTestEngine
from config import get_settings

logger = structlog.get_logger()

if TYPE_CHECKING:
    from agent.recommend.agents import (
        CourseFeasibilityAgent,
        CourseRecallAgent,
        CourseRerankAgent,
        RecommendationReasonAgent,
        StudentProfileAgent,
    )


class SupervisorOrchestrator:
    """Coordinates public elective course agents in a parallel-then-aggregate pattern."""

    def __init__(
        self,
        ab_engine: ABTestEngine | None = None,
        student_profile_agent: StudentProfileAgent | None = None,
        course_recall_agent: CourseRecallAgent | None = None,
        course_rerank_agent: CourseRerankAgent | None = None,
        course_feasibility_agent: CourseFeasibilityAgent | None = None,
        recommendation_reason_agent: RecommendationReasonAgent | None = None,
    ):
        if student_profile_agent is None:
            from agent.recommend.agents import StudentProfileAgent

            student_profile_agent = StudentProfileAgent()
        if course_recall_agent is None:
            from agent.recommend.agents import CourseRecallAgent

            course_recall_agent = CourseRecallAgent()
        if course_rerank_agent is None:
            from agent.recommend.agents import CourseRerankAgent

            course_rerank_agent = CourseRerankAgent()
        if course_feasibility_agent is None:
            from agent.recommend.agents import CourseFeasibilityAgent

            course_feasibility_agent = CourseFeasibilityAgent()
        if recommendation_reason_agent is None:
            from agent.recommend.agents import RecommendationReasonAgent

            recommendation_reason_agent = RecommendationReasonAgent()

        self.student_profile_agent = student_profile_agent
        self.course_recall_agent = course_recall_agent
        self.course_rerank_agent = course_rerank_agent
        self.course_feasibility_agent = course_feasibility_agent
        self.recommendation_reason_agent = recommendation_reason_agent
        self.ab_engine = ab_engine or ABTestEngine()
        self.hard_constraint_filter = HardConstraintFilter()
        self._react_llm_cache: dict[str, Any] = {}

    async def recommend(
        self,
        request: RecommendationRequest,
        *,
        _allow_react: bool = True,
    ) -> RecommendationResponse:
        request_id = str(uuid.uuid4())
        start = time.perf_counter()
        prompt = self._request_prompt(request)

        logger.info(
            "course_supervisor.start",
            request_id=request_id,
            user_id=request.user_id,
            scene=request.scene,
            prompt_chars=len(prompt),
            context_keys=sorted(request.context.keys()),
            prompt=prompt,
        )

        experiment = self.ab_engine.assign(request.user_id, "react_vs_pipeline")

        # A/B test routing: react group uses LLM-driven tool calling pipeline
        if experiment.get("group") == "react" and _allow_react:
            try:
                response = await self._react_recommend(request, request_id, start)
                response.experiment_group = "react"
                return response
            except Exception as exc:
                logger.exception(
                    "course_supervisor.react_failed_fallback_pipeline",
                    request_id=request_id,
                    error=str(exc),
                )
                self.ab_engine.record_outcome("react_vs_pipeline", "react", success=False)
                response = await self.recommend(request, _allow_react=False)
                response.experiment_group = "pipeline_fallback"
                response.selection_warnings.insert(
                    0,
                    {
                        "type": "react_fallback",
                        "level": "medium",
                        "message": "ReAct 编排暂时不可用，已降级到确定性推荐流程。",
                        "error": type(exc).__name__,
                    },
                )
                return response

        # Phase 1: 学生画像与课程召回并行。召回先用原始 prompt 和 context 做宽召回。
        profile_result, recall_result = await asyncio.gather(
            self.student_profile_agent.run(
                user_id=request.user_id,
                prompt=prompt,
                context=request.context,
            ),
            self.course_recall_agent.run(
                student_profile=None,
                prompt=prompt,
                context=request.context,
                num_items=request.num_items * 2,
            ),
        )

        student_profile: StudentProfile | None = getattr(profile_result, "profile", None)
        raw_courses: list[Course] = getattr(recall_result, "courses", [])
        if not isinstance(getattr(recall_result, "data", None), dict):
            recall_result.data = {}
        logger.info(
            "course_supervisor.phase1_complete",
            request_id=request_id,
            profile_extracted=student_profile is not None,
            wide_recall_count=len(raw_courses),
            recall_success=getattr(recall_result, "success", False),
            hard_constraints=self._hard_constraint_snapshot(student_profile),
            wide_recall_strategies=getattr(recall_result, "recall_strategies", []),
        )

        # 如果画像提取出了强约束，再补一次轻量结构化召回，避免只靠宽召回漏掉课程。
        if student_profile:
            refined_result = await self.course_recall_agent.run(
                student_profile=student_profile,
                prompt=prompt,
                context=request.context,
                num_items=request.num_items * 2,
            )
            raw_courses = self._merge_courses(
                raw_courses,
                getattr(refined_result, "courses", []),
            )
            recall_result.data["wide_recall_strategies"] = getattr(recall_result, "recall_strategies", [])
            recall_result.data["refined_recall_strategies"] = getattr(refined_result, "recall_strategies", [])
            recall_result.data["refined_candidate_count"] = len(raw_courses)
            logger.info(
                "course_supervisor.refined_recall_complete",
                request_id=request_id,
                refined_count=len(getattr(refined_result, "courses", [])),
                merged_candidate_count=len(raw_courses),
                refined_strategies=getattr(refined_result, "recall_strategies", []),
            )

        # Phase 1.5: 硬约束确定性过滤 — 违反硬约束的课程不进入重排。
        warnings: list[dict[str, Any]] = []
        if student_profile and has_active_constraints(student_profile.hard_constraints):
            pre_filter_summary = self._course_axis_summary(raw_courses)
            raw_courses, hc_filtered, hc_warnings = self.hard_constraint_filter.filter(
                raw_courses, student_profile.hard_constraints
            )
            warnings.extend(hc_warnings)
            logger.info(
                "course_supervisor.phase15_complete",
                request_id=request_id,
                hard_filtered_count=len(hc_filtered),
                remaining_after_filter=len(raw_courses),
                hard_constraints=self._hard_constraint_snapshot(student_profile),
                before_filter_summary=pre_filter_summary,
                after_filter_summary=self._course_axis_summary(raw_courses),
            )

        # Phase 1.75: LLM 语义初筛 — 从硬约束过滤后的候选集中筛选出最相关的课程。
        if student_profile and len(raw_courses) > 40:
            semantic_filtered = await self._llm_semantic_filter(raw_courses, student_profile)
            if semantic_filtered:
                logger.info(
                    "course_supervisor.semantic_filter_complete",
                    request_id=request_id,
                    before=len(raw_courses),
                    after=len(semantic_filtered),
                )
                raw_courses = semantic_filtered
            else:
                logger.info(
                    "course_supervisor.semantic_filter_skipped",
                    request_id=request_id,
                    reason="llm_failed_or_empty",
                )

        # Phase 2: 课程重排与选课可行性检查并行。
        rerank_result, feasibility_result = await asyncio.gather(
            self.course_rerank_agent.run(
                student_profile=student_profile,
                candidates=raw_courses,
                num_items=request.num_items,
            ),
            self.course_feasibility_agent.run(
                student_profile=student_profile,
                courses=raw_courses,
                context=request.context,
            ),
        )

        ranked_courses: list[Course] = getattr(rerank_result, "courses", raw_courses)
        allowed_course_ids = {course.course_id for course in raw_courses}
        ranked_courses = [course for course in ranked_courses if course.course_id in allowed_course_ids]
        available_ids = set(getattr(feasibility_result, "available_courses", []))
        final_courses = [course for course in ranked_courses if course.course_id in available_ids]
        final_courses = final_courses[: request.num_items]
        warnings.extend(getattr(feasibility_result, "selection_warnings", []))
        if len(final_courses) < request.num_items:
            warnings.append(
                self._build_shortage_warning(
                    requested_count=request.num_items,
                    final_count=len(final_courses),
                    ranked_count=len(ranked_courses),
                    available_count=len(available_ids),
                    candidate_count=len(raw_courses),
                )
            )
        logger.info(
            "course_supervisor.phase2_complete",
            request_id=request_id,
            ranked_count=len(ranked_courses),
            feasibility_count=len(available_ids),
            warning_count=len(warnings),
            final_count=len(final_courses),
            final_course_summary=self._course_axis_summary(final_courses),
        )

        # Phase 3: 面向学生生成推荐理由和选课提醒。
        reason_result = await self.recommendation_reason_agent.run(
            student_profile=student_profile,
            courses=final_courses,
            warnings=warnings,
        )
        reasons = getattr(reason_result, "reasons", [])
        logger.info(
            "course_supervisor.phase3_complete",
            request_id=request_id,
            reason_count=len(reasons),
        )

        total_latency = (time.perf_counter() - start) * 1000
        logger.info(
            "course_supervisor.complete",
            request_id=request_id,
            total_latency_ms=round(total_latency, 1),
            course_count=len(final_courses),
            warning_count=len(warnings),
        )
        logger.info(
            "course_supervisor.response",
            request_id=request_id,
            courses=[{"id": c.course_id, "name": c.course_name, "score": c.score} for c in final_courses],
            reasons=[{"course_id": r.get("course_id"), "reason": r.get("reason", "")[:60]} for r in reasons],
        )

        priority_advice = getattr(feasibility_result, "priority_advice", {})

        # Record metrics for Pipeline path (non-streaming)
        group_name = experiment.get("group", "pipeline")
        self.ab_engine.record_outcome("react_vs_pipeline", group_name, success=True)
        self.ab_engine.record_metric("react_vs_pipeline", group_name, "total_latency_ms", total_latency, request.user_id)
        self.ab_engine.record_metric("react_vs_pipeline", group_name, "course_count", len(final_courses), request.user_id)
        self.ab_engine.record_metric("react_vs_pipeline", group_name, "warning_count", len(warnings), request.user_id)

        return RecommendationResponse(
            request_id=request_id,
            user_id=request.user_id,
            courses=final_courses,
            recommendation_reasons=reasons,
            selection_warnings=warnings,
            priority_advice=priority_advice,
            experiment_group=experiment.get("group", "control"),
            agent_results={
                "student_profile": profile_result,
                "course_recall": recall_result,
                "course_rerank": rerank_result,
                "course_feasibility": feasibility_result,
                "recommendation_reason": reason_result,
            },
            total_latency_ms=total_latency,
        )

    async def stream_recommend(
        self, request: RecommendationRequest
    ) -> "AsyncGenerator[dict[str, Any], None]":
        settings = get_settings()
        request_id = str(uuid.uuid4())
        start = time.perf_counter()
        prompt = self._request_prompt(request)
        current_phase = "start"
        collected_text: dict[str, str] = {}
        agent_results: dict[str, Any] = {}

        yield {
            "event": "phase",
            "data": {
                "phase": "start",
                "request_id": request_id,
                "num_items": request.num_items,
            },
        }

        try:
            experiment = self.ab_engine.assign(request.user_id, "react_vs_pipeline")

            # Phase 1: 画像 + 宽召回并行
            current_phase = "phase1"
            profile_result, recall_result = await asyncio.gather(
                self.student_profile_agent.run(
                    user_id=request.user_id,
                    prompt=prompt,
                    context=request.context,
                ),
                self.course_recall_agent.run(
                    student_profile=None,
                    prompt=prompt,
                    context=request.context,
                    num_items=request.num_items * 2,
                ),
            )

            student_profile: StudentProfile | None = getattr(profile_result, "profile", None)
            raw_courses: list[Course] = getattr(recall_result, "courses", [])
            if not isinstance(getattr(recall_result, "data", None), dict):
                recall_result.data = {}
            agent_results["student_profile"] = profile_result
            agent_results["course_recall"] = recall_result

            yield {
                "event": "phase",
                "data": {
                    "phase": "phase1_complete",
                    "profile_extracted": student_profile is not None,
                    "wide_recall_count": len(raw_courses),
                },
            }

            if student_profile:
                refined_result = await self.course_recall_agent.run(
                    student_profile=student_profile,
                    prompt=prompt,
                    context=request.context,
                    num_items=request.num_items * 2,
                )
                raw_courses = self._merge_courses(
                    raw_courses,
                    getattr(refined_result, "courses", []),
                )
                recall_result.data["wide_recall_strategies"] = getattr(recall_result, "recall_strategies", [])
                recall_result.data["refined_recall_strategies"] = getattr(refined_result, "recall_strategies", [])
                recall_result.data["refined_candidate_count"] = len(raw_courses)
                agent_results["course_recall"] = recall_result
                logger.info(
                    "course_supervisor.refined_recall_complete",
                    request_id=request_id,
                    refined_count=len(getattr(refined_result, "courses", [])),
                    merged_candidate_count=len(raw_courses),
                    refined_strategies=getattr(refined_result, "recall_strategies", []),
                )

            # Phase 1.5: 硬约束确定性过滤 — 违反硬约束的课程不进入重排。
            warnings: list[dict[str, Any]] = []
            if student_profile and has_active_constraints(student_profile.hard_constraints):
                pre_filter_summary = self._course_axis_summary(raw_courses)
                raw_courses, hc_filtered, hc_warnings = self.hard_constraint_filter.filter(
                    raw_courses, student_profile.hard_constraints
                )
                warnings.extend(hc_warnings)
                logger.info(
                    "course_supervisor.phase15_complete",
                    request_id=request_id,
                    hard_filtered_count=len(hc_filtered),
                    remaining_after_filter=len(raw_courses),
                    hard_constraints=self._hard_constraint_snapshot(student_profile),
                    before_filter_summary=pre_filter_summary,
                    after_filter_summary=self._course_axis_summary(raw_courses),
                )
                yield {
                    "event": "phase",
                    "data": {
                        "phase": "phase15_complete",
                        "hard_filtered_count": len(hc_filtered),
                        "remaining_after_filter": len(raw_courses),
                    },
                }

            # Phase 1.75: LLM 语义初筛
            if student_profile and len(raw_courses) > 40:
                semantic_filtered = await self._llm_semantic_filter(raw_courses, student_profile)
                if semantic_filtered:
                    raw_courses = semantic_filtered
                    yield {
                        "event": "phase",
                        "data": {
                            "phase": "semantic_filter_complete",
                            "filtered_count": len(raw_courses),
                        },
                    }
                else:
                    yield {
                        "event": "phase",
                        "data": {"phase": "semantic_filter_skipped"},
                    }

            # Phase 2: 重排 + 可行性并行
            current_phase = "phase2"
            rerank_result, feasibility_result = await asyncio.gather(
                self.course_rerank_agent.run(
                    student_profile=student_profile,
                    candidates=raw_courses,
                    num_items=request.num_items,
                ),
                self.course_feasibility_agent.run(
                    student_profile=student_profile,
                    courses=raw_courses,
                    context=request.context,
                ),
            )

            ranked_courses: list[Course] = getattr(rerank_result, "courses", raw_courses)
            allowed_course_ids = {course.course_id for course in raw_courses}
            ranked_courses = [course for course in ranked_courses if course.course_id in allowed_course_ids]
            available_ids = set(getattr(feasibility_result, "available_courses", []))
            final_courses = [course for course in ranked_courses if course.course_id in available_ids]
            final_courses = final_courses[: request.num_items]
            warnings.extend(getattr(feasibility_result, "selection_warnings", []))
            if len(final_courses) < request.num_items:
                warnings.append(
                    self._build_shortage_warning(
                        requested_count=request.num_items,
                        final_count=len(final_courses),
                        ranked_count=len(ranked_courses),
                        available_count=len(available_ids),
                        candidate_count=len(raw_courses),
                    )
                )
            agent_results["course_rerank"] = rerank_result
            agent_results["course_feasibility"] = feasibility_result

            yield {
                "event": "phase",
                "data": {
                    "phase": "phase2_complete",
                    "ranked_count": len(ranked_courses),
                    "available_count": len(available_ids),
                    "warning_count": len(warnings),
                    "final_count": len(final_courses),
                },
            }

            # Phase 3: 流式推荐理由（超时仅约束本阶段 token 流，避免前几阶段已耗尽的秒数误判超时）
            current_phase = "phase3"
            yield {"event": "phase", "data": {"phase": "phase3_start"}}
            phase3_stream_start = time.perf_counter()

            async for chunk in self.recommendation_reason_agent.astream_reasons(
                profile=student_profile,
                courses=final_courses,
                warnings=warnings,
            ):
                elapsed = time.perf_counter() - phase3_stream_start
                if elapsed > settings.stream_timeout_seconds:
                    yield {
                        "event": "error",
                        "data": {
                            "code": "STREAM_TIMEOUT",
                            "message": f"流式超时 ({settings.stream_timeout_seconds:.0f}s)",
                            "phase": current_phase,
                            "agent": "recommendation_reason",
                            "request_id": request_id,
                        },
                    }
                    return

                if chunk["type"] == "text":
                    course_id = chunk.get("course_id") or "__prelude__"
                    collected_text[course_id] = (
                        collected_text.get(course_id, "") + chunk["token"]
                    )
                yield {"event": chunk["type"], "data": chunk}

            yield {"event": "phase", "data": {"phase": "phase3_complete"}}

            total_latency = (time.perf_counter() - start) * 1000
            logger.info(
                "course_supervisor.response",
                request_id=request_id,
                courses=[{"id": c.course_id, "name": c.course_name, "score": c.score} for c in final_courses],
                reasons=[{"course_id": cid, "reason": text[:60]} for cid, text in collected_text.items() if cid != "__prelude__"],
            )
            feasibility = agent_results.get("course_feasibility")
            priority_advice = getattr(feasibility, "priority_advice", {}) if feasibility else {}
            yield {
                "event": "done",
                "data": {
                    "request_id": request_id,
                    "user_id": request.user_id,
                    "courses": [course.model_dump() for course in final_courses],
                    "recommendation_reasons": [
                        {"course_id": cid, "reason": text}
                        for cid, text in collected_text.items()
                        if cid != "__prelude__"
                    ],
                    "selection_warnings": warnings,
                    "priority_advice": {cid: pa.model_dump() for cid, pa in priority_advice.items()},
                    "experiment_group": experiment.get("group", "control"),
                    "agent_results": {
                        name: result.model_dump()
                        for name, result in agent_results.items()
                    },
                    "total_latency_ms": round(total_latency, 1),
                },
            }

            group_name = experiment.get("group", "pipeline")
            self.ab_engine.record_outcome("react_vs_pipeline", group_name, success=True)
            self.ab_engine.record_metric("react_vs_pipeline", group_name, "total_latency_ms", total_latency, request.user_id)
            self.ab_engine.record_metric("react_vs_pipeline", group_name, "course_count", len(final_courses), request.user_id)
            self.ab_engine.record_metric("react_vs_pipeline", group_name, "warning_count", len(warnings), request.user_id)

        except Exception as exc:
            logger.error(
                "course_supervisor.stream_error",
                request_id=request_id,
                phase=current_phase,
                error=str(exc),
            )
            self.ab_engine.record_outcome("react_vs_pipeline", experiment.get("group", "pipeline"), success=False)
            yield {
                "event": "error",
                "data": {
                    "code": type(exc).__name__.upper(),
                    "message": str(exc),
                    "phase": current_phase,
                    "request_id": request_id,
                },
            }

    @staticmethod
    def _request_prompt(request: RecommendationRequest) -> str:
        return (request.prompt or request.query or request.context.get("query") or "").strip()

    @staticmethod
    def _merge_courses(*course_lists: list[Course]) -> list[Course]:
        seen: set[str] = set()
        merged: list[Course] = []
        for courses in course_lists:
            for course in courses:
                if course.course_id not in seen:
                    seen.add(course.course_id)
                    merged.append(course)
        return merged

    @staticmethod
    def _hard_constraint_snapshot(profile: StudentProfile | None) -> dict[str, Any]:
        if not profile:
            return {}
        hard = profile.hard_constraints
        return {
            "campus": list(hard.campus),
            "categories": list(hard.categories),
            "avoid_time_slots": list(hard.avoid_time_slots),
            "teacher": hard.teacher,
            "no_exam": hard.no_exam,
            "no_group_work": hard.no_group_work,
            "max_difficulty": hard.max_difficulty,
            "max_workload": hard.max_workload,
        }

    @staticmethod
    def _course_axis_summary(courses: list[Course]) -> dict[str, Any]:
        campus_count: dict[str, int] = {}
        category_count: dict[str, int] = {}
        for course in courses:
            campus = course.campus or "unknown"
            campus_count[campus] = campus_count.get(campus, 0) + 1
            category = course.course_category or course.domain or "unknown"
            category_count[category] = category_count.get(category, 0) + 1
        return {
            "count": len(courses),
            "campus_count": campus_count,
            "category_count": category_count,
        }

    @staticmethod
    async def _llm_semantic_filter(
        courses: list[Course], profile: StudentProfile | None, target_count: int = 40
    ) -> list[Course]:
        MAX_SEMANTIC_INPUT = 200
        if len(courses) > MAX_SEMANTIC_INPUT:
            courses = sorted(courses, key=lambda x: x.score, reverse=True)[:MAX_SEMANTIC_INPUT]
        if not courses or not profile:
            return []
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
            f"你是课程语义匹配专家。根据学生画像从候选课程中选出 {target_count} 门真正相关的。"
            "判断标准：课程名称+描述+标签是否真实匹配学生的兴趣和偏好（不是只看 domain 字段）。"
            f"返回 JSON 数组：[\"course_id_1\", \"course_id_2\", ...]"
        )
        user_prompt = json.dumps({
            "student": profile_data,
            "candidates": course_data,
        }, ensure_ascii=False)
        try:
            llm = build_chat_openai(temperature=0, max_tokens=2048, task_name=LLMTaskName.SEMANTIC_FILTER)
            response = await llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
            raw = (response.content or "").strip()
            if not raw:
                logger.info("course_supervisor.semantic_filter_empty_response")
                return []
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            ids = json.loads(raw)
            if isinstance(ids, list) and ids:
                id_set = {str(i) for i in ids}
                filtered = [c for c in courses if c.course_id in id_set]
                if filtered:
                    return filtered[:target_count]
        except Exception:
            logger.warning("course_supervisor.semantic_filter_failed", exc_info=True)
        return []

    async def react_recommend(self, request: RecommendationRequest) -> RecommendationResponse:
        """Public entry point for React-mode recommendation (non-streaming)."""
        request_id = str(uuid.uuid4())
        start = time.perf_counter()
        return await self._react_recommend(request, request_id, start)

    async def react_stream_recommend(
        self, request: RecommendationRequest
    ) -> "AsyncGenerator[dict[str, Any], None]":
        """SSE streaming React-mode recommendation with tool-call phase events."""
        from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
        from agent.recommend.react_tools import REACT_TOOLS, ReactToolExecutor
        from ai import build_tool_calling_llm

        settings = get_settings()
        request_id = str(uuid.uuid4())
        start = time.perf_counter()
        prompt = self._request_prompt(request)

        REACT_SYSTEM_PROMPT = (
            "你是公选课推荐系统的编排器。根据学生需求，按顺序调用工具完成推荐。\n"
            "必须遵守的顺序：extract_profile → search_courses → filter_hard_constraints → "
            "semantic_filter_courses → rerank_courses → check_feasibility → generate_reasons。\n"
            "filter_hard_constraints 是强制的，不可跳过。\n"
            "每个工具只调用一次，不要重复搜索或重复重排；候选充足时直接进入重排，不重复召回。\n"
            "extract_profile 与 search_courses(wide) 可同一轮并行；rerank_courses 与 check_feasibility 也可同一轮并行（互相独立）。\n"
            "如果召回太少（<5门），再尝试一次不同策略的搜索。\n"
            "当所有必需工具调用完成后，输出 FINISH。"
        )

        llm = build_tool_calling_llm(REACT_TOOLS, task_name=LLMTaskName.REACT_ORCHESTRATOR)
        executor = ReactToolExecutor(self, prompt, request.context, request.num_items, request.user_id)

        messages = [
            SystemMessage(content=REACT_SYSTEM_PROMPT),
            HumanMessage(content=f"学生需求: {prompt}\n需要推荐 {request.num_items} 门课。"),
        ]

        yield {
            "event": "phase",
            "data": {
                "phase": "react_start",
                "request_id": request_id,
                "num_items": request.num_items,
            },
        }

        try:
            max_rounds = 10
            round_idx = 0
            for round_idx in range(max_rounds):
                response = await llm.ainvoke(messages)
                messages.append(response)

                tool_calls = getattr(response, "tool_calls", None)
                if not tool_calls:
                    content = str(getattr(response, "content", ""))
                    if "FINISH" in content.upper():
                        break
                    # 空转即终止：工具型 agent 每轮应调工具，不继续白耗一轮
                    break

                # 一轮内并行 + 顺序回填：A 组（extract_profile ∥ search_courses）写不同
                # state 字段可安全并行；其余工具串行。ToolMessage 必须按 tool_calls
                # 原始顺序回填，否则违反 OpenAI "tool 消息须跟在 tool_calls 之后"约束。
                def _is_parallel_group(names: list[str]) -> bool:
                    return "extract_profile" in names and any(
                        n == "search_courses" for n in names
                    )

                tc_names = [t.get("name", "") for t in tool_calls]
                if _is_parallel_group(tc_names) and len(tool_calls) == len(
                    [n for n in tc_names if n in ("extract_profile", "search_courses")]
                ):
                    # 本轮全部是可并行工具：gather 执行，按原序回填
                    for t in tool_calls:
                        yield {
                            "event": "phase",
                            "data": {"phase": f"react_{t.get('name', '')}"},
                        }
                    results = await asyncio.gather(
                        *[
                            executor.execute_tool(t.get("name", ""), t.get("args", {}))
                            for t in tool_calls
                        ]
                    )
                    for t, r in zip(tool_calls, results):
                        messages.append(
                            ToolMessage(content=r, tool_call_id=t.get("id", ""))
                        )
                    continue

                # B 组并行：rerank_courses ∥ check_feasibility（读同一快照，互不依赖）
                if (
                    "rerank_courses" in tc_names
                    and "check_feasibility" in tc_names
                    and len(tool_calls) == len(
                        [n for n in tc_names if n in ("rerank_courses", "check_feasibility")]
                    )
                    and executor.state.courses
                ):
                    for t in tool_calls:
                        yield {
                            "event": "phase",
                            "data": {"phase": f"react_{t.get('name', '')}"},
                        }
                    snapshot = list(executor.state.courses)
                    rerank_args = next(
                        (t.get("args", {}) for t in tool_calls if t.get("name") == "rerank_courses"),
                        {},
                    )
                    num_items = rerank_args.get("num_items", 10)
                    rerank_result, feas_result = await asyncio.gather(
                        executor.execute_rerank_on_snapshot(snapshot, num_items=num_items),
                        executor.execute_feasibility_on_snapshot(snapshot),
                    )
                    # 合并（对齐 Pipeline Phase2 语义）：
                    # ranked 排序 → 仅保留 available → 记录 warnings/priority_advice
                    ranked_ids = rerank_result["course_ids"]
                    available_ids = set(feas_result["available_ids"])
                    id_to_course = {c.course_id: c for c in snapshot}
                    executor.state.warnings.extend(feas_result["warnings"])
                    executor.state.priority_advice.update(feas_result["priority_advice"])
                    final = [id_to_course[cid] for cid in ranked_ids if cid in available_ids]
                    executor.state.courses = final
                    executor.state.rerank_done = True
                    executor.state.feasibility_done = True
                    for t in tool_calls:
                        name = t.get("name", "")
                        if name == "rerank_courses":
                            text = (
                                f"Reranked {len(ranked_ids)} courses. "
                                f"Top: {[id_to_course[cid].course_name for cid in ranked_ids[:5] if cid in id_to_course]}"
                            )
                        else:
                            text = (
                                f"Feasibility check: {len(available_ids)} available, "
                                f"{len(final)} after filtering, "
                                f"{len(feas_result['warnings'])} warnings."
                            )
                        messages.append(ToolMessage(content=text, tool_call_id=t.get("id", "")))
                    continue

                for tc in tool_calls:
                    tool_name = tc.get("name", "")
                    tool_args = tc.get("args", {})
                    yield {
                        "event": "phase",
                        "data": {"phase": f"react_{tool_name}"},
                    }
                    observation = await executor.execute_tool(tool_name, tool_args)
                    messages.append(ToolMessage(content=observation, tool_call_id=tc.get("id", "")))

            # Post-loop safety nets
            if executor.state.courses and not executor.state.hard_filtered and executor.state.profile:
                yield {"event": "phase", "data": {"phase": "react_filter_hard_constraints"}}
                await executor._tool_filter_hard_constraints()

            if executor.state.courses and not executor.state.feasibility_done:
                yield {"event": "phase", "data": {"phase": "react_check_feasibility"}}
                await executor._tool_check_feasibility()

            if executor.state.courses:
                yield {"event": "phase", "data": {"phase": "react_generate_reasons"}}
                collected_text: dict[str, str] = {}
                stream_start = time.perf_counter()
                async for chunk in self.recommendation_reason_agent.astream_reasons(
                    profile=executor.state.profile,
                    courses=executor.state.courses[: request.num_items],
                    warnings=executor.state.warnings,
                ):
                    elapsed = time.perf_counter() - stream_start
                    if elapsed > settings.stream_timeout_seconds:
                        yield {
                            "event": "error",
                            "data": {
                                "code": "STREAM_TIMEOUT",
                                "message": f"流式超时 ({settings.stream_timeout_seconds:.0f}s)",
                                "phase": "react_generate_reasons",
                                "agent": "recommendation_reason",
                                "request_id": request_id,
                            },
                        }
                        break

                    if chunk["type"] == "text":
                        cid = chunk.get("course_id") or "__prelude__"
                        collected_text[cid] = collected_text.get(cid, "") + chunk["token"]
                    yield {"event": chunk["type"], "data": chunk}

                executor.state.reasons = [
                    {"course_id": cid, "reason": text}
                    for cid, text in collected_text.items()
                    if cid != "__prelude__"
                ]
                executor.state.reasons_done = True

            final_courses = executor.state.courses[: request.num_items]
            total_latency = (time.perf_counter() - start) * 1000

            logger.info(
                "course_supervisor.react_stream_complete",
                request_id=request_id,
                course_count=len(final_courses),
                rounds=round_idx + 1,
                total_latency_ms=round(total_latency, 1),
            )

            yield {
                "event": "done",
                "data": {
                    "request_id": request_id,
                    "user_id": request.user_id,
                    "courses": [c.model_dump() for c in final_courses],
                    "recommendation_reasons": executor.state.reasons,
                    "selection_warnings": executor.state.warnings,
                    "priority_advice": {
                        cid: pa.model_dump() if hasattr(pa, 'model_dump') else pa
                        for cid, pa in executor.state.priority_advice.items()
                    },
                    "experiment_group": "react",
                    "agent_results": {
                        "react_orchestrator": {
                            "agent_name": "react_orchestrator",
                            "success": True,
                            "latency_ms": round(total_latency, 1),
                            "error": None,
                            "data": {"rounds": round_idx + 1, "course_count": len(final_courses)},
                            "confidence": 1.0,
                        }
                    },
                    "total_latency_ms": round(total_latency, 1),
                },
            }

            self.ab_engine.record_outcome("react_vs_pipeline", "react", success=True)
            self.ab_engine.record_metric("react_vs_pipeline", "react", "total_latency_ms", total_latency, request.user_id)
            self.ab_engine.record_metric("react_vs_pipeline", "react", "course_count", len(final_courses), request.user_id)
            self.ab_engine.record_metric("react_vs_pipeline", "react", "warning_count", len(executor.state.warnings), request.user_id)

        except Exception as exc:
            logger.error(
                "course_supervisor.react_stream_error",
                request_id=request_id,
                error=str(exc),
            )
            self.ab_engine.record_outcome("react_vs_pipeline", "react", success=False)
            yield {
                "event": "error",
                "data": {
                    "code": type(exc).__name__.upper(),
                    "message": str(exc),
                    "phase": "react",
                    "request_id": request_id,
                },
            }

    async def stream_recommend_unified(
        self,
        request: RecommendationRequest,
        *,
        mode: str = "pipeline",
    ) -> "AsyncGenerator[dict[str, Any], None]":
        """统一流式推荐入口。

        默认走并行 Pipeline（student_profile∥course_recall 并行、rerank∥feasibility 并行），
        外部 LLM 调用数少、延迟低。mode="react" 时走 ReAct（多轮决策 LLM，较慢），
        失败自动兜底 Pipeline。
        """
        request_id = str(uuid.uuid4())
        logger.info(
            "course_supervisor.unified_stream.start",
            request_id=request_id,
            user_id=request.user_id,
            mode=mode,
        )

        if mode == "pipeline":
            async for event in self.stream_recommend(request):
                yield event
            return

        react_failed: Exception | None = None
        try:
            async for event in self.react_stream_recommend(request):
                if event["event"] == "error":
                    react_failed = RuntimeError(
                        f"react stream failed: {event['data'].get('message', 'unknown')}"
                    )
                    break
                yield event
        except Exception as exc:
            react_failed = exc
            logger.warning(
                "course_supervisor.unified_stream.react_error",
                request_id=request_id,
                error=str(exc),
            )

        if react_failed is None:
            return

        # 兜底：切到 Pipeline 流式
        logger.info(
            "course_supervisor.unified_stream.fallback_pipeline",
            request_id=request_id,
            reason=str(react_failed),
        )
        yield {
            "event": "phase",
            "data": {
                "phase": "react_fallback",
                "reason": type(react_failed).__name__,
                "request_id": request_id,
            },
        }

        async for event in self.stream_recommend(request):
            if event["event"] == "done":
                event["data"]["experiment_group"] = "pipeline_fallback"
                event["data"]["react_fallback"] = {
                    "error": type(react_failed).__name__,
                    "message": str(react_failed),
                }
            yield event

    async def _react_recommend(
        self, request: RecommendationRequest, request_id: str, start: float
    ) -> RecommendationResponse:
        from agent.recommend.react_tools import REACT_TOOLS, ReactToolExecutor
        from ai import build_tool_calling_llm

        prompt = self._request_prompt(request)

        REACT_SYSTEM_PROMPT = (
            "你是公选课推荐系统的编排器。根据学生需求，按顺序调用工具完成推荐。\n"
            "必须遵守的顺序：extract_profile → search_courses → filter_hard_constraints → "
            "semantic_filter_courses → rerank_courses → check_feasibility → generate_reasons。\n"
            "filter_hard_constraints 是强制的，不可跳过。\n"
            "每个工具只调用一次，不要重复搜索或重复重排；候选充足时直接进入重排，不重复召回。\n"
            "extract_profile 与 search_courses(wide) 可同一轮并行；rerank_courses 与 check_feasibility 也可同一轮并行（互相独立）。\n"
            "如果召回太少（<5门），再尝试一次不同策略的搜索。\n"
            "当所有必需工具调用完成后，输出 FINISH。"
        )

        llm = build_tool_calling_llm(REACT_TOOLS, task_name=LLMTaskName.REACT_ORCHESTRATOR)
        executor = ReactToolExecutor(self, prompt, request.context, request.num_items, request.user_id)

        messages = [
            SystemMessage(content=REACT_SYSTEM_PROMPT),
            HumanMessage(content=f"学生需求: {prompt}\n需要推荐 {request.num_items} 门课。"),
        ]

        max_rounds = 10
        for round_idx in range(max_rounds):
            response = await llm.ainvoke(messages)
            messages.append(response)

            tool_calls = getattr(response, "tool_calls", None)
            if not tool_calls:
                content = str(getattr(response, "content", ""))
                if "FINISH" in content.upper():
                    break
                # 空转即终止：工具型 agent 每轮应调工具，不继续白耗一轮
                break

            # 一轮内并行 + 顺序回填：A 组（extract_profile ∥ search_courses）写不同
            # state 字段可安全并行；其余工具串行。ToolMessage 必须按 tool_calls
            # 原始顺序回填，否则违反 OpenAI "tool 消息须跟在 tool_calls 之后"约束。
            def _is_parallel_group(names: list[str]) -> bool:
                return "extract_profile" in names and any(
                    n == "search_courses" for n in names
                )

            tc_names = [t.get("name", "") for t in tool_calls]
            if _is_parallel_group(tc_names) and len(tool_calls) == len(
                [n for n in tc_names if n in ("extract_profile", "search_courses")]
            ):
                results = await asyncio.gather(
                    *[
                        executor.execute_tool(t.get("name", ""), t.get("args", {}))
                        for t in tool_calls
                    ]
                )
                for t, r in zip(tool_calls, results):
                    messages.append(
                        ToolMessage(content=r, tool_call_id=t.get("id", ""))
                    )
                continue

            # B 组并行：rerank_courses ∥ check_feasibility（读同一快照，互不依赖）
            if (
                "rerank_courses" in tc_names
                and "check_feasibility" in tc_names
                and len(tool_calls) == len(
                    [n for n in tc_names if n in ("rerank_courses", "check_feasibility")]
                )
                and executor.state.courses
            ):
                logger.info(
                    "course_supervisor.react_b_group_parallel",
                    request_id=request_id,
                    candidate_count=len(executor.state.courses),
                    round=round_idx + 1,
                )
                snapshot = list(executor.state.courses)
                rerank_args = next(
                    (t.get("args", {}) for t in tool_calls if t.get("name") == "rerank_courses"),
                    {},
                )
                num_items = rerank_args.get("num_items", 10)
                rerank_result, feas_result = await asyncio.gather(
                    executor.execute_rerank_on_snapshot(snapshot, num_items=num_items),
                    executor.execute_feasibility_on_snapshot(snapshot),
                )
                ranked_ids = rerank_result["course_ids"]
                available_ids = set(feas_result["available_ids"])
                id_to_course = {c.course_id: c for c in snapshot}
                executor.state.warnings.extend(feas_result["warnings"])
                executor.state.priority_advice.update(feas_result["priority_advice"])
                final = [id_to_course[cid] for cid in ranked_ids if cid in available_ids]
                executor.state.courses = final
                executor.state.rerank_done = True
                executor.state.feasibility_done = True
                for t in tool_calls:
                    name = t.get("name", "")
                    if name == "rerank_courses":
                        text = (
                            f"Reranked {len(ranked_ids)} courses. "
                            f"Top: {[id_to_course[cid].course_name for cid in ranked_ids[:5] if cid in id_to_course]}"
                        )
                    else:
                        text = (
                            f"Feasibility check: {len(available_ids)} available, "
                            f"{len(final)} after filtering, "
                            f"{len(feas_result['warnings'])} warnings."
                        )
                    messages.append(ToolMessage(content=text, tool_call_id=t.get("id", "")))
                continue

            for tc in tool_calls:
                tool_name = tc.get("name", "")
                tool_args = tc.get("args", {})
                observation = await executor.execute_tool(tool_name, tool_args)
                messages.append(ToolMessage(content=observation, tool_call_id=tc.get("id", "")))

        # Enforce hard constraint filter if LLM skipped it
        if executor.state.courses and not executor.state.hard_filtered and executor.state.profile:
            await executor._tool_filter_hard_constraints()

        if not executor.state.reasons_done and executor.state.courses:
            await executor._tool_generate_reasons()

        final_courses = executor.state.courses[: request.num_items]
        total_latency = (time.perf_counter() - start) * 1000

        logger.info(
            "course_supervisor.react_complete",
            request_id=request_id,
            course_count=len(final_courses),
            rounds=round_idx + 1,
        )

        return RecommendationResponse(
            request_id=request_id,
            user_id=request.user_id,
            courses=final_courses,
            recommendation_reasons=executor.state.reasons,
            selection_warnings=executor.state.warnings,
            priority_advice=executor.state.priority_advice,
            experiment_group="react",
            total_latency_ms=total_latency,
        )

    @staticmethod
    def _build_shortage_warning(
        requested_count: int,
        final_count: int,
        ranked_count: int,
        available_count: int,
        candidate_count: int,
    ) -> dict[str, Any]:
        if candidate_count < requested_count:
            cause = "candidate_insufficient"
            message = "召回候选数量不足，建议放宽筛选条件或调整需求描述。"
        elif available_count < requested_count:
            cause = "feasibility_filter_insufficient"
            message = "可行性过滤后课程不足，建议放宽硬约束或准备替代课程。"
        else:
            cause = "rerank_output_insufficient"
            message = "排序后可返回课程不足，建议补充偏好或减少请求数量。"
        logger.warning(
            "course_supervisor.shortage_warning",
            requested_count=requested_count,
            final_count=final_count,
            ranked_count=ranked_count,
            available_count=available_count,
            candidate_count=candidate_count,
            cause=cause,
            message=message,
        )
        return {
            "type": "requested_count_shortage",
            "level": "medium",
            "cause": cause,
            "requested_count": requested_count,
            "final_count": final_count,
            "ranked_count": ranked_count,
            "available_count": available_count,
            "candidate_count": candidate_count,
            "message": message,
        }
