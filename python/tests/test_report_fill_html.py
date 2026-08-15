# -*- coding: utf-8 -*-
"""模板填充测试：模板契约、结构校验、数值回填校验、Jinja2 降级、LLM 坏响应拦截。"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from tools.report.fill_report_html import (
    FillValidationError,
    fill_one_llm,
    fill_with_jinja2,
    get_template,
    validate_backfill,
    validate_structure,
)

STUDENT = {
    "student_id": "1",
    "class": "四（7）班",
    "name": "陈烨",
    "semester": "2023-2024第二学期",
    "score": [
        {
            "subject": "道法",
            "过程性评价": "A",
            "综合答辩·等级": "A",
            "学科实践·等级": "A",
            "考试性评价70分·等级": "A",
            "综合性评价100分·等级": "A",
        }
    ],
}


@pytest.fixture(scope="module")
def template():
    return get_template("grade4-6.html")


def _slots(html: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in re.finditer(r'data-slot="([^"]+)"[^>]*>([^<]*)</span>', html)}


# ── 模板契约 ───────────────────────────────────────────────────────────
@pytest.mark.unit
def test_template_slots_complete(template):
    """模板锚点覆盖 12 学科 + 班级/姓名/学期/评语区（契约完备性）。"""
    slots = {m.group(1) for m in re.finditer(r'data-slot="([^"]+)"', template)}
    assert "class|name" in slots
    assert "student|name" in slots
    assert "semester" in slots
    assert "comment" in slots
    for subj in ["道德与法治", "语文", "数学", "英语", "科学"]:
        for dim in ["过程性评价", "综合答辩", "学科实践", "卷面成绩", "期末总评"]:
            assert f"{subj}|{dim}|grade" in slots, f"缺 {subj}|{dim}"
    for subj in ["音乐", "体育", "美术", "信息", "劳动", "综实"]:
        for dim in ["过程性评价", "必选", "自选", "综合性评价"]:
            assert f"{subj}|{dim}|grade" in slots, f"缺 {subj}|{dim}"
    assert "社团|课程名称|grade" in slots
    assert "社团|综合评价|grade" in slots


@pytest.mark.unit
def test_template_structure_valid(template):
    """模板本身结构校验通过（标签闭合、无重复锚点）。"""
    assert validate_structure(template, template) == []
    slots = re.findall(r'data-slot="([^"]+)"', template)
    assert len(slots) == len(set(slots))  # 无重复锚点


# ── 确定性降级填充（Jinja2）────────────────────────────────────────────
@pytest.mark.unit
def test_fill_with_jinja2_correct(template):
    html = fill_with_jinja2(template, STUDENT)
    filled = _slots(html)
    assert filled["class|name"] == "四（7）班"
    assert filled["student|name"] == "陈烨"
    assert filled["semester"] == "2023-2024第二学期"
    # 别名归一：道法→道德与法治、考试性评价70分→卷面成绩、综合性评价100分→期末总评
    assert filled["道德与法治|过程性评价|grade"] == "A"
    assert filled["道德与法治|卷面成绩|grade"] == "A"
    assert filled["道德与法治|期末总评|grade"] == "A"
    assert validate_structure(html, template) == []
    assert validate_backfill(html, STUDENT) == []


@pytest.mark.unit
def test_fill_with_jinja2_missing_keeps_blank(template):
    """数据里没有的学科 → 锚点留空（没给到就留空）。"""
    student = {"student_id": "2", "class": "四（7）班", "name": "李四", "semester": "", "score": []}
    html = fill_with_jinja2(template, student)
    filled = _slots(html)
    assert filled["道德与法治|过程性评价|grade"] == ""
    assert validate_backfill(html, student) == []


# ── 校验器 ─────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_validate_structure_catches_missing_slot(template):
    """模板锚点被删 → 结构校验拦截。"""
    broken = template.replace('data-slot="道德与法治|过程性评价|grade"', 'data-slot="hacked"')
    errors = validate_structure(broken, template)
    assert any("道德与法治|过程性评价|grade" in e for e in errors)


@pytest.mark.unit
def test_validate_backfill_catches_wrong_value(template):
    """填错等级 → 数值回填校验拦截。"""
    html = fill_with_jinja2(template, STUDENT).replace(">A</span>", ">B</span>", 1)
    errors = validate_backfill(html, STUDENT)
    assert errors


# ── LLM 填充（mock）───────────────────────────────────────────────────
def _fake_llm(output: str) -> MagicMock:
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content=output))
    return llm


@pytest.mark.unit
async def test_fill_one_llm_good_output(template):
    """LLM 输出正确 → 通过双校验返回。"""
    good = fill_with_jinja2(template, STUDENT)
    result = await fill_one_llm(template, STUDENT, llm=_fake_llm(good))
    assert "陈烨" in result


@pytest.mark.unit
async def test_fill_one_llm_wrong_grade_retries_then_raises(template):
    """LLM 填错等级 → 错误回灌重试 → 仍错 → FillValidationError（触发 Jinja2 降级）。"""
    bad = fill_with_jinja2(template, STUDENT).replace(">A</span>", ">B</span>", 1)
    llm = _fake_llm(bad)
    with pytest.raises(FillValidationError) as ei:
        await fill_one_llm(template, STUDENT, llm=llm, retries=1)
    assert any("卷面成绩" in e or "期末总评" in e or "过程性评价" in e for e in ei.value.errors)
    assert llm.ainvoke.await_count == 2  # 重试 1 次


@pytest.mark.unit
async def test_fill_one_llm_truncated_output_raises(template):
    """LLM 输出截断（缺锚点）→ 结构校验拦截 → 抛错。"""
    truncated = fill_with_jinja2(template, STUDENT)[: len(template) // 2]
    with pytest.raises(FillValidationError):
        await fill_one_llm(template, STUDENT, llm=_fake_llm(truncated), retries=0)


@pytest.mark.unit
async def test_fill_one_llm_template_mangled_raises(template):
    """LLM 改模板结构 → 结构校验拦截。"""
    mangled = fill_with_jinja2(template, STUDENT).replace("<table>", "<tablex>")
    with pytest.raises(FillValidationError):
        await fill_one_llm(template, STUDENT, llm=_fake_llm(mangled), retries=0)
