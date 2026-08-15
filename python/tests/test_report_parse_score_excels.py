# -*- coding: utf-8 -*-
"""真实样本解析测试：等级列 C/E/G/J/L、丢分数/备注、sheet 选择、元数据提取。"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.report.parse_score_excels import ExcelParseError, parse_workbook

FIXTURE = Path(__file__).parent / "fixtures" / "daofa-grade4-class7.xlsx"


@pytest.fixture
def parsed():
    return parse_workbook(FIXTURE)


@pytest.mark.unit
def test_grade_columns_expected(parsed):
    """等级列 = 过程性评价/综合答辩/学科实践/考试性评价70分/综合性评价100分。"""
    assert parsed.grade_columns == [
        "过程性评价",
        "综合答辩·等级",
        "学科实践·等级",
        "考试性评价70分·等级",
        "综合性评价100分·等级",
    ]


@pytest.mark.unit
def test_meta_from_row3(parsed):
    """行3 班级/学科提取；学期从文件名兜底。"""
    assert parsed.class_name == "四（7）班"
    assert parsed.subject == "道法"
    assert parsed.semester == ""


@pytest.mark.unit
def test_first_student_grades(parsed):
    """首行学生：陈烨 A/A/A/A/A（分数 15 被丢，等级保留）。"""
    assert parsed.students[0].student_id == "1"
    assert parsed.students[0].name == "陈烨"
    assert parsed.students[0].grades["过程性评价"] == "A"
    assert parsed.students[0].grades["综合答辩·等级"] == "A"
    assert parsed.students[0].grades["学科实践·等级"] == "A"
    assert parsed.students[0].grades["考试性评价70分·等级"] == "A"
    assert parsed.students[0].grades["综合性评价100分·等级"] == "A"


@pytest.mark.unit
def test_grades_varied(parsed):
    """第二行学生：黎斯荣 考试性 D / 综合性 C（等级多样性）。"""
    s = parsed.students[1]
    assert s.name == "黎斯荣"
    assert s.grades["考试性评价70分·等级"] == "D"
    assert s.grades["综合性评价100分·等级"] == "C"


@pytest.mark.unit
def test_scores_and_remarks_dropped(parsed):
    """分数/原始/折算/备注列不进等级集合。"""
    for dim in parsed.grade_columns:
        assert "分数" not in dim
        assert "原始" not in dim
        assert "折算" not in dim
        assert "备注" not in dim


@pytest.mark.unit
def test_student_count_and_no_blanks(parsed):
    """学生行数 > 30 且无空行混入（表头后首个非空行起）。"""
    assert len(parsed.students) >= 30
    assert all(s.name for s in parsed.students)


@pytest.mark.unit
def test_missing_file_raises_structured(tmp_path):
    """文件不存在/损坏 → 结构化 ExcelParseError。"""
    with pytest.raises(ExcelParseError) as ei:
        parse_workbook(tmp_path / "not_exist.xlsx")
    assert "parse_failed" in str(ei.value)
