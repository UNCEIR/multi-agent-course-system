"""
ReAct tool wrappers for Supervisor orchestration.

Each tool wraps an existing Agent as a callable function with a typed parameter schema,
making them usable via LLM tool/function calling.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from models.schemas import Course, StudentProfile


class HardConstraintArgs(BaseModel):
    """Parameters for filter_hard_constraints tool. This tool is MANDATORY."""
    courses: list[str] = Field(description="List of course IDs to apply hard constraint filtering to")


class SearchCoursesArgs(BaseModel):
    """Parameters for search_courses tool."""
    strategy: Literal["wide", "refined"] = Field(
        description="'wide' for broad vector search, 'refined' for profile-aware structured search"
    )


class RerankCoursesArgs(BaseModel):
    """Parameters for rerank_courses tool."""
    courses: list[str] = Field(description="List of course IDs to rerank")
    num_items: int = Field(default=10, description="Number of courses to return")


class CheckFeasibilityArgs(BaseModel):
    """Parameters for check_feasibility tool."""
    courses: list[str] = Field(description="List of course IDs to check feasibility for")


class GenerateReasonsArgs(BaseModel):
    """Parameters for generate_reasons tool."""
    courses: list[str] = Field(description="List of course IDs to generate reasons for")


class SemanticFilterArgs(BaseModel):
    """Parameters for semantic_filter_courses tool."""
    courses: list[str] = Field(description="List of course IDs to filter semantically")
    target_count: int = Field(default=40, description="Target number of courses to keep")


# Tool definitions for bind_tools
REACT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "extract_profile",
            "description": "Extract structured student profile from natural language需求. Call this first.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_courses",
            "description": "Recall candidate courses. Use 'wide' for broad search, 'refined' when profile has specific constraints.",
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy": {
                        "type": "string",
                        "enum": ["wide", "refined"],
                        "description": "Search strategy: wide=vector search only, refined=structured query",
                    }
                },
                "required": ["strategy"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "filter_hard_constraints",
            "description": "MANDATORY: Apply hard constraint filtering (campus, category, time, teacher, exam requirements). Remove violating courses. Must be called before reranking.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "semantic_filter_courses",
            "description": "Optional: Use LLM to pick the most semantically relevant courses from candidates, reducing the candidate pool for reranking.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rerank_courses",
            "description": "Rerank courses based on student profile. Returns ordered list of course IDs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "num_items": {
                        "type": "integer",
                        "description": "Number of courses to return",
                        "default": 10,
                    }
                },
                "required": ["num_items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_feasibility",
            "description": "Check enrollment capacity, time conflicts, and grade priority for courses. Returns warnings and availability.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_reasons",
            "description": "Generate personalized recommendation reasons for the final course list.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


class ReactState:
    """Mutable state carried across ReAct rounds."""

    def __init__(self):
        self.profile: StudentProfile | None = None
        self.courses: list[Course] = []
        self.priority_advice: dict[str, Any] = {}
        self.reasons: list[dict[str, str]] = []
        self.warnings: list[dict[str, Any]] = []
        self.hard_filtered: bool = False
        self.profile_extracted: bool = False
        self.recall_done: bool = False
        self.rerank_done: bool = False
        self.feasibility_done: bool = False
        self.reasons_done: bool = False


class ReactToolExecutor:
    """Executes ReAct tool calls against the real Agent implementations."""

    def __init__(
        self,
        supervisor,
        prompt: str,
        context: dict[str, Any],
        num_items: int,
        user_id: str,
    ):
        self.supervisor = supervisor
        self.prompt = prompt
        self.context = context
        self.num_items = num_items
        self.user_id = user_id
        self.state = ReactState()

    async def execute_tool(self, tool_name: str, tool_args: dict[str, Any]) -> str:
        method = getattr(self, f"_tool_{tool_name}", None)
        if not method:
            return f"Unknown tool: {tool_name}"
        # 防重复工具：已完成的关键步骤直接跳过，避免重复召回/重复重排
        already_done = {
            "search_courses": self.state.recall_done,
            "filter_hard_constraints": self.state.hard_filtered,
            "rerank_courses": self.state.rerank_done,
            "check_feasibility": self.state.feasibility_done,
            "generate_reasons": self.state.reasons_done,
            "extract_profile": self.state.profile_extracted,
        }
        if already_done.get(tool_name) and tool_name != "search_courses":
            return f"Tool {tool_name} already executed, skipping."
        if tool_name == "search_courses":
            # search_courses 允许 wide/refined 两次（不同策略），但同策略不重复
            strategy = (tool_args or {}).get("strategy", "wide")
            if strategy == "refined" and not self.state.profile_extracted:
                return "Search(wide) already executed; refined requires profile first."
        try:
            result = await method(**tool_args)
            return result
        except Exception as exc:
            return f"Tool {tool_name} failed: {exc}"

    async def _tool_extract_profile(self) -> str:
        result = await self.supervisor.student_profile_agent.run(
            user_id=self.user_id,
            prompt=self.prompt,
            context=self.context,
        )
        profile = getattr(result, "profile", None)
        if profile:
            self.state.profile = profile
            self.state.profile_extracted = True
            return (
                f"Profile extracted: grade={profile.grade}, "
                f"interests={profile.interests}, "
                f"domains={profile.preferred_domains}, "
                f"campus={profile.preferred_campus}, "
                f"exam_preference={profile.exam_preference}, "
                f"hard_constraints={{campus: {profile.hard_constraints.campus}, "
                f"categories: {profile.hard_constraints.categories}, "
                f"no_exam: {profile.hard_constraints.no_exam}}}"
            )
        return "Profile extraction failed, no profile returned."

    async def _tool_search_courses(self, strategy: str = "wide") -> str:
        sp = self.state.profile if strategy == "refined" else None
        result = await self.supervisor.course_recall_agent.run(
            student_profile=sp,
            prompt=self.prompt,
            context=self.context,
            num_items=self.num_items * 2,
        )
        courses = getattr(result, "courses", [])
        if courses:
            self.state.courses.extend(courses)
            self.state.recall_done = True
            domains = set(c.domain for c in courses)
            return f"Search ({strategy}) returned {len(courses)} courses. Domains: {domains}"
        return f"Search ({strategy}) returned 0 courses."

    async def _tool_filter_hard_constraints(self) -> str:
        if not self.state.profile or not self.state.courses:
            return "No profile or courses to filter."
        from agent.recommend.hard_constraint_filter import has_active_constraints

        if not has_active_constraints(self.state.profile.hard_constraints):
            self.state.hard_filtered = True
            return "No active hard constraints to apply. All courses pass."
        filtered, hc_filtered, hc_warnings = self.supervisor.hard_constraint_filter.filter(
            self.state.courses, self.state.profile.hard_constraints
        )
        self.state.warnings.extend(hc_warnings)
        removed_count = len(self.state.courses) - len(filtered)
        self.state.courses = filtered
        self.state.hard_filtered = True
        return f"Hard constraint filter: removed {removed_count} courses, {len(filtered)} remain."

    async def _tool_semantic_filter_courses(self) -> str:
        if not self.state.profile or not self.state.courses:
            return "No profile or courses to filter semantically."
        filtered = await self.supervisor._llm_semantic_filter(
            self.state.courses, self.state.profile, target_count=40
        )
        if filtered:
            self.state.courses = filtered
            return f"Semantic filter: narrowed from {len(self.state.courses)} to {len(filtered)} courses."
        return "Semantic filter skipped (not needed or failed)."

    async def _tool_rerank_courses(self, num_items: int = 10) -> str:
        if not self.state.courses:
            return "No courses to rerank."
        result = await self.supervisor.course_rerank_agent.run(
            student_profile=self.state.profile,
            candidates=self.state.courses,
            num_items=num_items,
        )
        ranked = getattr(result, "courses", [])
        if not ranked:
            ranked = self.state.courses
        self.state.courses = ranked
        self.state.rerank_done = True
        names = [c.course_name for c in ranked[:5]]
        return f"Reranked {len(ranked)} courses. Top 5: {names}"

    async def _tool_check_feasibility(self) -> str:
        if not self.state.courses:
            return "No courses to check feasibility."
        result = await self.supervisor.course_feasibility_agent.run(
            student_profile=self.state.profile,
            courses=self.state.courses,
            context=self.context,
        )
        available_ids = set(getattr(result, "available_courses", []))
        w = getattr(result, "selection_warnings", [])
        pa = getattr(result, "priority_advice", {})
        self.state.warnings.extend(w)
        self.state.priority_advice = pa
        self.state.feasibility_done = True
        self.state.courses = [c for c in self.state.courses if c.course_id in available_ids]
        return (
            f"Feasibility check: {len(available_ids)} available, "
            f"{len(self.state.courses)} after filtering, {len(w)} warnings."
        )

    async def _tool_generate_reasons(self) -> str:
        if not self.state.courses:
            return "No courses to generate reasons."
        result = await self.supervisor.recommendation_reason_agent.run(
            student_profile=self.state.profile,
            courses=self.state.courses,
            warnings=self.state.warnings,
        )
        reasons = getattr(result, "reasons", [])
        self.state.reasons = reasons
        self.state.reasons_done = True
        return f"Generated {len(reasons)} recommendation reasons."

    async def execute_rerank_on_snapshot(self, courses: list, num_items: int = 10) -> dict:
        """B 组并行：在快照上执行重排，不写共享 state.courses。

        Returns: {"course_ids": [...], "strategy": str}
        """
        result = await self.supervisor.course_rerank_agent.run(
            student_profile=self.state.profile,
            candidates=courses,
            num_items=num_items,
        )
        ranked = getattr(result, "courses", courses) or courses
        return {
            "course_ids": [c.course_id for c in ranked],
            "strategy": getattr(result, "rerank_strategy", ""),
        }

    async def execute_feasibility_on_snapshot(self, courses: list) -> dict:
        """B 组并行：在快照上做可行性检查，不写共享 state.courses。

        Returns: {"available_ids": [...], "warnings": [...], "priority_advice": {...}}
        """
        result = await self.supervisor.course_feasibility_agent.run(
            student_profile=self.state.profile,
            courses=courses,
            context=self.context,
        )
        return {
            "available_ids": list(getattr(result, "available_courses", [])),
            "warnings": getattr(result, "selection_warnings", []),
            "priority_advice": getattr(result, "priority_advice", {}),
        }
