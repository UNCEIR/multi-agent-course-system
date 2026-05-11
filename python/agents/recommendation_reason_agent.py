from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from config import get_settings
from models.schemas import Course, RecommendationReasonResult, StudentProfile
from services import build_chat_openai

from .base_agent import BaseAgent

REASON_PROMPT = """你是学校教务系统的选课建议助手。请为推荐课程生成简洁、真实、可执行的推荐理由。

要求:
1. 每门课一条，说明匹配学生需求的原因。
2. 如果课程爆满、容量紧张、考核方式不完全匹配，要温和提示风险。
3. 不要编造数据，只能使用输入字段。
4. 每条 40-80 字。

输出JSON数组:
[{"course_id": "xxx", "reason": "推荐理由"}]

只输出JSON，不要其他内容。"""


class RecommendationReasonAgent(BaseAgent):
    def __init__(self):
        settings = get_settings()
        super().__init__(
            name="recommendation_reason",
            timeout=settings.agent_timeout_marketing_copy,
        )
        self.llm = build_chat_openai(temperature=0.55, max_tokens=1536)

    async def _execute(self, **kwargs: Any) -> RecommendationReasonResult:
        profile: StudentProfile | None = kwargs.get("student_profile")
        courses: list[Course] = kwargs.get("courses", [])
        warnings: list[dict[str, Any]] = kwargs.get("warnings", [])

        if not courses:
            return RecommendationReasonResult(success=True, reasons=[], confidence=1.0)

        reasons = await self._llm_reasons(profile, courses, warnings)
        if not reasons:
            reasons = self._fallback_reasons(courses, warnings)

        return RecommendationReasonResult(
            success=True,
            reasons=reasons,
            data={"course_count": len(courses), "warning_count": len(warnings)},
            confidence=0.88,
        )

    async def _llm_reasons(
        self,
        profile: StudentProfile | None,
        courses: list[Course],
        warnings: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        course_payload = [
            {
                "course_id": course.course_id,
                "course_name": course.course_name,
                "teacher": course.teacher,
                "domain": course.domain,
                "campus": course.campus,
                "time_slot": course.time_slot,
                "difficulty": course.difficulty,
                "workload": course.workload,
                "grade_friendly": course.grade_friendly,
                "has_exam": course.has_exam,
                "assessment": course.assessment,
                "popularity_level": course.popularity_level,
                "rush_advice": course.rush_advice,
                "tags": course.tags,
            }
            for course in courses
        ]
        response = await self.llm.ainvoke(
            [
                SystemMessage(content=REASON_PROMPT),
                HumanMessage(
                    content=json.dumps(
                        {
                            "student_profile": profile.model_dump() if profile else {},
                            "courses": course_payload,
                            "warnings": warnings,
                        },
                        ensure_ascii=False,
                    )
                ),
            ]
        )
        try:
            raw = response.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            parsed = json.loads(raw)
            return [
                {"course_id": str(item.get("course_id", "")), "reason": str(item.get("reason", ""))}
                for item in parsed
                if item.get("course_id") and item.get("reason")
            ]
        except (json.JSONDecodeError, IndexError, TypeError):
            return []

    @staticmethod
    def _fallback_reasons(courses: list[Course], warnings: list[dict[str, Any]]) -> list[dict[str, str]]:
        warning_ids = {item.get("course_id") for item in warnings}
        reasons = []
        for course in courses:
            parts = [
                f"{course.course_name}属于{course.domain or course.course_category}",
                f"上课时间为{course.time_slot}" if course.time_slot else "",
                f"考核方式：{course.assessment}" if course.assessment else "",
            ]
            risk = "；但当前热度较高，建议提前抢课。" if course.course_id in warning_ids else "。"
            reasons.append(
                {
                    "course_id": course.course_id,
                    "reason": "，".join(part for part in parts if part) + risk,
                }
            )
        return reasons
