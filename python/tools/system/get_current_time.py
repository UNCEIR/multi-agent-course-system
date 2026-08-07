# -*- coding: utf-8 -*-
"""获取当前日期和时间。

供 agent 获取当前时间戳，用于记录操作时间、上下文感知等。
"""

from __future__ import annotations

from datetime import datetime

from langchain_core.tools import tool


@tool
def get_current_time() -> str:
    """获取当前日期和时间。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")