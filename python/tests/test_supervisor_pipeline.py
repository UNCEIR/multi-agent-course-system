from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from models.schemas import (
    Course,
    CourseFeasibilityResult,
    CourseRecallResult,
    CourseRerankResult,
    RecommendationReasonResult,
    RecommendationRequest,
    StudentProfile,
    StudentProfileResult,
)
from orchestrator.supervisor import SupervisorOrchestrator


@pytest.mark.agent
@pytest.mark.asyncio
async def test_supervisor_filters_time_conflict_and_returns_course_reasons():
    orchestrator = SupervisorOrchestrator()
    req = RecommendationRequest(
        user_id="S10001",
        num_items=2,
        prompt="想选不考试、作业少、给分友好的艺术类公选课，避开周三晚上",
        context={"avoid_time_slots": ["周三第9-10节"]},
    )

    profile = StudentProfile(
        student_id="S10001",
        raw_prompt=req.prompt,
        preferred_domains=["人文艺术"],
        avoid_time_slots=["周三第9-10节"],
        exam_preference="不考试",
        workload_preference="少",
        grade_friendly_preference="高",
    )
    profile_result = StudentProfileResult(success=True, profile=profile)

    c1 = Course(
        course_id="GXK001",
        course_name="电影艺术赏析",
        domain="人文艺术",
        campus="东校区",
        time_slot="周二第5-6节",
        capacity=120,
        current_enrolled=80,
        has_exam="否",
        workload="低",
        grade_friendly="高",
    )
    c2 = Course(
        course_id="GXK002",
        course_name="现代音乐导论",
        domain="人文艺术",
        campus="东校区",
        time_slot="周三第9-10节",
        capacity=100,
        current_enrolled=60,
        has_exam="否",
        workload="低",
        grade_friendly="高",
    )
    recall_result = CourseRecallResult(success=True, courses=[c1, c2], recall_strategies=["mysql_structured"])
    rerank_result = CourseRerankResult(success=True, courses=[c2, c1], rerank_strategy="llm_course_rerank")
    feasibility_result = CourseFeasibilityResult(
        success=True,
        available_courses=["GXK001"],
        filtered_courses=[{"course_id": "GXK002", "reasons": ["上课时间命中避开时段：周三第9-10节"]}],
        data={"total_checked": 2, "available_count": 1, "filtered_count": 1},
    )
    reason_result = RecommendationReasonResult(
        success=True,
        reasons=[{"course_id": "GXK001", "reason": "匹配不考试、作业少和人文艺术兴趣。"}],
    )

    orchestrator.student_profile_agent.run = AsyncMock(return_value=profile_result)
    orchestrator.course_recall_agent.run = AsyncMock(return_value=recall_result)
    orchestrator.course_rerank_agent.run = AsyncMock(return_value=rerank_result)
    orchestrator.course_feasibility_agent.run = AsyncMock(return_value=feasibility_result)
    orchestrator.recommendation_reason_agent.run = AsyncMock(return_value=reason_result)

    response = await orchestrator.recommend(req)

    assert [course.course_id for course in response.courses] == ["GXK001"]
    assert response.recommendation_reasons[0]["course_id"] == "GXK001"
    assert "course_recall" in response.agent_results
    assert response.agent_results["course_feasibility"].data["filtered_count"] == 1
