from __future__ import annotations

import pytest

from agent.recommend.agents.student_profile_agent import StudentProfileAgent
from models.schemas import Course, HardConstraints
from agent.recommend.hard_constraint_filter import HardConstraintFilter


def _parse_categories_from_prompt(prompt: str) -> list[str]:
    agent = StudentProfileAgent.__new__(StudentProfileAgent)
    hard = agent._parse_hard_constraints(
        data={"hard_constraints": {}},
        prompt=prompt,
        context={},
    )
    return hard.categories


def test_parse_hard_constraints_extracts_prompt_campus_and_category():
    agent = StudentProfileAgent.__new__(StudentProfileAgent)
    hard = agent._parse_hard_constraints(
        data={"hard_constraints": {}},
        prompt="我要去西校区上课，而且我只要上自然科学类的课",
        context={},
    )
    assert "西校区" in hard.campus
    assert "自然科学与工程技术类" in hard.categories


@pytest.mark.parametrize(
    ("prompt", "expected_category"),
    [
        ("我只要理工类的课", "自然科学与工程技术类"),
        ("想找文科的公选课", "人文与社会科学类"),
        ("偏好工科类的选修", "自然科学与工程技术类"),
        ("只要理科类课程", "自然科学与工程技术类"),
        ("想选社科类公选课", "人文与社会科学类"),
        ("而且我只要上自然科学类的课", "自然科学与工程技术类"),
    ],
)
def test_parse_hard_constraints_extracts_b_scheme_category_prompts(
    prompt: str, expected_category: str
):
    assert expected_category in _parse_categories_from_prompt(prompt)


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
