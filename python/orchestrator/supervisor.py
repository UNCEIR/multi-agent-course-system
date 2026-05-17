"""
公选课推荐 Supervisor 编排器

用户输入自然语言选课需求后，Supervisor 负责并行调度专业 Agent：

Phase 1: 学生画像 Agent 与课程召回 Agent 并行
Phase 2: 课程重排 Agent 与选课可行性 Agent 并行
Phase 3: 推荐理由 Agent 串行生成可解释建议
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, TYPE_CHECKING

import structlog

from models.schemas import Course, RecommendationRequest, RecommendationResponse, StudentProfile
from services.ab_test import ABTestEngine
from config import get_settings

logger = structlog.get_logger()

if TYPE_CHECKING:
    from agents import (
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
            from agents import StudentProfileAgent

            student_profile_agent = StudentProfileAgent()
        if course_recall_agent is None:
            from agents import CourseRecallAgent

            course_recall_agent = CourseRecallAgent()
        if course_rerank_agent is None:
            from agents import CourseRerankAgent

            course_rerank_agent = CourseRerankAgent()
        if course_feasibility_agent is None:
            from agents import CourseFeasibilityAgent

            course_feasibility_agent = CourseFeasibilityAgent()
        if recommendation_reason_agent is None:
            from agents import RecommendationReasonAgent

            recommendation_reason_agent = RecommendationReasonAgent()

        self.student_profile_agent = student_profile_agent
        self.course_recall_agent = course_recall_agent
        self.course_rerank_agent = course_rerank_agent
        self.course_feasibility_agent = course_feasibility_agent
        self.recommendation_reason_agent = recommendation_reason_agent
        self.ab_engine = ab_engine or ABTestEngine()

    async def recommend(self, request: RecommendationRequest) -> RecommendationResponse:
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
        )

        experiment = self.ab_engine.assign(request.user_id)

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
        logger.info(
            "course_supervisor.phase1_complete",
            request_id=request_id,
            profile_extracted=student_profile is not None,
            wide_recall_count=len(raw_courses),
            recall_success=getattr(recall_result, "success", False),
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
            recall_result.data["refined_candidate_count"] = len(raw_courses)
            logger.info(
                "course_supervisor.refined_recall_complete",
                request_id=request_id,
                refined_count=len(getattr(refined_result, "courses", [])),
                merged_candidate_count=len(raw_courses),
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
        available_ids = set(getattr(feasibility_result, "available_courses", []))
        final_courses = [course for course in ranked_courses if course.course_id in available_ids]
        final_courses = final_courses[: request.num_items]
        warnings = getattr(feasibility_result, "selection_warnings", [])
        logger.info(
            "course_supervisor.phase2_complete",
            request_id=request_id,
            ranked_count=len(ranked_courses),
            feasibility_count=len(available_ids),
            warning_count=len(warnings),
            final_count=len(final_courses),
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

        return RecommendationResponse(
            request_id=request_id,
            user_id=request.user_id,
            courses=final_courses,
            recommendation_reasons=reasons,
            selection_warnings=warnings,
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
            experiment = self.ab_engine.assign(request.user_id)

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
                agent_results["course_recall"] = recall_result
                logger.info(
                    "course_supervisor.refined_recall_complete",
                    request_id=request_id,
                    refined_count=len(getattr(refined_result, "courses", [])),
                    merged_candidate_count=len(raw_courses),
                )

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
            available_ids = set(getattr(feasibility_result, "available_courses", []))
            final_courses = [course for course in ranked_courses if course.course_id in available_ids]
            final_courses = final_courses[: request.num_items]
            warnings = getattr(feasibility_result, "selection_warnings", [])
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

            # Phase 3: 流式推荐理由
            current_phase = "phase3"
            yield {"event": "phase", "data": {"phase": "phase3_start"}}

            async for chunk in self.recommendation_reason_agent.astream_reasons(
                student_profile=student_profile,
                courses=final_courses,
                warnings=warnings,
            ):
                elapsed = time.perf_counter() - start
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
                    "experiment_group": experiment.get("group", "control"),
                    "agent_results": {
                        name: result.model_dump()
                        for name, result in agent_results.items()
                    },
                    "total_latency_ms": round(total_latency, 1),
                },
            }

        except Exception as exc:
            logger.error(
                "course_supervisor.stream_error",
                request_id=request_id,
                phase=current_phase,
                error=str(exc),
            )
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
