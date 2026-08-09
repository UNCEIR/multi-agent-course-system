from __future__ import annotations

import pytest

from models.schemas import (
    Course,
    CourseFeasibilityResult,
    CourseRecallResult,
    CourseRerankResult,
    RecommendationRequest,
    StudentProfile,
    StudentProfileResult,
)
from agent.recommend.supervisor import SupervisorOrchestrator


class _AgentStub:
    def __init__(self, result):
        self._result = result

    async def run(self, **kwargs):
        return self._result

    async def astream_reasons(self, **kwargs):
        courses = kwargs.get("courses", [])
        for idx, course in enumerate(courses):
            yield {
                "type": "course_start",
                "course_id": course.course_id,
                "course_name": course.course_name,
                "index": idx,
            }
            yield {
                "type": "text",
                "course_id": course.course_id,
                "token": f"推荐理由-{course.course_id}",
            }
            yield {"type": "course_end", "course_id": course.course_id}
        return


def _make_profile():
    return StudentProfile(
        student_id="S10001",
        raw_prompt="测试",
        preferred_domains=["人文艺术"],
        exam_preference="不考试",
    )


def _make_course(course_id: str, name: str, **kwargs):
    fields = {
        "course_id": course_id,
        "course_name": name,
        "domain": "人文艺术",
        "campus": "东校区",
        "time_slot": "周二第5-6节",
        "has_exam": 0,
        "workload": "低",
        "grade_friendly": "高",
    }
    fields.update(kwargs)
    return Course(**fields)


@pytest.mark.agent
@pytest.mark.asyncio
async def test_stream_recommend_event_sequence():
    req = RecommendationRequest(
        user_id="S10001",
        num_items=2,
        prompt="想选不考试的艺术类公选课",
    )
    profile = _make_profile()
    c1 = _make_course("GXK001", "电影鉴赏")
    c2 = _make_course("GXK002", "音乐导论")

    orchestrator = SupervisorOrchestrator(
        student_profile_agent=_AgentStub(
            StudentProfileResult(success=True, profile=profile)
        ),
        course_recall_agent=_AgentStub(
            CourseRecallResult(success=True, courses=[c1, c2], recall_strategies=["test"])
        ),
        course_rerank_agent=_AgentStub(
            CourseRerankResult(success=True, courses=[c1, c2], rerank_strategy="test")
        ),
        course_feasibility_agent=_AgentStub(
            CourseFeasibilityResult(
                success=True,
                available_courses=["GXK001", "GXK002"],
                data={"total_checked": 2, "available_count": 2, "filtered_count": 0},
            )
        ),
        recommendation_reason_agent=_AgentStub(None),
    )

    events = []
    async for event in orchestrator.stream_recommend(req):
        events.append(event)

    event_types = [e["event"] for e in events]
    assert event_types == [
        "phase",          # start
        "phase",          # phase1_complete
        "phase",          # phase2_complete
        "phase",          # phase3_start
        "course_start",   # GXK001
        "text",           # GXK001
        "course_end",     # GXK001
        "course_start",   # GXK002
        "text",           # GXK002
        "course_end",     # GXK002
        "phase",          # phase3_complete
        "done",           # final
    ]

    done = events[-1]["data"]
    assert done["request_id"] is not None
    assert len(done["courses"]) == 2
    assert done["courses"][0]["course_id"] == "GXK001"
    assert len(done["recommendation_reasons"]) == 2


@pytest.mark.agent
@pytest.mark.asyncio
async def test_stream_recommend_no_profile_skips_refined_recall():
    req = RecommendationRequest(
        user_id="S10002",
        num_items=1,
        prompt="测试",
    )
    c1 = _make_course("GXK001", "电影鉴赏")

    orchestrator = SupervisorOrchestrator(
        student_profile_agent=_AgentStub(
            StudentProfileResult(success=True, profile=None)
        ),
        course_recall_agent=_AgentStub(
            CourseRecallResult(success=True, courses=[c1], recall_strategies=["test"])
        ),
        course_rerank_agent=_AgentStub(
            CourseRerankResult(success=True, courses=[c1], rerank_strategy="test")
        ),
        course_feasibility_agent=_AgentStub(
            CourseFeasibilityResult(
                success=True,
                available_courses=["GXK001"],
                data={"total_checked": 1, "available_count": 1, "filtered_count": 0},
            )
        ),
        recommendation_reason_agent=_AgentStub(None),
    )

    events = []
    async for event in orchestrator.stream_recommend(req):
        events.append(event)

    event_types = [e["event"] for e in events]
    assert event_types[-1] == "done"
    p1_data = events[1]["data"]
    assert p1_data["profile_extracted"] is False


