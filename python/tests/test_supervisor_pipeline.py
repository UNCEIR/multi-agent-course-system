from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from models.schemas import (
    Course,
    CourseFeasibilityResult,
    CourseRecallResult,
    CourseRerankResult,
    HardConstraints,
    RecommendationReasonResult,
    RecommendationRequest,
    StudentProfile,
    StudentProfileResult,
)
from app.recommend.agents.course_recall_agent import CourseRecallAgent
from app.recommend.supervisor import SupervisorOrchestrator


class _AgentStub:
    def __init__(self, result):
        self.run = AsyncMock(return_value=result)


@pytest.mark.agent
@pytest.mark.asyncio
async def test_supervisor_filters_time_conflict_and_returns_course_reasons(monkeypatch):
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
        has_exam=0,
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
        has_exam=0,
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

    orchestrator = SupervisorOrchestrator(
        student_profile_agent=_AgentStub(profile_result),
        course_recall_agent=_AgentStub(recall_result),
        course_rerank_agent=_AgentStub(rerank_result),
        course_feasibility_agent=_AgentStub(feasibility_result),
        recommendation_reason_agent=_AgentStub(reason_result),
    )

    monkeypatch.setattr(
        orchestrator.ab_engine, "assign",
        lambda user_id, experiment_id: {"group": "pipeline", "config": {}},
    )

    response = await orchestrator.recommend(req)

    assert [course.course_id for course in response.courses] == ["GXK001"]
    assert response.recommendation_reasons[0]["course_id"] == "GXK001"
    assert "course_recall" in response.agent_results
    assert response.agent_results["course_feasibility"].data["filtered_count"] == 1
    assert any(w.get("type") == "requested_count_shortage" for w in response.selection_warnings)


@pytest.mark.agent
@pytest.mark.asyncio
async def test_supervisor_pipeline_uses_cached_recall_candidates(monkeypatch):
    req = RecommendationRequest(
        user_id="S10002",
        num_items=2,
        prompt="想选不考试、作业少、给分友好的艺术类公选课，东校区优先",
    )
    profile = StudentProfile(
        student_id="S10002",
        raw_prompt=req.prompt,
        preferred_domains=["人文艺术"],
        preferred_campus=["东校区"],
        exam_preference="不考试",
        workload_preference="少",
        grade_friendly_preference="高",
    )
    cached_course = Course(
        course_id="GXK010",
        course_name="电影艺术赏析",
        domain="人文艺术",
        campus="东校区",
        has_exam=0,
        workload="低",
        grade_friendly="高",
    )

    recall_agent = CourseRecallAgent()

    class _CacheHit:
        async def get_course_ids(self, cache_key: str) -> list[str]:
            return ["GXK010"]

        async def set_course_ids(self, cache_key: str, course_ids: list[str]) -> None:
            raise AssertionError("cache should not be rewritten on hit")

        async def try_acquire_lock(self, cache_key: str) -> bool:
            raise AssertionError("lock should not be acquired on hit")

    recall_agent.recall_cache = _CacheHit()
    recall_agent.course_repo.fetch_courses_by_ids = MagicMock(return_value=[cached_course])
    recall_agent.course_repo.fetch_courses = MagicMock(side_effect=AssertionError("structured recall should be skipped"))
    recall_agent.vector_repo.search = MagicMock(side_effect=AssertionError("vector search should be skipped"))

    rerank_result = CourseRerankResult(success=True, courses=[cached_course], rerank_strategy="cached_candidates")
    feasibility_result = CourseFeasibilityResult(
        success=True,
        available_courses=["GXK010"],
        data={"total_checked": 1, "available_count": 1, "filtered_count": 0},
    )
    reason_result = RecommendationReasonResult(
        success=True,
        reasons=[{"course_id": "GXK010", "reason": "命中缓存候选后回表获取最新课程状态。"}],
    )
    orchestrator = SupervisorOrchestrator(
        student_profile_agent=_AgentStub(StudentProfileResult(success=True, profile=profile)),
        course_recall_agent=recall_agent,
        course_rerank_agent=_AgentStub(rerank_result),
        course_feasibility_agent=_AgentStub(feasibility_result),
        recommendation_reason_agent=_AgentStub(reason_result),
    )

    monkeypatch.setattr(
        orchestrator.ab_engine, "assign",
        lambda user_id, experiment_id: {"group": "pipeline", "config": {}},
    )

    response = await orchestrator.recommend(req)

    assert [course.course_id for course in response.courses] == ["GXK010"]
    assert response.agent_results["course_recall"].recall_strategies == ["redis_recall_cache_hit"]
    recall_agent.course_repo.fetch_courses_by_ids.assert_called()


@pytest.mark.agent
@pytest.mark.asyncio
async def test_supervisor_hard_constraint_filter_blocks_non_west_campus_courses(monkeypatch):
    req = RecommendationRequest(
        user_id="S10003",
        num_items=3,
        prompt="我要去西校区上课，而且我只要上自然科学类的课",
    )
    profile = StudentProfile(
        student_id="S10003",
        raw_prompt=req.prompt,
        preferred_domains=["自然环境"],
        preferred_categories=["自然科学类"],
        preferred_campus=["西校区"],
        hard_constraints=HardConstraints(campus=["西校区"], categories=["自然科学类"]),
    )
    west_course = Course(
        course_id="GXK201",
        course_name="地球系统科学导论",
        campus="西校区",
        course_category="自然科学类",
        domain="自然环境",
        has_exam=0,
    )
    east_course = Course(
        course_id="GXK202",
        course_name="海洋科学与文明",
        campus="东校区",
        course_category="自然科学类",
        domain="自然环境",
        has_exam=0,
    )
    recall_result = CourseRecallResult(
        success=True,
        courses=[east_course, west_course],
        recall_strategies=["mysql_structured"],
    )
    rerank_result = CourseRerankResult(
        success=True,
        courses=[east_course, west_course],
        rerank_strategy="llm_course_rerank",
    )
    feasibility_result = CourseFeasibilityResult(
        success=True,
        available_courses=["GXK201", "GXK202"],
        data={"total_checked": 2, "available_count": 2, "filtered_count": 0},
    )
    reason_result = RecommendationReasonResult(
        success=True,
        reasons=[{"course_id": "GXK201", "reason": "符合西校区与自然科学偏好。"}],
    )

    orchestrator = SupervisorOrchestrator(
        student_profile_agent=_AgentStub(StudentProfileResult(success=True, profile=profile)),
        course_recall_agent=_AgentStub(recall_result),
        course_rerank_agent=_AgentStub(rerank_result),
        course_feasibility_agent=_AgentStub(feasibility_result),
        recommendation_reason_agent=_AgentStub(reason_result),
    )

    monkeypatch.setattr(
        orchestrator.ab_engine, "assign",
        lambda user_id, experiment_id: {"group": "pipeline", "config": {}},
    )

    response = await orchestrator.recommend(req)

    assert [course.course_id for course in response.courses] == ["GXK201"]
    assert all(course.campus == "西校区" for course in response.courses)
