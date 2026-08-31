# -*- coding: utf-8 -*-
"""compute_weighted_grade 加权成绩统计单测。

工具经 @tool 包装为 StructuredTool，直接调用底层实现用 .func。
"""

from tools.report.compute_weighted_grade import compute_weighted_grade


def _call(display_eval, exam_eval, bonus=0.0):
    return compute_weighted_grade.func(
        display_eval=display_eval, exam_eval=exam_eval, bonus=bonus
    )


def test_zero_inputs():
    result = _call(0, 0, 0)
    assert result == {"total": 0.0, "display_weighted": 0.0, "exam_weighted": 0.0, "bonus": 0.0}


def test_typical_case():
    result = _call(60, 80, 5)
    assert result["display_weighted"] == 18.0
    assert result["exam_weighted"] == 56.0
    assert result["total"] == 79.0


def test_upper_bound():
    result = _call(100, 100, 20)
    assert result["display_weighted"] == 30.0
    assert result["exam_weighted"] == 70.0
    assert result["total"] == 120.0


def test_rounding():
    result = _call(33.33, 66.67)
    assert result["display_weighted"] == 10.0
    assert result["exam_weighted"] == 46.67
    assert result["total"] == 56.67


def test_schema_guard_clamps_out_of_range():
    result = _call(150, -10, 99)
    assert result["total"] <= 120.0
    assert result["bonus"] == 20.0