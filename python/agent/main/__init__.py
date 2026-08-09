"""v2.0.0 主 Agent 工厂 — 导出 `build_main_agent`。

使用 deepagents 0.7.5 的 `create_deep_agent` 注入：
- MemoryMiddleware（长期记忆，FilesystemBackend 真实 AGENTS.md）
- SummarizationMiddleware（compaction，对齐决策 11 阈值）
- FilesystemMiddleware（大 tool result 落盘）
- SkillsMiddleware（渐进式 skill 披露）
- SqliteSaver（thread_id 跨会话恢复 checkpointer）
"""

from __future__ import annotations

from .agent import build_main_agent
from .factory import build_deep_agent
from .subagents import (
    build_evaluation_agent,
    build_ppt_agent,
    build_recommendation_agent,
    build_report_agent,
)

__all__ = [
    "build_deep_agent",
    "build_main_agent",
    "build_recommendation_agent",
    "build_report_agent",
    "build_evaluation_agent",
    "build_ppt_agent",
]
