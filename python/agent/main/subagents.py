# -*- coding: utf-8 -*-
"""Subagent 工厂占位 — Phase 2/3 实装后替换为真实实现。

当前返回 stub + NotImplementedError，保持主 agent 可编译。
"""

from __future__ import annotations

from typing import Any


def build_report_subagent() -> Any:
    """成绩统计报告 subagent — Phase 2 实装。

    功能：批量 Excel → 单科 JSON → 学生 JSON → 加权复合统计 → HTML→PDF。
    """
    raise NotImplementedError("build_report_subagent: Phase 2 实装")


def build_evaluation_agent() -> Any:
    """评价寄语 subagent — Phase 2 实装。

    功能：studentList JSON → comment_type 四种驱动 → LLM 生成 comment。
    """
    raise NotImplementedError("build_evaluation_agent: Phase 2 实装")


def build_ppt_agent() -> Any:
    """PPT 生成 subagent — Phase 3 实装。

    功能：参考 OpenMAIC，DSL→PPTX 渲染管线。
    """
    raise NotImplementedError("build_ppt_agent: Phase 3 实装")