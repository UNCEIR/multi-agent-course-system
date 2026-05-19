from __future__ import annotations

from agents.student_profile_agent import StudentProfileAgent
from models.schemas import Course, HardConstraints
from orchestrator.hard_constraint_filter import HardConstraintFilter


def test_parse_hard_constraints_extracts_prompt_campus_and_category():
    agent = StudentProfileAgent.__new__(StudentProfileAgent)
    hard = agent._parse_hard_constraints(
        data={"hard_constraints": {}},
        prompt="我要去西校区上课，而且我只要上自然科学类的课",
        context={},
    )
    assert "西校区" in hard.campus
    assert "自然科学与工程技术类" in hard.categories


def test_hard_constraint_filter_accepts_fuzzy_category_match():
    course = Course(
        course_id="GXK301",
        course_name="地球科学概论",
        course_category="自然科学与工程技术类",
        domain="自然环境",
        campus="西校区",
    )
    hard = HardConstraints(campus=["西校区"], categories=["自然科学类"])
    passing, filtered, warnings = HardConstraintFilter().filter([course], hard)
    assert [item.course_id for item in passing] == ["GXK301"]
    assert filtered == []
    assert warnings == []
