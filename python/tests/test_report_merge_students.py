# -*- coding: utf-8 -*-
"""多科合并测试：键合并、顺序打乱、差集告警、完整性断言、Journal。"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.report.contract import canonical_dimension, canonical_subject
from tools.report.merge_students import (
    assert_integrity,
    journal_load,
    journal_save,
    merge_files,
)
from tools.report.parse_score_excels import ParsedFile, ParsedStudent, parse_workbook

FIXTURE = Path(__file__).parent / "fixtures" / "daofa-grade4-class7.xlsx"


def _pf(subject: str, students: list[ParsedStudent], class_name: str = "四（7）班") -> ParsedFile:
    return ParsedFile(
        subject=subject,
        class_name=class_name,
        semester="2023-2024第二学期",
        source_name=f"{subject}.xlsx",
        grade_columns=["过程性评价"],
        students=students,
    )


def _stu(sid: str, name: str, grade: str = "A") -> ParsedStudent:
    return ParsedStudent(student_id=sid, name=name, grades={"过程性评价": grade})


@pytest.mark.unit
def test_merge_two_subjects():
    """两科文件（同批学生、顺序打乱）→ 键合并正确、每生两科。"""
    f1 = _pf("道法", [_stu("1", "张三"), _stu("2", "李四"), _stu("3", "王五")])
    f2 = _pf("数学", [_stu("3", "王五"), _stu("1", "张三"), _stu("2", "李四")])

    merged = merge_files([f1, f2])

    assert len(merged.students) == 3
    by_name = {s["name"]: s for s in merged.students}
    assert len(by_name["张三"]["score"]) == 2
    assert [e["subject"] for e in by_name["张三"]["score"]] == ["道德与法治", "数学"]  # 别名归一
    assert assert_integrity(merged, 2) == []


@pytest.mark.unit
def test_merge_real_fixture_twice():
    """真实样本解析后与自身合并 → 每生 2 条道法（键冲突追加，不丢）。"""
    pf = parse_workbook(FIXTURE)
    merged = merge_files([pf, pf])
    assert len(merged.students) == len(pf.students)
    assert all(len(s["score"]) == 2 for s in merged.students)
    assert assert_integrity(merged, 2) == []


@pytest.mark.unit
def test_missing_student_detected():
    """某文件缺学生 → 差集告警 + 完整性断言捕获（不静默）。"""
    f1 = _pf("道法", [_stu("1", "张三"), _stu("2", "李四")])
    f2 = _pf("数学", [_stu("1", "张三")])

    merged = merge_files([f1, f2])

    assert any("李四" in w or "学号" in w for w in merged.warnings)
    errors = assert_integrity(merged, 2)
    assert any("李四" in e for e in errors)  # 缺科学生被标记


@pytest.mark.unit
def test_key_conflict_keeps_both():
    """学号相同姓名不同 → 键冲突告警但成绩不丢（追加到同一记录）。"""
    f1 = _pf("道法", [_stu("1", "张三")])
    f2 = _pf("数学", [_stu("1", "张三三")])  # 姓名不同

    merged = merge_files([f1, f2])

    assert any("键冲突" in w for w in merged.warnings)
    assert len(merged.students) == 1
    assert len(merged.students[0]["score"]) == 2


@pytest.mark.unit
def test_journal_roundtrip(tmp_path):
    """Journal 落盘/恢复：崩溃续跑的数据基础。"""
    f1 = _pf("道法", [_stu("1", "张三")])
    merged = merge_files([f1])
    path = journal_save(tmp_path, merged)

    restored = journal_load(tmp_path)
    assert restored is not None
    assert restored.batch_id == merged.batch_id
    assert restored.students == merged.students
    assert path.is_file()


@pytest.mark.unit
def test_empty_merge():
    merged = merge_files([])
    assert merged.students == []
    assert assert_integrity(merged, 0)  # 空数据 → 错误清单非空


@pytest.mark.unit
def test_alias_mapping():
    """别名归一：Excel 名 → 模板名（数值回填校验匹配依据）。"""
    assert canonical_subject("道法") == "道德与法治"
    assert canonical_subject("语文") == "语文"
    assert canonical_dimension("考试性评价70分") == "卷面成绩"
    assert canonical_dimension("综合性评价100分") == "期末总评"
    assert canonical_dimension("综合答辩") == "综合答辩"