@pytest.mark.agent
@pytest.mark.asyncio
async def test_stream_recommend_empty_courses():
    req = RecommendationRequest(
        user_id="S10003",
        num_items=2,
        prompt="测试",
    )
    profile = _make_profile()

    orchestrator = SupervisorOrchestrator(
        student_profile_agent=_AgentStub(
            StudentProfileResult(success=True, profile=profile)
        ),
        course_recall_agent=_AgentStub(
            CourseRecallResult(success=True, courses=[], recall_strategies=["empty"])
        ),
        course_rerank_agent=_AgentStub(
            CourseRerankResult(success=True, courses=[], rerank_strategy="empty")
        ),
        course_feasibility_agent=_AgentStub(
            CourseFeasibilityResult(
                success=True,
                available_courses=[],
                data={"total_checked": 0, "available_count": 0, "filtered_count": 0},
            )
        ),
        recommendation_reason_agent=_AgentStub(None),
    )

    events = []
    async for event in orchestrator.stream_recommend(req):
        events.append(event)

    event_types = [e["event"] for e in events]
    assert "done" in event_types
    assert "error" not in event_types
    done = events[-1]["data"]
    assert done["courses"] == []


@pytest.mark.agent
@pytest.mark.asyncio
async def test_stream_recommend_phase1_error():
    req = RecommendationRequest(
        user_id="S10004",
        num_items=2,
        prompt="测试",
    )

    class _FailingAgent:
        async def run(self, **kwargs):
            raise RuntimeError("LLM不可用")

    orchestrator = SupervisorOrchestrator(
        student_profile_agent=_FailingAgent(),
        course_recall_agent=_AgentStub(
            CourseRecallResult(success=True, courses=[], recall_strategies=[])
        ),
        course_rerank_agent=_AgentStub(
            CourseRerankResult(success=True, courses=[], rerank_strategy="")
        ),
        course_feasibility_agent=_AgentStub(
            CourseFeasibilityResult(success=True, available_courses=[])
        ),
        recommendation_reason_agent=_AgentStub(None),
    )

    events = []
    async for event in orchestrator.stream_recommend(req):
        events.append(event)

    event_types = [e["event"] for e in events]
    assert event_types == ["phase", "error"]
    error = events[1]["data"]
    assert error["code"] == "RUNTIMEERROR"
    assert "LLM" in error["message"]


@pytest.mark.agent
@pytest.mark.asyncio
async def test_stream_recommend_includes_warnings():
    req = RecommendationRequest(
        user_id="S10005",
        num_items=1,
        prompt="测试",
    )
    profile = _make_profile()
    c1 = _make_course("GXK001", "电影鉴赏", capacity=100, current_enrolled=95)

    orchestrator = SupervisorOrchestrator(
        student_profile_agent=_AgentStub(
            StudentProfileResult(success=True, profile=profile)
        ),
        course_recall_agent=_AgentStub(
            CourseRecallResult(success=True, courses=[c1], recall_strategies=["test"])
        ),
        course_rerank_agent=_AgentStub(
            CourseRerankResult(success=True, courses=[c1], rerank_strategy="test")
        ),
        course_feasibility_agent=_AgentStub(
            CourseFeasibilityResult(
                success=True,
                available_courses=["GXK001"],
                selection_warnings=[
                    {
                        "course_id": "GXK001",
                        "level": "medium",
                        "type": "capacity_tight",
                        "message": "容量偏紧",
                    }
                ],
                data={"total_checked": 1, "available_count": 1, "filtered_count": 0},
            )
        ),
        recommendation_reason_agent=_AgentStub(None),
    )

    events = []
    async for event in orchestrator.stream_recommend(req):
        events.append(event)

    done = events[-1]["data"]
    assert len(done["selection_warnings"]) == 1
    assert done["selection_warnings"][0]["type"] == "capacity_tight"

@pytest.mark.agent
@pytest.mark.asyncio
async def test_stream_recommend_unified_react_fallback_pipeline(monkeypatch):
    """统一流式：ReAct 失败时切换 Pipeline，done.experiment_group=pipeline_fallback。"""
    req = RecommendationRequest(user_id="S_FALLBACK", num_items=1, prompt="测试")
    c1 = _make_course("GXK001", "电影鉴赏")

    orchestrator = SupervisorOrchestrator(
        student_profile_agent=_AgentStub(StudentProfileResult(success=True, profile=_make_profile())),
        course_recall_agent=_AgentStub(CourseRecallResult(success=True, courses=[c1], recall_strategies=["test"])),
        course_rerank_agent=_AgentStub(CourseRerankResult(success=True, courses=[c1], rerank_strategy="test")),
        course_feasibility_agent=_AgentStub(
            CourseFeasibilityResult(success=True, available_courses=["GXK001"], data={})
        ),
        recommendation_reason_agent=_AgentStub(None),
    )

    async def fake_react_stream(_request):
        yield {"event": "phase", "data": {"phase": "react_start"}}
        yield {
            "event": "error",
            "data": {"code": "LLM_FAILED", "message": "react llm down", "phase": "react"},
        }

    monkeypatch.setattr(orchestrator, "react_stream_recommend", fake_react_stream)

    events = []
    async for event in orchestrator.stream_recommend_unified(req, mode="react"):
        events.append(event)

    event_types = [e["event"] for e in events]
    assert "phase" in event_types
    assert any(e["data"].get("phase") == "react_fallback" for e in events if e["event"] == "phase")
    assert event_types[-1] == "done"
    done = events[-1]["data"]
    assert done["experiment_group"] == "pipeline_fallback"
    assert done["react_fallback"]["error"] == "RuntimeError"
    assert len(done["courses"]) == 1


