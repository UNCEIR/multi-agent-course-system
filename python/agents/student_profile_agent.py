from __future__ import annotations

import json
from typing import Any
import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from config import get_settings
from models.schemas import HardConstraints, StudentProfile, StudentProfileResult
from services import LLMTaskName, build_chat_openai

from .base_agent import BaseAgent


logger = structlog.get_logger()

SYSTEM_PROMPT = """你是教务系统里的公选课学生画像分析专家。
请根据学生输入的自然语言需求和结构化上下文，抽取适合公选课推荐的画像。

## 重要：硬约束与软约束的区别

【天然硬约束】——学生只要提及具体值就填入 hard_constraints，不需要"只/必须"等强调词：
- campus: 提到任何具体校区（如"东校区""西校区"）
- avoid_time_slots: 提到任何需要避开的时间（如"周五""下午没空"）
- categories: 提到任何具体课程类型/分类（如"工程技术类""体育健康类"）
- teacher: 提到任何老师姓名（如"张三老师""我要选李老师的课"）
- no_exam: 提到不考试/没有期末/不要考核（true），否则 false

【强意图才升级为硬约束】——仅当学生使用"只要/必须/一定/绝对/不能/坚决"等强调词时才填：
- no_group_work: 坚决不要小组作业时为 true
- max_difficulty: 只要低/中难度时填"低"或"中"
- max_workload: 只要作业量少/中时填"少"或"中"

其余软约束（interests/preferred_domains/difficulty_preference等）按偏好正常填写，只影响排序不影响过滤。

输出JSON格式（只输出JSON，不要其他内容）:
{
  "hard_constraints": {
    "campus": [],
    "avoid_time_slots": [],
    "categories": [],
    "teacher": "",
    "no_exam": false,
    "no_group_work": false,
    "max_difficulty": null,
    "max_workload": null
  },
  "interests": ["兴趣关键词"],
  "preferred_domains": ["人文艺术"|"自然环境"|"工程技术"|"创新创业"|"体育健康"|"社会科学"],
  "preferred_categories": ["课程分类"],
  "preferred_campus": ["校区"],
  "preferred_time_slots": ["偏好上课时间"],
  "avoid_time_slots": ["需要避开的时间"],
  "difficulty_preference": "低|中|高|不限",
  "workload_preference": "少|中|多|不限",
  "grade_friendly_preference": "高|中|不限",
  "exam_preference": "不考试|可考试|不限",
  "group_work_preference": "不小组|可小组|不限",
  "grade": "大一|大二|大三|大四|研(可选，学生未提则为空字符串)",
  "department": "学院名称(可选，学生未提则为空字符串)",
  "constraints": ["其他硬性约束描述"],
  "real_time_tags": {"画像摘要": "..."}
}"""


