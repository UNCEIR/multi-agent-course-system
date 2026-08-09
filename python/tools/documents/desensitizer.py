# -*- coding: utf-8 -*-
"""个人数据脱敏器 — 供成绩单/个人文档摄入管道使用。

规则：
- NFKC 归一化（PDF 抽取的 Kangxi 变体字 ⼴→广、⻩→黄）
- 姓名 → [姓名] 占位
- 学号 → 掩码（保留前后 4 位）
- 班级 → 泛化为年级
- 打印日期 → 年份
- 正则守卫：18 位身份证号、11 位手机号硬删/掩码
"""

from __future__ import annotations

import re
import unicodedata

STUDENT_ID_RE = re.compile(r"\b\d{9,12}\b")
ID_CARD_RE = re.compile(r"\b[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b")
MOBILE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
# 班级：纯中文名 + 两位年级 + 括号序号，如 信息管理与信息系统23(3)
CLASS_RE = re.compile(r"([\u4e00-\u9fa5]{2,12})(\d{2})\((\d+)\)")

# CJK 补充部首（U+2E80–2EFF）→ 标准字。NFKC 不映射这些，需手动转换，
# 否则姓名/文字含变体（如 ⻩→黄）时无法命中脱敏规则。
_RADICAL_MAP = {
    "⻩": "黄",
    "⻓": "长",
    "⻅": "见",
    "⻜": "飞",
    "⻢": "马",
    "⻋": "车",
    "⻔": "门",
    "⻕": "与",
    "⻒": "专",
    "⻞": "业",
    "⻣": "骨",
    "⻥": "鱼",
    "⻦": "鸟",
    "⻫": "齐",
    "⻭": "齿",
    "⻰": "龙",
}


def _fix_supplement_radicals(text: str) -> str:
    for radical, char in _RADICAL_MAP.items():
        text = text.replace(radical, char)
    return text


def normalize_nfkc(text: str) -> str:
    """PDF 抽取文本的 Kangxi 变体归一化。"""
    return unicodedata.normalize("NFKC", text)


def mask_student_id(text: str) -> str:
    """学号 3123003252 → 3123****52（保留前 4 后 2，中间掩码）。"""

    def _mask(match: re.Match) -> str:
        value = match.group(0)
        keep_head, keep_tail = 4, 2
        if len(value) <= keep_head + keep_tail:
            return value[:keep_head] + "*" * (len(value) - keep_head)
        return value[:keep_head] + "*" * (len(value) - keep_head - keep_tail) + value[-keep_tail:]

    return STUDENT_ID_RE.sub(_mask, text)


def mask_id_card(text: str) -> str:
    return ID_CARD_RE.sub(lambda m: m.group(0)[:6] + "*" * 8 + m.group(0)[-4:], text)


def mask_mobile(text: str) -> str:
    return MOBILE_RE.sub(lambda m: m.group(0)[:3] + "*" * 4 + m.group(0)[-4:], text)


def generalize_class(text: str) -> str:
    """班级 信息管理与信息系统23(3) → 2023级。"""

    def _replace(match: re.Match) -> str:
        year = match.group(2)
        full_year = f"20{year}" if year.startswith(("2", "3")) else f"19{year}"
        return f"{full_year}级"

    return CLASS_RE.sub(_replace, text)


def replace_name(text: str, name: str | None = None) -> str:
    """姓名替换为占位符。name 为 None 时按上下文规则处理。

    对于已知姓名（来自解析元数据），直接替换；否则依赖调用方传入。
    """
    if not name or not name.strip():
        return text
    return text.replace(name, "[姓名]")


def generalize_date(text: str) -> str:
    """2026-07-28 → 2026 年。"""

    def _replace(match: re.Match) -> str:
        return f"{match.group(1)}年"

    return re.sub(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", _replace, text)


def desensitize_transcript(
    text: str,
    *,
    student_name: str | None = None,
    keep_grades: bool = True,
) -> str:
    """成绩单脱敏主入口。

    keep_grades=True 时保留课程名/学分/成绩精确值（个人分区内用于回答
    "某科考了多少分"）；直接标识符（姓名/学号/班级/身份证/手机号）始终脱敏。

    Args:
        text: 原始抽取文本（建议先 NFKC 归一化）
        student_name: 学生姓名（可选，命中则替换为 [姓名]）
        keep_grades: 是否保留成绩精确值

    Returns:
        脱敏后的文本
    """
    text = normalize_nfkc(text)
    text = _fix_supplement_radicals(text)
    text = replace_name(text, student_name)
    text = mask_student_id(text)
    text = mask_id_card(text)
    text = mask_mobile(text)
    text = generalize_class(text)
    text = generalize_date(text)
    return text


def build_pii_report(text: str) -> dict[str, int]:
    """返回文本中各类敏感信息的匹配计数（供审计/日志）。

    学号计数先排除手机号，避免 11 位手机被同时计入学号。
    """
    without_mobile = MOBILE_RE.sub("", text)
    return {
        "student_id": len(STUDENT_ID_RE.findall(without_mobile)),
        "id_card": len(ID_CARD_RE.findall(text)),
        "mobile": len(MOBILE_RE.findall(text)),
    }
