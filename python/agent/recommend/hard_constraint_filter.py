"""
Hard constraint filter - Phase 1.5

After course recall and before LLM rerank, apply deterministic hard constraint filtering.
Courses that violate any hard constraint are removed and never enter the rerank stage.
"""

from __future__ import annotations

from typing import Any

import structlog

from models.schemas import Course, HardConstraints

logger = structlog.get_logger()

# Ordered mappings for upper-limit comparisons
_DIFFICULTY_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2,
                                      "\u4f4e": 0, "\u4e2d": 1, "\u9ad8": 2}
_WORKLOAD_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2,
                                    "\u5c11": 0, "\u4f4e": 0, "\u4e2d": 1, "\u591a": 2, "\u9ad8": 2}

# Warn when passing courses drop below this count
_SPARSE_THRESHOLD = 3


def has_active_constraints(hc: HardConstraints) -> bool:
    """Return True if any hard constraint field carries a meaningful value."""
    return bool(
        hc.campus
        or hc.avoid_time_slots
        or hc.categories
        or hc.teacher
        or hc.no_exam
        or hc.no_group_work
        or hc.max_difficulty
        or hc.max_workload
    )


class HardConstraintFilter:
    """Phase 1.5 deterministic hard constraint filter.

    Single responsibility: accepts a candidate course list and a HardConstraints object,
    returns three groups - passing courses, filtered-out records, and sparse warnings.
    No LLM calls, no network I/O - pure in-memory synchronous logic.
    """

    def filter(
        self,
        courses: list[Course],
        hc: HardConstraints,
    ) -> tuple[list[Course], list[dict[str, Any]], list[dict[str, Any]]]:
        """Apply hard constraint filtering.

        Returns:
            passing:      courses that pass all hard constraints (original order preserved)
            filtered_out: records of rejected courses (course_id / course_name / violations)
            warnings:     sparsity warnings when too few courses remain after filtering
        """
        passing: list[Course] = []
        filtered_out: list[dict[str, Any]] = []

        for course in courses:
            violations = self._check_violations(course, hc)
            if violations:
                filtered_out.append(
                    {
                        "course_id": course.course_id,
                        "course_name": course.course_name,
                        "violations": violations,
                    }
                )
            else:
                passing.append(course)

        warnings = self._build_sparse_warnings(passing, filtered_out)

        logger.info(
            "hard_constraint_filter.done",
            total_input=len(courses),
            passing=len(passing),
            filtered_out=len(filtered_out),
            active_constraints=self._active_constraint_summary(hc),
        )

        return passing, filtered_out, warnings

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_violations(course: Course, hc: HardConstraints) -> list[str]:
        """Return a list of violation descriptions; empty list means the course passes."""
        violations: list[str] = []

        if hc.campus and course.campus not in hc.campus:
            required = "/".join(hc.campus)
            actual = course.campus or "unknown"
            violations.append(
                f"\u6821\u533a\u4e0d\u7b26\uff08\u8bfe\u7a0b\u5728{actual}\uff0c\u8981\u6c42{required}\uff09"
            )

        if hc.categories:
            category_match = any(
                HardConstraintFilter._fuzzy_text_match(required, course.course_category)
                or HardConstraintFilter._fuzzy_text_match(required, course.domain)
                for required in hc.categories
            )
            if not category_match:
                required = "/".join(hc.categories)
                actual = f"{course.course_category or 'unknown'}(分类)/{course.domain or 'unknown'}(领域)"
                violations.append(
                    f"课程分类/领域不符（{actual}，要求{required}）"
                )

        if hc.teacher and hc.teacher not in course.teacher:
            actual = course.teacher or "unknown"
            violations.append(
                f"\u8001\u5e08\u4e0d\u7b26\uff08{actual}\uff0c\u8981\u6c42\u5305\u542b[{hc.teacher}]\uff09"
            )

        if hc.no_exam and course.has_exam == 1:
            violations.append(
                "\u8be5\u8bfe\u7a0b\u6709\u8003\u8bd5\uff0c\u4e0e\u4e0d\u8003\u8bd5\u8981\u6c42\u51b2\u7a81"
            )

        if hc.no_group_work and course.group_work_required == 1:
            violations.append(
                "\u8be5\u8bfe\u7a0b\u6709\u5c0f\u7ec4\u4f5c\u4e1a\uff0c\u4e0e\u4e0d\u5c0f\u7ec4\u8981\u6c42\u51b2\u7a81"
            )

        for avoid in hc.avoid_time_slots:
            if avoid and avoid in course.time_slot:
                violations.append(
                    f"\u4e0a\u8bfe\u65f6\u95f4\u51b2\u7a81\uff08\u65f6\u95f4\u6bb5\u5305\u542b[{avoid}]\uff09"
                )

        if hc.max_difficulty and course.difficulty:
            limit = _DIFFICULTY_ORDER.get(hc.max_difficulty)
            actual = _DIFFICULTY_ORDER.get(course.difficulty)
            if limit is not None and actual is not None and actual > limit:
                violations.append(
                    f"\u96be\u5ea6\u8d85\u51fa\u4e0a\u9650\uff08{course.difficulty} > {hc.max_difficulty}\uff09"
                )

        if hc.max_workload and course.workload:
            limit = _WORKLOAD_ORDER.get(hc.max_workload)
            actual = _WORKLOAD_ORDER.get(course.workload)
            if limit is not None and actual is not None and actual > limit:
                violations.append(
                    f"\u4f5c\u4e1a\u91cf\u8d85\u51fa\u4e0a\u9650\uff08{course.workload} > {hc.max_workload}\uff09"
                )

        return violations

    @staticmethod
    def _build_sparse_warnings(
        passing: list[Course],
        filtered_out: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        warnings: list[dict[str, Any]] = []

        if not filtered_out:
            return warnings

        if not passing:
            warnings.append(
                {
                    "type": "hard_constraint_no_match",
                    "level": "high",
                    "message": (
                        f"\u6ca1\u6709\u8bfe\u7a0b\u540c\u65f6\u6ee1\u8db3\u6240\u6709\u786c\u6027\u8981\u6c42"
                        f"\uff08\u5df2\u8fc7\u6ee4 {len(filtered_out)} \u95e8\uff09\uff0c"
                        "\u5efa\u8bae\u9002\u5f53\u653e\u5bbd\u9009\u8bfe\u6761\u4ef6\u540e\u91cd\u65b0\u5c1d\u8bd5\u3002"
                    ),
                    "filtered_count": len(filtered_out),
                }
            )
        elif len(passing) < _SPARSE_THRESHOLD:
            warnings.append(
                {
                    "type": "hard_constraint_sparse",
                    "level": "medium",
                    "message": (
                        f"\u6839\u636e\u60a8\u7684\u786c\u6027\u8981\u6c42\u8fc7\u6ee4\u540e\uff0c"
                        f"\u7b26\u5408\u6761\u4ef6\u7684\u8bfe\u7a0b\u4ec5\u5269 {len(passing)} \u95e8"
                        f"\uff08\u5df2\u8fc7\u6ee4 {len(filtered_out)} \u95e8\uff09\uff0c"
                        "\u5efa\u8bae\u9002\u5f53\u8c03\u6574\u9009\u8bfe\u6761\u4ef6\u4ee5\u83b7\u5f97\u66f4\u591a\u9009\u62e9\u3002"
                    ),
                    "passing_count": len(passing),
                    "filtered_count": len(filtered_out),
                }
            )

        return warnings

    @staticmethod
    def _fuzzy_text_match(required: str, actual: str) -> bool:
        required_text = (required or "").strip()
        actual_text = (actual or "").strip()
        if not required_text or not actual_text:
            return False
        if required_text == actual_text:
            return True

        # 类别别名映射：用户口语化描述 → 课程正式分类名
        category_aliases = {
            "自然学科": "自然科学",
            "自然学科类": "自然科学与工程技术类",
            "自然学科": "自然科学",
            "理工": "自然科学与工程技术",
            "理工类": "自然科学与工程技术类",
            "理工科": "自然科学与工程技术类",
            "工科": "自然科学与工程技术",
            "工科类": "自然科学与工程技术类",
            "理科": "自然科学",
            "理科类": "自然科学与工程技术类",
            "文科": "人文与社会科学",
            "文科类": "人文与社会科学类",
            "社科": "人文与社会科学",
            "社科类": "人文与社会科学类",
        }

        # 先尝试别名映射后精确匹配
        alias_required = category_aliases.get(required_text, required_text)
        alias_actual = category_aliases.get(actual_text, actual_text)
        if alias_required == alias_actual:
            return True
        if alias_required in alias_actual or alias_actual in alias_required:
            return True

        required_core = required_text.replace("类", "")
        actual_core = actual_text.replace("类", "")
        return (
            required_core in actual_core
            or actual_core in required_core
            or required_text in actual_text
            or actual_text in required_text
        )

    @staticmethod
    def _active_constraint_summary(hc: HardConstraints) -> dict[str, Any]:
        return {
            "campus": hc.campus,
            "avoid_time_slots": hc.avoid_time_slots,
            "categories": hc.categories,
            "teacher": hc.teacher or None,
            "no_exam": hc.no_exam,
            "no_group_work": hc.no_group_work,
            "max_difficulty": hc.max_difficulty,
            "max_workload": hc.max_workload,
        }
