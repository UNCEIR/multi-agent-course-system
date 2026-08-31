from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class HardConstraints(BaseModel):
    """硬性约束：违反即过滤，不参与排序打分。

    天然硬约束（只要提及具体值即触发，无需强意图词）：
      campus / avoid_time_slots / categories / teacher / no_exam

    强意图才升级（须包含 只/必须/一定/绝对/不能 等词）：
      no_group_work / max_difficulty / max_workload
    """

    campus: list[str] = Field(default_factory=list)
    avoid_time_slots: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    teacher: str = ""
    no_exam: bool = False
    no_group_work: bool = False
    max_difficulty: str | None = None
    max_workload: str | None = None


class StudentProfile(BaseModel):
    student_id: str
    raw_prompt: str = ""
    interests: list[str] = Field(default_factory=list)
    preferred_domains: list[str] = Field(default_factory=list)
    preferred_categories: list[str] = Field(default_factory=list)
    preferred_campus: list[str] = Field(default_factory=list)
    preferred_time_slots: list[str] = Field(default_factory=list)
    avoid_time_slots: list[str] = Field(default_factory=list)
    difficulty_preference: str = ""
    workload_preference: str = ""
    grade_friendly_preference: str = ""
    exam_preference: str = ""
    group_work_preference: str = ""
    grade: str = ""
    department: str = ""
    constraints: list[str] = Field(default_factory=list)
    real_time_tags: dict[str, Any] = Field(default_factory=dict)
    hard_constraints: HardConstraints = Field(default_factory=HardConstraints)


class Course(BaseModel):
    course_id: str
    course_name: str
    teacher: str = ""
    credits: float = 0.0
    course_type: str = "公共选修课"
    course_category: str = ""
    domain: str = ""
    campus: str = ""
    time_slot: str = ""
    location: str = ""
    capacity: int = 0
    current_enrolled: int = 0
    current_enrollment_ratio: float = 0.0
    popularity_level: int = 0
    rush_advice: str = ""
    description: str = ""
    assessment: str = ""
    difficulty: str = ""
    workload: str = ""
    grade_friendly: str = ""
    has_exam: int = 0
    group_work_required: int = 0
    suitable_for: str = ""
    tags: list[str] = Field(default_factory=list)
    score: float = 0.0
    match_reasons: list[str] = Field(default_factory=list)


class RecommendationRequest(BaseModel):
    user_id: str
    scene: str = "course_selection"
    num_items: int = 10
    context: dict[str, Any] = Field(default_factory=dict)
    query: str = ""
    prompt: str = ""
    device_type: str = "web"
    mode: str = Field(default="pipeline", pattern="^(pipeline|react)$", description="推荐模式：pipeline（默认，并行）/ react（ReAct，失败自动兜底 pipeline）")


class RecommendationResponse(BaseModel):
    request_id: str
    user_id: str
    courses: list[Course] = Field(default_factory=list)
    recommendation_reasons: list[dict[str, str]] = Field(default_factory=list)
    selection_warnings: list[dict[str, Any]] = Field(default_factory=list)
    priority_advice: dict[str, PriorityAdvice] = Field(default_factory=dict)
    experiment_group: str = "control"
    agent_results: dict[str, AgentResult] = Field(default_factory=dict)
    agent_latencies: dict[str, float] = Field(default_factory=dict)
    total_latency_ms: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.now)


class AgentResult(BaseModel):
    agent_name: str
    success: bool = True
    latency_ms: float = 0.0
    error: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0


class StudentProfileResult(AgentResult):
    agent_name: str = "student_profile"
    profile: StudentProfile | None = None


class CourseRecallResult(AgentResult):
    agent_name: str = "course_recall"
    courses: list[Course] = Field(default_factory=list)
    recall_strategies: list[str] = Field(default_factory=list)


class CourseRerankResult(AgentResult):
    agent_name: str = "course_rerank"
    courses: list[Course] = Field(default_factory=list)
    rerank_strategy: str = ""


class RecommendationReasonResult(AgentResult):
    agent_name: str = "recommendation_reason"
    reasons: list[dict[str, str]] = Field(default_factory=list)
    prompt_template_used: str = "course_explanation"


class PriorityAdvice(BaseModel):
    advice: str = ""
    priority: str = "medium"


class CourseFeasibilityResult(AgentResult):
    agent_name: str = "course_feasibility"
    available_courses: list[str] = Field(default_factory=list)
    selection_warnings: list[dict[str, Any]] = Field(default_factory=list)
    filtered_courses: list[dict[str, Any]] = Field(default_factory=list)
    priority_advice: dict[str, PriorityAdvice] = Field(default_factory=dict)
