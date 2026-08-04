from __future__ import annotations

from typing import TYPE_CHECKING


__all__ = [
    "BaseAgent",
    "StudentProfileAgent",
    "CourseRecallAgent",
    "CourseRerankAgent",
    "CourseFeasibilityAgent",
    "RecommendationReasonAgent",
]

if TYPE_CHECKING:
    from .base_agent import BaseAgent
    from .course_feasibility_agent import CourseFeasibilityAgent
    from .course_recall_agent import CourseRecallAgent
    from .course_rerank_agent import CourseRerankAgent
    from .recommendation_reason_agent import RecommendationReasonAgent
    from .student_profile_agent import StudentProfileAgent


def __getattr__(name: str):
    if name == "BaseAgent":
        from .base_agent import BaseAgent

        return BaseAgent
    if name == "StudentProfileAgent":
        from .student_profile_agent import StudentProfileAgent

        return StudentProfileAgent
    if name == "CourseRecallAgent":
        from .course_recall_agent import CourseRecallAgent

        return CourseRecallAgent
    if name == "CourseRerankAgent":
        from .course_rerank_agent import CourseRerankAgent

        return CourseRerankAgent
    if name == "CourseFeasibilityAgent":
        from .course_feasibility_agent import CourseFeasibilityAgent

        return CourseFeasibilityAgent
    if name == "RecommendationReasonAgent":
        from .recommendation_reason_agent import RecommendationReasonAgent

        return RecommendationReasonAgent
    raise AttributeError(f"module 'app.recommend.agents' has no attribute {name!r}")
