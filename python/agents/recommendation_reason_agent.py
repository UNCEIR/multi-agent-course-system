from __future__ import annotations

import json
from typing import Any, AsyncGenerator

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from config import get_settings
from models.schemas import Course, RecommendationReasonResult, StudentProfile
from services import build_chat_openai
from services.stream_token_markup_parser import StreamTokenMarkupParser

from .base_agent import BaseAgent

logger = structlog.get_logger()

REASON_PROMPT = """你是学校教务系统的选课建议助手。请为推荐课程生成简洁、真实、可执行的推荐理由。

要求:
1. 每门课一条，说明匹配学生需求的原因。
2. popularity_level 为整数编码：4=爆满，3=热门，2=正常偏热，1=正常，0=冷门。
3. 如果课程爆满、容量紧张、考核方式不完全匹配，要温和提示风险。
4. 不要编造数据，只能使用输入字段。
5. 每条 40-80 字。

输出JSON数组:
[{"course_id": "xxx", "reason": "推荐理由"}]

只输出JSON，不要其他内容。"""

REASON_STREAM_PROMPT = """你是学校教务系统的选课建议助手。请为以下推荐课程生成简洁、真实的自然语言选课建议。

课程列表中的每门课都有唯一的 course_id 和 course_name，请严格按照提供的 course_id 和 course_name 引用，不要编造。

输出要求：
1. 先写一段 1-2 句的总起语（不要包含任何 marker），总体介绍推荐思路。
2. 然后依次为每门课输出推荐理由，每门课程推荐以 [COURSE:course_id:course_name] 作为起始标记。
3. 每条推荐理由 40-80 字，说明课程如何匹配学生兴趣、校区、时间、考核方式等偏好。
4. popularity_level 为整数编码：4=爆满，3=热门，2=正常偏热，1=正常，0=冷门。
5. 如果课程爆满、容量紧张、考核方式不完全匹配，在推荐理由中温和提示风险，自然融入文本。
6. 不要编造数据，只能使用输入字段。
7. 不要输出 JSON，只输出纯文本。
8. 所有课程推荐完成后直接结束，不需要总结段。

输出示例：

根据你的偏好，结合课程容量和考核方式，推荐以下公选课供参考：

[COURSE:GXK001:电影艺术赏析] 该课程属于人文艺术领域，张老师授课风格生动，上课时间为周二下午，难度适中，作业量较低且无考试，非常适合对艺术感兴趣的同学。当前选课人数较多，建议开选后优先提交。

[COURSE:GXK002:Python程序设计] 该课程面向零基础学生，涵盖 Python 基础与数据分析，考核方式为项目制无考试，适合偏好动手实践的同学。"""


class RecommendationReasonAgent(BaseAgent):
    def __init__(self):
        settings = get_settings()
        super().__init__(
            name="recommendation_reason",
            timeout=settings.agent_timeout_marketing_copy,
        )
        self.llm = build_chat_openai(
            temperature=0.55, max_tokens=1536, streaming=True
        )
    async def _execute(self, **kwargs: Any) -> RecommendationReasonResult:
        profile: StudentProfile | None = kwargs.get("student_profile")
        courses: list[Course] = kwargs.get("courses", [])
        warnings: list[dict[str, Any]] = kwargs.get("warnings", [])
        if not courses:
            return RecommendationReasonResult(success=True, reasons=[], confidence=1.0)

        reasons = await self._llm_reasons(profile, courses, warnings)
        if not reasons:
            logger.warning(
                "recommendation_reason.llm_fallback",
                course_count=len(courses),
                warning_count=len(warnings),
            )
            reasons = self._fallback_reasons(courses, warnings)
        logger.info(
            "recommendation_reason.done",
            course_count=len(courses),
            reason_count=len(reasons),
        )
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
        course_payload = self._build_course_payload(courses)
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
            logger.error("recommendation_reason.llm_parse_failed")
            return []

    @staticmethod
    def _build_course_payload(courses: list[Course]) -> list[dict[str, Any]]:
        return [
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
    async def astream_reasons(
        self,
        profile: StudentProfile | None,
        courses: list[Course],
        warnings: list[dict[str, Any]],
    ) -> AsyncGenerator[dict[str, Any], None]:
        if not courses:
            return

        course_payload = self._build_course_payload(courses)
        messages = [
            SystemMessage(content=REASON_STREAM_PROMPT),
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
        parser = StreamTokenMarkupParser()
        token_stream = self._extract_tokens(messages)
        async for chunk in parser.parse(token_stream):
            yield chunk

    async def _extract_tokens(
        self, messages: list
    ) -> AsyncGenerator[str, None]:
        async for chunk in self.llm.astream(messages):
            content = chunk.content
            if isinstance(content, str):
                yield content
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        text = item.get("text", "")
                        if text:
                            yield text
                    elif item:
                        yield str(item)

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