class StudentProfileAgent(BaseAgent):
    def __init__(self):
        settings = get_settings()
        super().__init__(
            name="student_profile",
            timeout=settings.agent_timeout_user_profile,
        )
        self.llm = build_chat_openai(temperature=0.2, max_tokens=2048, task_name=LLMTaskName.STUDENT_PROFILE)

    async def _execute(self, **kwargs: Any) -> StudentProfileResult:
        student_id: str = kwargs["user_id"]
        prompt: str = kwargs.get("prompt", "")
        context: dict[str, Any] = kwargs.get("context", {})
        profile = await self._analyze_profile(student_id, prompt, context)
        domains = profile.preferred_domains or ["none"]
        campus = profile.preferred_campus or ["none"]
        has_hard = bool(profile.hard_constraints and (
            profile.hard_constraints.campus
            or profile.hard_constraints.categories
            or profile.hard_constraints.no_exam
            or profile.hard_constraints.teacher
        ))
        logger.info(
            "student_profile.done",
            student_id=student_id,
            domains=domains,
            campus=campus,
            hard_constraints=has_hard,
            prompt=prompt,
        )
        return StudentProfileResult(
            success=True,
            profile=profile,
            data={"raw_prompt": prompt, "context": context},
            confidence=0.88,
        )

    async def _analyze_profile(
        self, student_id: str, prompt: str, context: dict[str, Any]
    ) -> StudentProfile:
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"学生ID: {student_id}\n"
                    f"学生需求: {prompt}\n"
                    f"结构化上下文: {json.dumps(context, ensure_ascii=False)}"
                )
            ),
        ]
        response = await self.llm.ainvoke(messages)
        data = self._parse_json(response.content)
        if not data:
            logger.warning("student_profile.llm_fallback", student_id=student_id)
            data = self._heuristic_profile(prompt, context)
        hard_constraints = self._parse_hard_constraints(data, prompt, context)
        return StudentProfile(
            student_id=student_id,
            raw_prompt=prompt,
            interests=self._list(data, "interests"),
            preferred_domains=self._list(data, "preferred_domains", context.get("preferred_domains")),
            preferred_categories=self._list(data, "preferred_categories", context.get("preferred_categories")),
            preferred_campus=self._list(data, "preferred_campus", context.get("campus")),
            preferred_time_slots=self._list(data, "preferred_time_slots", context.get("preferred_time_slots")),
            avoid_time_slots=self._list(data, "avoid_time_slots", context.get("avoid_time_slots")),
            difficulty_preference=str(data.get("difficulty_preference") or context.get("difficulty_preference") or ""),
            workload_preference=str(data.get("workload_preference") or context.get("workload_preference") or ""),
            grade_friendly_preference=str(data.get("grade_friendly_preference") or context.get("grade_friendly_preference") or ""),
            exam_preference=str(data.get("exam_preference") or context.get("exam_preference") or ""),
            group_work_preference=str(data.get("group_work_preference") or context.get("group_work_preference") or ""),
            grade=str(data.get("grade") or context.get("grade") or ""),
            department=str(data.get("department") or context.get("department") or ""),
            constraints=self._list(data, "constraints"),
            real_time_tags=data.get("real_time_tags", {}),
            hard_constraints=hard_constraints,
        )

    def _parse_hard_constraints(
        self, data: dict[str, Any], prompt: str, context: dict[str, Any]
    ) -> HardConstraints:
        hc_raw = data.get("hard_constraints") or {}
        if not isinstance(hc_raw, dict):
            hc_raw = {}

        campus = self._list(hc_raw, "campus")
        avoid_time_slots = self._list(hc_raw, "avoid_time_slots")
        categories = self._list(hc_raw, "categories")
        teacher = str(hc_raw.get("teacher") or "").strip()
        no_exam = bool(hc_raw.get("no_exam", False))
        no_group_work = bool(hc_raw.get("no_group_work", False))
        max_difficulty = hc_raw.get("max_difficulty") or None
        max_workload = hc_raw.get("max_workload") or None

        # Merge context-level hard constraints (API 调用方可直接传入)
        if not campus and context.get("hard_campus"):
            campus = self._list(context, "hard_campus")
        if not avoid_time_slots and context.get("hard_avoid_time_slots"):
            avoid_time_slots = self._list(context, "hard_avoid_time_slots")
        prompt_hard = self._extract_prompt_hard_constraints(prompt)
        if prompt_hard["campus"]:
            campus = self._merge_unique(campus, prompt_hard["campus"])
        if prompt_hard["categories"]:
            categories = self._merge_unique(categories, prompt_hard["categories"])
        if prompt_hard["no_exam"]:
            no_exam = True
        return HardConstraints(
            campus=campus,
            avoid_time_slots=avoid_time_slots,
            categories=categories,
            teacher=teacher,
            no_exam=no_exam,
            no_group_work=no_group_work,
            max_difficulty=max_difficulty if isinstance(max_difficulty, str) else None,
            max_workload=max_workload if isinstance(max_workload, str) else None,
        )

    def _extract_prompt_hard_constraints(self, prompt: str) -> dict[str, Any]:
        normalized = prompt or ""
        campus = []
        for campus_name in ["东校区", "南校区", "北校区", "西校区", "主校区"]:
            if campus_name in normalized:
                campus.append(campus_name)

        categories: list[str] = []
        category_rules = {
            "自然科学": "自然科学与工程技术类",
            "工程技术": "自然科学与工程技术类",
            "理工类": "自然科学与工程技术类",
            "理工科": "自然科学与工程技术类",
            "工科类": "自然科学与工程技术类",
            "理科类": "自然科学与工程技术类",
            "理工": "自然科学与工程技术类",
            "工科": "自然科学与工程技术类",
            "人文": "人文与社会科学类",
            "社会科学": "人文与社会科学类",
            "心理": "人文与社会科学类",
            "文科类": "人文与社会科学类",
            "社科类": "人文与社会科学类",
            "文科": "人文与社会科学类",
            "社科": "人文与社会科学类",
        }
        for keyword, category in category_rules.items():
            if keyword in normalized and category not in categories:
                categories.append(category)

        no_exam = any(
            keyword in normalized
            for keyword in ["不考试", "不要考试", "没有考试", "没有期末", "无考试", "免考试"]
        )
        return {
            "campus": campus,
            "categories": categories,
            "no_exam": no_exam,
        }

    @staticmethod
    def _merge_unique(base: list[str], incoming: list[str]) -> list[str]:
        merged = list(base)
        for item in incoming:
            if item and item not in merged:
                merged.append(item)
        return merged

    def _parse_json(self, raw: str) -> dict[str, Any]:
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(cleaned)
        except (json.JSONDecodeError, IndexError):
            return {}

    def _heuristic_profile(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        data: dict[str, Any] = {
            "interests": [],
            "preferred_domains": [],
            "preferred_campus": [],
            "avoid_time_slots": [],
            "constraints": [],
            "hard_constraints": {
                "campus": [],
                "avoid_time_slots": [],
                "categories": [],
                "teacher": "",
                "no_exam": False,
                "no_group_work": False,
                "max_difficulty": None,
                "max_workload": None,
            },
        }
        keyword_domains = {
            "艺术": "人文艺术",
            "文学": "人文艺术",
            "历史": "人文艺术",
            "电影": "人文艺术",
            "环境": "自然环境",
            "生态": "自然环境",
            "科技": "工程技术",
            "工程": "工程技术",
            "创业": "创新创业",
            "心理": "社会科学",
            "体育": "体育健康",
        }
        for keyword, domain in keyword_domains.items():
            if keyword in prompt:
                data["interests"].append(keyword)
                data["preferred_domains"].append(domain)

        hc = data["hard_constraints"]
        for campus in ["东校区", "南校区", "北校区", "西校区"]:
            if campus in prompt:
                data["preferred_campus"].append(campus)
                hc["campus"].append(campus)

        if "不考试" in prompt or "不要考试" in prompt or "没有考试" in prompt or "没有期末" in prompt:
            data["exam_preference"] = "不考试"
            hc["no_exam"] = True

        strong_intent = any(word in prompt for word in ["只要", "必须", "一定", "绝对", "不能", "坚决"])
        if strong_intent and ("不小组" in prompt or ("小组" in prompt and ("不要" in prompt or "不想" in prompt))):
            hc["no_group_work"] = True
        elif "小组" in prompt and ("不要" in prompt or "不想" in prompt):
            data["group_work_preference"] = "不小组"

        if "作业少" in prompt or "轻松" in prompt:
            data["workload_preference"] = "少"
        if "给分" in prompt or "绩点" in prompt:
            data["grade_friendly_preference"] = "高"
        for grade_kw in ["大一", "大二", "大三", "大四", "研一", "研二", "研三"]:
            if grade_kw in prompt:
                data["grade"] = grade_kw
                break
        for dept_kw in ["计算机", "信息", "软件", "电子", "机械", "土木", "化工", "材料",
                         "经管", "管理", "经济", "金融", "外语", "文学", "法学", "艺术",
                         "医学", "数学", "物理", "化学", "生物", "环境", "建筑", "设计"]:
            if dept_kw in prompt:
                data["department"] = dept_kw + "学院"
                break
        data.update({key: value for key, value in context.items() if key not in data})
        return data

    @staticmethod
    def _list(data: dict[str, Any], key: str, fallback: Any = None) -> list[str]:
        value = data.get(key, fallback)
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [value]
        return [str(item) for item in value if str(item).strip()]