@pytest.mark.agent
@pytest.mark.asyncio
async def test_react_empty_turn_terminates(monkeypatch):
    """ReAct 空转（决策不调工具且无 FINISH）立即终止，不继续白耗。"""
    from unittest.mock import AsyncMock, MagicMock

    req = RecommendationRequest(user_id="S_IDLE", num_items=1, prompt="测试")
    c1 = _make_course("GXK001", "电影鉴赏")

    orchestrator = SupervisorOrchestrator(
        student_profile_agent=_AgentStub(StudentProfileResult(success=True, profile=_make_profile())),
        course_recall_agent=_AgentStub(CourseRecallResult(success=True, courses=[c1], recall_strategies=["test"])),
        course_rerank_agent=_AgentStub(CourseRerankResult(success=True, courses=[c1], rerank_strategy="test")),
        course_feasibility_agent=_AgentStub(
            CourseFeasibilityResult(success=True, available_courses=["GXK001"], data={})
        ),
        recommendation_reason_agent=_AgentStub(None),
    )

    # 记录 llm.ainvoke 被调用次数
    invoke_count = {"n": 0}

    class _EmptyLLM:
        def __init__(self):
            pass

        async def ainvoke(self, messages):
            invoke_count["n"] += 1
            # 返回无 tool_calls、无 FINISH 的响应 → 应触发空转即终止
            return MagicMock(tool_calls=[], content="我先思考一下")

    import agent.recommend.supervisor as sup_mod
    import ai as ai_mod

    monkeypatch.setattr(ai_mod, "build_tool_calling_llm", lambda *a, **k: _EmptyLLM())

    response = await orchestrator.react_recommend(req)
    # 空转即终止：只调用 1 次 llm，不再 continue 第二次
    assert invoke_count["n"] == 1
    assert response.experiment_group == "react"


@pytest.mark.agent
@pytest.mark.asyncio
async def test_react_rerank_feasibility_parallel(monkeypatch):
    """B 组并行：rerank_courses 与 check_feasibility 同一轮同时调用时 gather 执行。"""
    from unittest.mock import MagicMock

    req = RecommendationRequest(user_id="S_PAR", num_items=1, prompt="测试")
    c1 = _make_course("GXK001", "电影鉴赏")
    c2 = _make_course("GXK002", "音乐导论")

    orchestrator = SupervisorOrchestrator(
        student_profile_agent=_AgentStub(StudentProfileResult(success=True, profile=_make_profile())),
        course_recall_agent=_AgentStub(CourseRecallResult(success=True, courses=[c1, c2], recall_strategies=["test"])),
        course_rerank_agent=_AgentStub(CourseRerankResult(success=True, courses=[c1, c2], rerank_strategy="test")),
        course_feasibility_agent=_AgentStub(
            CourseFeasibilityResult(success=True, available_courses=["GXK001", "GXK002"], data={})
        ),
        recommendation_reason_agent=_AgentStub(None),
    )

    class _ParallelLLM:
        def __init__(self):
            self.rounds = 0

        async def ainvoke(self, messages):
            self.rounds += 1
            if self.rounds == 1:
                # 第一轮先 search_courses 填充候选
                return MagicMock(
                    tool_calls=[
                        {
                            "name": "search_courses",
                            "args": {"strategy": "wide"},
                            "id": "tc0",
                        },
                    ]
                )
            if self.rounds == 2:
                # 第二轮同时调 rerank_courses + check_feasibility（B 组并行）
                return MagicMock(
                    tool_calls=[
                        {
                            "name": "rerank_courses",
                            "args": {"num_items": 1},
                            "id": "tc1",
                        },
                        {
                            "name": "check_feasibility",
                            "args": {},
                            "id": "tc2",
                        },
                    ]
                )
            # 第三轮 FINISH
            return MagicMock(tool_calls=[], content="FINISH")

    import ai as ai_mod

    monkeypatch.setattr(ai_mod, "build_tool_calling_llm", lambda *a, **k: _ParallelLLM())

    response = await orchestrator.react_recommend(req)
    # B 组并行后 courses 合并
    assert response.experiment_group == "react"
    assert len(response.courses) == 1, f"courses={[c.course_id for c in response.courses]}"
