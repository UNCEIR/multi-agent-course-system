from __future__ import annotations

import json
from typing import Any
import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from config import get_settings
from models.schemas import Course, CourseRerankResult, StudentProfile
from services import build_chat_openai

from .base_agent import BaseAgent


logger = structlog.get_logger()
RERANK_PROMPT = """你是学校教务系统的公选课推荐排序专家。请根据学生画像和候选课程，选出最适合的{num_items}门公选课。

学生画像:
{student_profile}

候选课程:
{candidates}

排序原则:
1. 优先满足学生明确提出的兴趣、校区、时间、考核方式和学习负担要求。
2. popularity_level 为整数编码：4=爆满，3=热门，2=正常偏热，1=正常，0=冷门。
3. 对 popularity_level=4 的爆满课程不要直接剔除，但要降低稳定性分数，除非它与兴趣高度匹配。
4. 低年级学生（大一/大二）选爆满课抢课优先级低、可能被随机踢出，除非兴趣高度匹配否则排后面。
5. 对不考试、作业少、给分友好等偏好要结合课程字段判断，不要凭空臆测。
6. 尽量保证课程领域多样性，避免结果全是同一领域。
7. 只允许输出候选课程中存在的课程ID。

输出课程ID JSON数组，按推荐优先级排序:
["course_id_1", "course_id_2"]

只输出JSON数组，不要其他内容。"""


class CourseRerankAgent(BaseAgent):
    def __init__(self):
        settings = get_settings()
        super().__init__(
            name="course_rerank",
            timeout=settings.agent_timeout_product_rerank,
        )
        self.llm = build_chat_openai(temperature=0.25, max_tokens=4096)
    async def _execute(self, **kwargs: Any) -> CourseRerankResult:
        profile: StudentProfile | None = kwargs.get("student_profile")
        candidates: list[Course] = kwargs.get("candidates", [])
        num_items: int = kwargs.get("num_items", 10)

        if not candidates:
            return CourseRerankResult(success=True, courses=[], rerank_strategy="empty", confidence=1.0)

        if profile:
            ranked_ids = await self._llm_rerank(profile, candidates, num_items)
            strategy = "llm_course_rerank"
        else:
            ranked_ids = self._rule_based_rerank(candidates, num_items)
            strategy = "rule_based_course_rerank"
        id_to_course = {course.course_id: course for course in candidates}
        final_courses: list[Course] = []
        for course_id in ranked_ids:
            if course_id in id_to_course and id_to_course[course_id] not in final_courses:
                final_courses.append(id_to_course[course_id])

        if len(final_courses) < num_items:
            for course in candidates:
                if course not in final_courses:
                    final_courses.append(course)
                if len(final_courses) >= num_items:
                    break

        final_courses = self._ensure_domain_diversity(final_courses, num_items)
        return CourseRerankResult(
            success=True,
            courses=final_courses[:num_items],
            rerank_strategy=strategy,
            data={"candidate_count": len(candidates), "output_count": len(final_courses[:num_items])},
            confidence=0.84,
        )

    async def _llm_rerank(
        self, profile: StudentProfile, candidates: list[Course], num_items: int
    ) -> list[str]:
        profile_summary = profile.model_dump()
        scored = [(self._compute_score(course, profile), course) for course in candidates]
        scored.sort(key=lambda item: item[0], reverse=True)
        prefiltered = [course for _, course in scored[:40]]
        candidate_summary = [
            {
                "id": course.course_id,
                "name": course.course_name,
                "teacher": course.teacher,
                "domain": course.domain,
                "category": course.course_category,
                "campus": course.campus,
                "time_slot": course.time_slot,
                "popularity_level": course.popularity_level,
                "difficulty": course.difficulty,
                "workload": course.workload,
                "grade_friendly": course.grade_friendly,
                "has_exam": course.has_exam,
                "group_work_required": course.group_work_required,
                "assessment": course.assessment,
                "tags": course.tags,
            }
            for course in prefiltered
        ]
        prompt = RERANK_PROMPT.format(
            num_items=num_items,
            student_profile=json.dumps(profile_summary, ensure_ascii=False),
            candidates=json.dumps(candidate_summary, ensure_ascii=False),
        )
        response = await self.llm.ainvoke(
            [
                SystemMessage(content="你是公选课推荐排序专家。"),
                HumanMessage(content=prompt),
            ]
        )
        try:
            raw = response.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            ids = json.loads(raw)
            return [str(course_id) for course_id in ids]
        except (json.JSONDecodeError, IndexError, TypeError):
            logger.warning("course_rerank.llm_parse_failed")
            return self._rule_based_rerank(candidates, num_items)

    @staticmethod
    def _rule_based_rerank(candidates: list[Course], num_items: int) -> list[str]:
        scored = []
        for course in candidates:
            score = course.score
            if course.has_exam == 0:
                score += 0.5
            if course.workload in ("低", "少"):
                score += 0.5
            if course.popularity_level >= 4:
                score -= 0.4
            scored.append((score, course.course_id))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [course_id for _, course_id in scored[:num_items]]

    @staticmethod
    def _ensure_domain_diversity(courses: list[Course], num_items: int) -> list[Course]:
        result: list[Course] = []
        domain_count: dict[str, int] = {}
        for course in courses:
            count = domain_count.get(course.domain, 0)
            if count < 3:
                result.append(course)
                domain_count[course.domain] = count + 1
            if len(result) >= num_items:
                return result
        for course in courses:
            if course not in result:
                result.append(course)
            if len(result) >= num_items:
                break
        return result

    @staticmethod
    def _compute_score(course: Course, profile: StudentProfile | None) -> float:
        milvus_sim = course.score
        profile_score = 0.0
        if profile:
            if course.domain in profile.preferred_domains:
                profile_score += 4.0
            if course.course_category in profile.preferred_categories:
                profile_score += 3.0
            if course.campus in profile.preferred_campus:
                profile_score += 2.0
            if profile.workload_preference == "少" and course.workload in ("低", "少"):
                profile_score += 1.5
            if profile.exam_preference == "不考试" and course.has_exam == 0:
                profile_score += 1.5
            if profile.grade_friendly_preference == "高" and course.grade_friendly in ("高", "中"):
                profile_score += 1.2
        if course.popularity_level >= 3:
            profile_score += 0.8
        if course.has_exam == 0:
            profile_score += 0.5
        if course.workload in ("低", "少"):
            profile_score += 0.5
        if course.popularity_level >= 4:
            profile_score -= 0.4
        if profile and profile.grade in ("大一", "大二") and course.popularity_level >= 4:
            profile_score -= 2.0
        milvus_weight = 0.5
        return round(profile_score * (1.0 + milvus_sim * milvus_weight), 4)
