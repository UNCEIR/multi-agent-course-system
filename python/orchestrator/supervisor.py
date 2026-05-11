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

import structlog

from agents import (
    CourseFeasibilityAgent,
    CourseRecallAgent,
    CourseRerankAgent,
    RecommendationReasonAgent,
    StudentProfileAgent,
)
from models.schemas import Course, RecommendationRequest, RecommendationResponse, StudentProfile
from services.ab_test import ABTestEngine

logger = structlog.get_logger()


class SupervisorOrchestrator:
    """Coordinates public elective course agents in a parallel-then-aggregate pattern."""

    def __init__(self, ab_engine: ABTestEngine | None = None):
        self.student_profile_agent = StudentProfileAgent()
        self.course_recall_agent = CourseRecallAgent()
        self.course_rerank_agent = CourseRerankAgent()
        self.course_feasibility_agent = CourseFeasibilityAgent()
        self.recommendation_reason_agent = RecommendationReasonAgent()
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
            prompt=prompt[:80],
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

        # Phase 3: 面向学生生成推荐理由和选课提醒。
        reason_result = await self.recommendation_reason_agent.run(
            student_profile=student_profile,
            courses=final_courses,
            warnings=warnings,
        )
        reasons = getattr(reason_result, "reasons", [])

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
