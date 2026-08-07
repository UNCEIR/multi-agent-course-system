# -*- coding: utf-8 -*-
"""对话工具 — 主 agent 对话框中调用的通用能力。

- writing_assistant: Phase 1 (stub — NotImplementedError)
- web_search: Phase 3 (stub — NotImplementedError)
"""

from __future__ import annotations

from .web_search import web_search
from .writing_assistant import writing_assistant

__all__ = [
    "web_search",
    "writing_assistant",
]