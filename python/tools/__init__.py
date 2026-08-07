# -*- coding: utf-8 -*-
"""v2 工具实现包 — 原子能力目录。

tools/ 放原子能力（解析、分块、向量化、渲染、搜索、插件），
以 @tool 装饰器 + Pydantic args_schema 暴露，通过 ToolRegistry 统一注册。

分层（按功能域子包组织）：
  - tools/           — 注册层（ToolRegistry/CircuitBreaker/MCPClient）
  - tools/system/    — 系统级工具（get_current_time, list_available_skills）
  - tools/chat/      — 对话工具（writing_assistant, web_search）
  - tools/documents/ — 文档解析 + 分块
  - tools/recommend/ — 推荐工具
  - tools/image/     — 图片生成
  - tools/code/      — 代码执行
  - tools/mindmap/   — 脑图生成
  - tools/report/    — 报告统计

与 skills/ 的区别：
  - tools/ = Python @tool 代码，原子能力，ToolRegistry 注册
  - skills/ = SKILL.md 文档，技能说明，SkillsMiddleware 注入 system prompt

架构决策：
  - 每个工具一个文件，通过子包 __init__.py 逐级导出，最终统一到 tools/__init__.py
  - 工具用 @tool 装饰器 + Pydantic args_schema，LangChain 自动生成 JSON Schema
  - 注册走 ToolRegistry（tools/registry.py），不直接 import
"""

from __future__ import annotations

# ── 工具注册层 ────────────────────────────────────────────────────────
from .circuit_breaker import CircuitBreaker
from .mcp_client import MultiServerMCPClient, get_mcp_client
from .registry import ToolRegistry, get_registry

# ── 功能域子包（工具逐级导出） ─────────────────────────────────────────
from .system import get_current_time, list_available_skills
from .chat import web_search, writing_assistant
from .documents import chunk_document, parse_document
from .recommend import recommend_courses
from .image import image_generate
from .code import code_interpreter
from .mindmap import mindmap_generator
from .report import compute_weighted_grade

# ── 公开 API ──────────────────────────────────────────────────────────
__all__ = [
    # 注册层
    "ToolRegistry",
    "get_registry",
    "CircuitBreaker",
    "MultiServerMCPClient",
    "get_mcp_client",
    # 工具
    "get_current_time",
    "list_available_skills",
    "writing_assistant",
    "web_search",
    "parse_document",
    "chunk_document",
    "recommend_courses",
    "image_generate",
    "code_interpreter",
    "mindmap_generator",
    "compute_weighted_grade",
]