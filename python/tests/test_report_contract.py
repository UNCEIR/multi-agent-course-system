# -*- coding: utf-8 -*-
"""report 契约测试：错误码/等级归一/别名映射（B6，数值回填校验的匹配依据）。"""

from __future__ import annotations

import pytest

from tools.report.contract import (
    DIMENSION_ALIAS,
    SUBJECT_ALIAS,
    canonical_dimension,
    canonical_subject,
    is_valid_grade,
    normalize_grade,
)


@pytest.mark.unit
def test_normalize_grade():
    assert normalize_grade(" a ") == "A"
    assert normalize_grade(None) == ""
    assert normalize_grade("ａ") == "A"  # 全角归一（NFKC）


@pytest.mark.unit
def test_valid_grade():
    assert is_valid_grade("A")
    assert is_valid_grade("B")
    assert is_valid_grade("")  # 空值合法（没给到就留空）
    assert not is_valid_grade("AB")
    assert not is_valid_grade("优")


@pytest.mark.unit
def test_subject_alias_covers_template_subjects():
    """1.html 全部 12 学科在映射表中（模板名直配自身）。"""
    for subj in ["道德与法治", "语文", "数学", "英语", "科学", "社团", "音乐", "体育", "美术", "信息", "劳动", "综实"]:
        assert canonical_subject(subj) == subj


@pytest.mark.unit
def test_dimension_alias_covers_template_dimensions():
    """模板子维度名在映射表中（归一幂等）。"""
    for dim in ["过程性评价", "综合答辩", "学科实践", "卷面成绩", "期末总评", "必选", "自选"]:
        assert canonical_dimension(dim) == dim


@pytest.mark.unit
def test_excel_to_template_mapping():
    """Excel 维度 → 模板维度（回填校验的匹配依据）。"""
    assert canonical_dimension("考试性评价70分") == "卷面成绩"
    assert canonical_dimension("综合性评价100分") == "期末总评"
    assert canonical_subject("道法") == "道德与法治"


@pytest.mark.unit
def test_mapping_completeness_identity():
    """映射是两两归一：Excel 名与模板名互为映射对（防漏配）。"""
    for k, v in SUBJECT_ALIAS.items():
        assert canonical_subject(v) == v
    for k, v in DIMENSION_ALIAS.items():
        assert canonical_dimension(v) == v
