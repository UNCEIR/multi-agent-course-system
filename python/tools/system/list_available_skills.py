# -*- coding: utf-8 -*-
"""列出当前可用的所有技能。

由 SkillsMiddleware 自动注入 skills_metadata 到 state，
agent 可通过 state["skills_metadata"] 读取。
此 tool 让 agent 显式查询 skill 列表。
"""

from __future__ import annotations

from langchain_core.tools import tool


@tool
def list_available_skills() -> str:
    """列出当前可用的所有技能（skills_metadata 中的 skill 名称与描述）。"""
    return "请查看系统提示中的技能列表（SkillsMiddleware 已注入到 system message）。"