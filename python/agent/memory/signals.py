# -*- coding: utf-8 -*-
"""记忆提取的本地信号预筛（纯函数、零 IO、无依赖）。

设计：信号只决定"这一轮要不要立刻送 LLM 判一次"，绝不直接写记忆；
真正写不写仍由 memory_extract.txt + Pydantic 校验把关。宁可漏（走攒批兜底），
不可把噪声送进 LLM。

- has_retraction_signal（强改口组，始终生效）：明确推翻旧偏好/旧决定的高精度表达。
- has_disclosure_signal（弱披露组，默认关闭）：新的强个人陈述，命中率高但误报成本也高。
"""
from __future__ import annotations

import re

_RETRACTION_PATTERNS = (
    re.compile(r"不再"),
    re.compile(r"以后不(?:想|要|打算|去|打|看|学|用|吃|喝|买|选|参加|玩|考|考虑|报|做)"),
    re.compile(r"(?:改主意|改口|反悔|变卦)"),
    re.compile(r"决定不"),
    re.compile(r"不打算(?:再)?"),
    re.compile(r"(?:放弃|戒了|再也不|算了不)"),
    # 我不(再)喜欢运动了 / 我不爱打篮球了（限短距离内收尾"了"，降低误报）
    re.compile(r"不(?:喜欢|爱)[^。！？\n]{0,10}了"),
)

_DISCLOSURE_PATTERNS = (
    re.compile(r"我(?:真的|超|特别|非常|还蛮|其实)?(?:很喜欢|喜欢|爱|讨厌|不喜欢|不擅长|擅长)"),
    re.compile(r"我是(?:一名|一个|个)?(?:大学生|学生|老师|广东工业大学|大[一二三四])"),
    re.compile(r"我(?:决定|打算|计划)(?:下学期|今年|明年|以后)?"),
)


def has_retraction_signal(text: str | None) -> bool:
    """命中明确的改口/推翻旧偏好表达。"""
    if not text:
        return False
    return any(p.search(text) for p in _RETRACTION_PATTERNS)


def has_disclosure_signal(text: str | None) -> bool:
    """命中新的强个人陈述（弱组，默认由开关控制）。"""
    if not text:
        return False
    return any(p.search(text) for p in _DISCLOSURE_PATTERNS)
