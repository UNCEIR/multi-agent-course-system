from __future__ import annotations

from typing import Any

from models.schemas import Course, CourseFeasibilityResult, StudentProfile

from .base_agent import BaseAgent


class CourseFeasibilityAgent(BaseAgent):
    def __init__(self):
        from config import get_settings

        settings = get_settings()
        super().__init__(
            name="course_feasibility",
            timeout=settings.agent_timeout_inventory,
        )

    async def _execute(self, **kwargs: Any) -> CourseFeasibilityResult:
        courses: list[Course] = kwargs.get("courses", [])
        profile: StudentProfile | None = kwargs.get("student_profile")
        context: dict[str, Any] = kwargs.get("context", {})

        available: list[str] = []
        warnings: list[dict[str, Any]] = []
        filtered: list[dict[str, Any]] = []
        priority_advice: dict[str, str] = {}

        for course in courses:
            reasons = self._hard_conflicts(course, profile, context)
            if reasons:
                filtered.append({"course_id": course.course_id, "course_name": course.course_name, "reasons": reasons})
                continue

            available.append(course.course_id)
            course_warnings = self._warnings(course, profile)
            warnings.extend(course_warnings)
            priority_advice[course.course_id] = self._priority_advice(course)

        return CourseFeasibilityResult(
            success=True,
            available_courses=available,
            selection_warnings=warnings,
            filtered_courses=filtered,
            priority_advice=priority_advice,
            data={
                "total_checked": len(courses),
                "available_count": len(available),
                "filtered_count": len(filtered),
                "warning_count": len(warnings),
            },
            confidence=0.92,
        )

    def _hard_conflicts(
        self, course: Course, profile: StudentProfile | None, context: dict[str, Any]
    ) -> list[str]:
        reasons: list[str] = []
        avoid_time_slots = set(context.get("avoid_time_slots", []))
        if profile:
            avoid_time_slots.update(profile.avoid_time_slots)
        for avoid in avoid_time_slots:
            if avoid and avoid in course.time_slot:
                reasons.append(f"上课时间命中避开时段：{avoid}")

        student_grade = str(context.get("grade", ""))
        if student_grade and course.grade_limit and course.grade_limit != "无限制":
            if student_grade not in course.grade_limit:
                reasons.append(f"年级限制不匹配：{course.grade_limit}")

        student_major = str(context.get("major", ""))
        if student_major and course.major_limit and course.major_limit != "无限制":
            if student_major not in course.major_limit:
                reasons.append(f"专业限制不匹配：{course.major_limit}")

        if course.prerequisite and course.prerequisite not in ("无", "无限制"):
            completed = " ".join(context.get("completed_courses", []))
            if course.prerequisite not in completed:
                reasons.append(f"可能缺少先修要求：{course.prerequisite}")
        return reasons

    def _warnings(self, course: Course, profile: StudentProfile | None) -> list[dict[str, Any]]:
        warnings: list[dict[str, Any]] = []
        if course.capacity > 0 and course.current_enrolled >= course.capacity:
            warnings.append(
                {
                    "course_id": course.course_id,
                    "course_name": course.course_name,
                    "level": "high",
                    "type": "capacity_full",
                    "message": "当前已选人数达到或超过容量，建议作为冲刺志愿并准备替代课程。",
                }
            )
        elif course.capacity > 0 and course.current_enrolled / course.capacity >= 0.85:
            warnings.append(
                {
                    "course_id": course.course_id,
                    "course_name": course.course_name,
                    "level": "medium",
                    "type": "capacity_tight",
                    "message": "课程容量偏紧，选课时需要优先处理。",
                }
            )

        if profile and profile.exam_preference == "不考试" and course.has_exam == "是":
            warnings.append(
                {
                    "course_id": course.course_id,
                    "course_name": course.course_name,
                    "level": "medium",
                    "type": "exam_mismatch",
                    "message": "该课程可能有考试，与“不考试”偏好不完全一致。",
                }
            )
        if profile and profile.group_work_preference == "不小组" and course.group_work_required == "是":
            warnings.append(
                {
                    "course_id": course.course_id,
                    "course_name": course.course_name,
                    "level": "medium",
                    "type": "group_work_mismatch",
                    "message": "该课程可能包含小组作业，与偏好不完全一致。",
                }
            )
        return warnings

    @staticmethod
    def _priority_advice(course: Course) -> str:
        if course.popularity_level == "爆满" or (
            course.capacity > 0 and course.current_enrolled >= course.capacity
        ):
            return "冲刺优先级高：开选后优先抢，建议同时准备 1-2 门替代课。"
        if course.capacity > 0 and course.current_enrolled / course.capacity >= 0.85:
            return "容量偏紧：建议排在前序志愿。"
        return "容量相对可控：可作为稳妥备选。"
