# -*- coding: utf-8 -*-
"""evaluation 三函数 @tool 薄壳等价性测试：薄壳转调与 service 直调结果一致。"""

from __future__ import annotations

import json

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.evaluation import compute_radar_values, design_dimensions, generate_comment


def _snapshot() -> dict:
    return {
        "derived": {
            "course_count": 71,
            "total_credits": 148.5,
            "weighted_avg": 86.3,
            "avg": 85.0,
            "variance": 2.1,
            "pass_rate": 0.98,
            "top_subject": {"name": "高等数学", "score": 95.0},
            "weak_subject": {"name": "大学英语", "score": 72.0},
        }
    }


def test_compute_radar_values_wrapper_matches_direct_call():
    from tools.evaluation.compute_radar_values import compute_radar_values as _direct

    dimensions = [
        {"name": "学业水平", "weight": 0.3, "metric": "weighted_gpa", "rationale": "x"},
    ]
    snapshot = _snapshot()
    direct = _direct(dimensions, snapshot)
    wrapped = json.loads(
        compute_radar_values.invoke({"dimensions": dimensions, "snapshot": snapshot})
    )
    assert wrapped == direct


@pytest.mark.asyncio
async def test_design_dimensions_wrapper_calls_impl_with_builtin_llm():
    with patch(
        "tools.evaluation.tool_wrappers._design_dimensions",
        new_callable=AsyncMock,
        return_value={"status": "llm", "dimensions": [], "overall_theme": "t", "errors": [], "usage": {}},
    ) as impl:
        result = await design_dimensions.ainvoke({"snapshot": _snapshot()})
    impl.assert_awaited_once()
    assert json.loads(result)["status"] == "llm"


@pytest.mark.asyncio
async def test_generate_comment_wrapper_matches_direct_output_schema():
    radar = {"values": [{"name": "学业水平", "metric": "weighted_gpa", "value": 86.3}]}
    snapshot = _snapshot()
    with patch(
        "tools.evaluation.tool_wrappers._generate_comment",
        new_callable=AsyncMock,
        return_value=("评语", "rule", {"input_tokens": 0, "output_tokens": 0}),
    ) as impl:
        out = await generate_comment.ainvoke(
            {"snapshot": snapshot, "radar": radar, "comment_type": "semester_summary"}
        )
    impl.assert_awaited_once()
    payload = json.loads(out)
    assert payload["comment"] == "评语"
    assert payload["status"] == "rule"