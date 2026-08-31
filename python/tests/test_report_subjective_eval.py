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


@pytest.mark.unit
async def test_generate_includes_user_message():
    """前端 user_message（补充要求）注入评语提示词，让该字段真正影响产物。"""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content="该生本学期表现优秀，望继续保持！"))
    await generate_subjective_eval(STUDENT, llm=llm, user_message="评语写温暖一些，多用鼓励")
    args = llm.ainvoke.await_args.args
    content = args[0][0].content
    assert "评语写温暖一些" in content
    assert "多用鼓励" in content


@pytest.mark.unit
async def test_generate_empty_user_message_no_injection():
    """user_message 为空 → 不额外拼接补充要求段。"""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content="好"))
    await generate_subjective_eval(STUDENT, llm=llm, user_message="   ")
    content = llm.ainvoke.await_args.args[0][0].content
    assert "用户补充要求" not in content


@pytest.mark.unit
def test_apply_class_override():
    """前端手动选择班级 → 批量覆盖学生 class；空值不覆盖。"""
    from tools.report.render_report_batch import apply_class_override

    students = [{"student_id": "1", "class": "四（7）班"}, {"student_id": "2", "class": ""}]
    apply_class_override(students, " 四（7）班 ")
    assert students[0]["class"] == "四（7）班"
    assert students[1]["class"] == "四（7）班"

    apply_class_override(students, "  ")
    assert students[0]["class"] == "四（7）班"  # 空值不覆盖
