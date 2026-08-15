# -*- coding: utf-8 -*-
"""综合评语测试：正常生成、失败留空不阻塞、去噪清洗。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tools.report.generate_subjective_eval import _sanitize, generate_subjective_eval

STUDENT = {
    "student_id": "1",
    "class": "四（7）班",
    "name": "陈烨",
    "score": [{"subject": "道法", "过程性评价": "A", "综合答辩·等级": "A"}],
}


def _llm(content: str) -> MagicMock:
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content=content))
    return llm


@pytest.mark.unit
async def test_generate_ok():
    text = await generate_subjective_eval(STUDENT, llm=_llm("该生本学期表现优秀，道法科目稳定在A等，望保持！"))
    assert "A" in text
    assert len(text) <= 200


@pytest.mark.unit
async def test_generate_failure_returns_empty():
    """LLM 抛错 → ""（评语区留空，不阻塞交付）。"""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=RuntimeError("llm down"))
    assert await generate_subjective_eval(STUDENT, llm=llm) == ""


@pytest.mark.unit
async def test_generate_timeout_returns_empty():
    """超时 → ""。"""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=TimeoutError("timeout"))
    assert await generate_subjective_eval(STUDENT, llm=llm, timeout_seconds=0.01) == ""


@pytest.mark.unit
def test_sanitize_strips_code_fences():
    text = _sanitize("```\n好的，以下是评语：该生认真努力。\n```")
    assert "该生认真努力" in text
    assert "```" not in text


@pytest.mark.unit
def test_sanitize_keeps_chinese_and_grades():
    text = _sanitize("道法A等，综合表现优秀。")
    assert "道法" in text
    assert "A" in text
