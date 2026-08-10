# -*- coding: utf-8 -*-
"""业务 Agent 的声明式配置。"""

from __future__ import annotations

from dataclasses import dataclass

from ai.llm_task_name import LLMTaskName

from .prompt import MAIN_AGENT_SYSTEM_PROMPT


@dataclass(frozen=True)
class AgentSpec:
    """描述一个业务 Agent 如何加载上下文和能力。"""

    name: str
    task_name: LLMTaskName
    system_prompt: str
    skills: tuple[str, ...] = ("/skills/",)
    memory: tuple[str, ...] = ("/memories/AGENTS.md",)
    allowed_tools: tuple[str, ...] = ()
    temperature: float = 0.1
    max_tokens: int = 2048
    enable_compaction: bool = True
    streaming: bool = True


MAIN_AGENT_SPEC = AgentSpec(
    name="main_agent",
    task_name=LLMTaskName.MAIN_AGENT_ROUTER,
    system_prompt=MAIN_AGENT_SYSTEM_PROMPT,
    # 主 agent 只暴露已实装且面向对话的工具。
    # 推荐原子工具（extract_profile 等 7 个）不暴露，避免它逐个串行调用变慢；
    # 推荐统一走 recommend_courses 一键工具（mode=pipeline，内部并行）。
    # streaming=True：让 /chat/stream 能透出 on_chat_model_stream token 事件；
    # 否则 deepagents 按 stream_mode="updates" 聚合，stream 端点只能拿到空 reply。
    streaming=True,
    allowed_tools=(
        "list_available_skills",
        "get_current_time",
        "recommend_courses",
        "query_knowledge",
        "parse_document",
        "chunk_document",
        "writing_assistant",
        "web_search",
        "image_generate",
        "code_interpreter",
        "mindmap_generator",
        "compute_weighted_grade",
        
    ),
)
RECOMMENDATION_AGENT_SPEC = AgentSpec(
    name="recommendation_agent",
    task_name=LLMTaskName.RECOMMEND_COURSES_TOOL,
    system_prompt=(
        "你是公选课推荐 Agent。只根据用户偏好和推荐工具返回的课程事实进行推荐，"
        "硬约束必须先满足，不能用主观排序绕过硬约束。"
    ),
    skills=("/skills/recommend-courses/",),
    memory=(),
    allowed_tools=("recommend_courses",),
)

REPORT_AGENT_SPEC = AgentSpec(
    name="report_agent",
    task_name=LLMTaskName.TRANSCRIPT_PARSER,
    system_prompt=(
        "你是学生成绩报告 Agent。只处理成绩数据分析和报告解释；"
        "数值统计必须交给确定性工具，不要凭语言模型心算。"
    ),
    skills=("/skills/report-generation/",),
    memory=(),
    allowed_tools=("compute_weighted_grade",),
)

EVALUATION_AGENT_SPEC = AgentSpec(
    name="evaluation_agent",
    task_name=LLMTaskName.EVALUATION_GENERATOR,
    system_prompt=(
        "你是学生评价寄语 Agent。根据结构化成绩和评价类型生成有依据的寄语，"
        "不得编造输入中不存在的成绩或经历。"
    ),
    skills=("/skills/evaluation-writing/",),
    memory=(),
)

PPT_AGENT_SPEC = AgentSpec(
    name="ppt_agent",
    task_name=LLMTaskName.MAIN_AGENT_ROUTER,
    system_prompt=(
        "你是课程小组 PPT 规划 Agent。先把用户需求整理为课件结构，"
        "只使用当前已注册的能力，不声称已经生成尚未实现的文件。"
    ),
    skills=("/skills/ppt-generation/",),
    memory=(),
)
