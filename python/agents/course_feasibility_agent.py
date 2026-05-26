from __future__ import annotations

import json
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from models.schemas import Course, CourseFeasibilityResult, PriorityAdvice, StudentProfile
from services import build_chat_openai

from .base_agent import BaseAgent

logger = structlog.get_logger()

PRIORITY_ADVICE_PROMPT = """你是选课可行性分析专家。基于学生画像和课程容量的真实数据，
判断每门课的选课可行性并给出抢课优先级建议。

【年级优先权业务规则（确定性）】
- 大四 > 大三 > 大二 = 大一
- 爆满课程（已选人数 >= 容量）：大四优先留，大三次之，大二/大一可能被随机踢出

【可行性判断】
- enrolled >= capacity → 爆满，可行性低
- enrolled / capacity >= 0.85 → 偏紧，需快速抢
- enrolled / capacity < 0.85 → 可控，可作保底

【priority 取值】
- high: 容量可控，年级优先权充足
- medium: 容量偏紧 或 年级优先权处于中位
- low: 爆满且低年级优先权不足，抢到概率低

输出 JSON 数组（只输出 JSON，不要其他内容）:
[{"course_id": "...", "priority": "high|medium|low", "advice": "40-60字可行性分析，引用真实数据"}]
"""


class CourseFeasibilityAgent(BaseAgent):
    def __init__(self):
        from config import get_settings

        settings = get_settings()
        super().__init__(
            name="course_feasibility",
            timeout=settings.agent_timeout_inventory,
        )
        self.llm = build_chat_openai(temperature=0.3, max_tokens=4096)

    async def _execute(self, **kwargs: Any) -> CourseFeasibilityResult:
        courses: list[Course] = kwargs.get("courses", [])
        profile: StudentProfile | None = kwargs.get("student_profile")
        context: dict[str, Any] = kwargs.get("context", {})

        available: list[str] = []
        warnings: list[dict[str, Any]] = []
        filtered: list[dict[str, Any]] = []
        available_courses: list[Course] = []

        for course in courses:
            reasons = self._hard_conflicts(course, profile, context)
            if reasons:
                filtered.append({"course_id": course.course_id, "course_name": course.course_name, "reasons": reasons})
                continue

            available.append(course.course_id)
            available_courses.append(course)
            course_warnings = self._warnings(course, profile)
            warnings.extend(course_warnings)

        priority_advice = await self._llm_priority_advice(available_courses, profile)

        logger.info(
            "course_feasibility.done",
            total=len(courses),
            available=len(available),
            filtered=len(filtered),
            warnings=len(warnings),
        )

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

    async def _llm_priority_advice(
        self, courses: list[Course], profile: StudentProfile | None
    ) -> dict[str, PriorityAdvice]:
        if not courses:
            return {}

        llm_courses = courses[:12]
        rule_courses = courses[12:]

        courses_data = []
        for c in llm_courses:
            capacity_ratio = (c.current_enrolled / c.capacity) if c.capacity > 0 else 0
            courses_data.append({
                "course_id": c.course_id,
                "name": c.course_name,
                "enrolled": c.current_enrolled,
                "capacity": c.capacity,
                "ratio": round(capacity_ratio, 2),
                "popularity": c.popularity_level,
                "campus": c.campus,
                "has_exam": c.has_exam,
                "difficulty": c.difficulty,
                "workload": c.workload,
            })

        student_data = {
            "grade": profile.grade if profile else "",
            "preferences": {
                "campus": profile.preferred_campus if profile else [],
                "exam": profile.exam_preference if profile else "",
                "workload": profile.workload_preference if profile else "",
                "difficulty": profile.difficulty_preference if profile else "",
            } if profile else {},
        }

        user_input = json.dumps({
            "student": student_data,
            "courses": courses_data,
        }, ensure_ascii=False)

        try:
            messages = [
                SystemMessage(content=PRIORITY_ADVICE_PROMPT),
                HumanMessage(content=user_input),
            ]
            response = await self.llm.ainvoke(messages)
            parsed = self._parse_advice_json(response.content, llm_courses)
            if parsed:
                if rule_courses:
                    parsed.update(self._rule_priority_advice_batch(rule_courses))
                return parsed
            logger.warning(
                "course_feasibility.llm_advice_parse_empty",
                course_count=len(courses),
                raw_len=len(response.content),
                raw_preview=str(response.content)[:200],
            )
        except Exception:
            logger.warning("course_feasibility.llm_advice_failed", exc_info=True)

        return self._rule_priority_advice_batch(courses)

    @staticmethod
    def _parse_advice_json(raw: str, courses: list[Course]) -> dict[str, PriorityAdvice]:
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
            items = json.loads(cleaned)
            if not isinstance(items, list):
                return {}
            result: dict[str, PriorityAdvice] = {}
            for item in items:
                cid = str(item.get("course_id", ""))
                if cid:
                    result[cid] = PriorityAdvice(
                        advice=str(item.get("advice", "")),
                        priority=str(item.get("priority", "medium")),
                    )
            return result
        except (json.JSONDecodeError, IndexError, TypeError):
            return {}

    @staticmethod
    def _rule_priority_advice_batch(courses: list[Course]) -> dict[str, PriorityAdvice]:
        result: dict[str, PriorityAdvice] = {}
        for course in courses:
            if course.popularity_level >= 4 or (
                course.capacity > 0 and course.current_enrolled >= course.capacity
            ):
                result[course.course_id] = PriorityAdvice(
                    advice="冲刺优先级高：开选后优先抢，建议同时准备 1-2 门替代课。",
                    priority="low",
                )
            elif course.capacity > 0 and course.current_enrolled / course.capacity >= 0.85:
                result[course.course_id] = PriorityAdvice(
                    advice="容量偏紧：建议排在前序志愿。",
                    priority="medium",
                )
            else:
                result[course.course_id] = PriorityAdvice(
                    advice="容量相对可控：可作为稳妥备选。",
                    priority="high",
                )
        return result

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

        if profile and profile.exam_preference == "不考试" and course.has_exam == 1:
            warnings.append(
                {
                    "course_id": course.course_id,
                    "course_name": course.course_name,
                    "level": "low",
                    "type": "exam_soft_mismatch",
                    "message": "该课程有考试，仅供参考（未设为硬性要求，可酌情选择）。",
                }
            )
        if profile and profile.group_work_preference == "不小组" and course.group_work_required == 1:
            warnings.append(
                {
                    "course_id": course.course_id,
                    "course_name": course.course_name,
                    "level": "low",
                    "type": "group_work_soft_mismatch",
                    "message": "该课程包含小组作业，仅供参考（未设为硬性要求，可酌情选择）。",
                }
            )
        return warnings
