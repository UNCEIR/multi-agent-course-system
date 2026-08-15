# -*- coding: utf-8 -*-
"""evaluation 反幻觉分层测试：维度提案校验、雷达数值确定性、评语核验硬闸。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tools.evaluation.compute_radar_values import compute_radar_values
from tools.evaluation.design_dimensions import (
    default_dimensions,
    design_dimensions,
    validate_proposal,
)
from tools.evaluation.generate_comment import (
    allowed_numbers,
    generate_comment,
    rule_based_comment,
    verify_numbers,
)

SNAPSHOT = {
    "user_id": "u1",
    "courses": [
        {"name": "高数", "credits": 5.0, "score": "92", "numeric_score": 92.0},
        {"name": "英语", "credits": 3.0, "score": "88", "numeric_score": 88.0},
    ],
    "derived": {
        "course_count": 2,
        "total_credits": 8.0,
        "avg": 90.0,
        "weighted_avg": 90.5,
        "variance": 2.0,
        "top_subject": {"name": "高数", "score": 92.0},
        "weak_subject": {"name": "英语", "score": 88.0},
        "pass_rate": 1.0,
    },
    "sources": ["c1"],
}

GOOD_DIMENSIONS = {
    "dimensions": [
        {"name": "学业水平", "weight": 0.3, "metric": "weighted_gpa", "rationale": "加权均分"},
        {"name": "稳定性", "weight": 0.2, "metric": "stability", "rationale": "波动"},
        {"name": "优势科目", "weight": 0.2, "metric": "top_subject", "rationale": "最高分"},
        {"name": "基础扎实", "weight": 0.15, "metric": "pass_rate", "rationale": "及格率"},
        {"name": "学业投入", "weight": 0.15, "metric": "credit_load", "rationale": "学分"},
    ],
    "overall_theme": "综合学业表现",
}


# ── 层② 维度提案校验 ───────────────────────────────────────────────────
@pytest.mark.unit
def test_validate_proposal_ok():
    parsed, errors = validate_proposal(GOOD_DIMENSIONS, 5)
    assert parsed is not None
    assert errors == []


@pytest.mark.unit
def test_validate_proposal_unknown_metric_rejected():
    bad = {"dimensions": [dict(d) for d in GOOD_DIMENSIONS["dimensions"]], "overall_theme": "x"}
    bad["dimensions"][0]["metric"] = "gpa_by_feeling"
    parsed, errors = validate_proposal(bad, 5)
    assert parsed is None
    assert any("metric" in e for e in errors)


@pytest.mark.unit
def test_validate_proposal_wrong_dim_count():
    dims = [dict(d) for d in GOOD_DIMENSIONS["dimensions"]][:4]
    parsed, errors = validate_proposal({"dimensions": dims, "overall_theme": "x"}, 5)
    assert parsed is None
    assert any("维度数" in e for e in errors)


@pytest.mark.unit
def test_validate_proposal_weight_not_one():
    dims = [dict(d) for d in GOOD_DIMENSIONS["dimensions"]]
    dims[0]["weight"] = 0.9
    parsed, errors = validate_proposal({"dimensions": dims, "overall_theme": "x"}, 5)
    assert parsed is None
    assert any("权重" in e for e in errors)


# ── 层③ 雷达数值确定性 ─────────────────────────────────────────────────
@pytest.mark.unit
def test_radar_values_hand_computed():
    radar = compute_radar_values(GOOD_DIMENSIONS["dimensions"], SNAPSHOT)
    values = {v["name"]: v["value"] for v in radar["values"]}
    assert values["学业水平"] == 90.5  # weighted_avg 90.5 归一 0-100
    assert values["稳定性"] == 80.0  # 100 - 2.0*10
    assert values["优势科目"] == 92.0
    assert values["基础扎实"] == 100.0  # pass_rate 1.0 → 100
    assert values["学业投入"] == 20.0  # 8/40*100
    assert radar["rejected"] == []


@pytest.mark.unit
def test_radar_values_reject_unknown_metric():
    dims = [{"name": "瞎编", "weight": 1.0, "metric": "magic", "rationale": "x"}]
    radar = compute_radar_values(dims, SNAPSHOT)
    assert radar["values"] == []
    assert radar["rejected"] == ["瞎编"]


# ── 层④ 评语数值核验 ───────────────────────────────────────────────────
@pytest.mark.unit
def test_verify_numbers_catches_hallucination():
    allowed = allowed_numbers(SNAPSHOT, {"values": [{"value": 90.5}, {"value": 80.0}]})
    assert verify_numbers("均分90.5，稳定性80，编造的99分", allowed) == ["99"]


@pytest.mark.unit
def test_verify_numbers_passes_real():
    allowed = allowed_numbers(SNAPSHOT, {"values": [{"value": 90.5}]})
    assert verify_numbers("加权均分90.5，共修2门，总学分8", allowed) == []


def _llm(content: str) -> MagicMock:
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content=content))
    return llm


@pytest.mark.unit
async def test_generate_comment_llm_path():
    comment, status, _usage = await generate_comment(
        SNAPSHOT,
        {"values": [{"value": 90.5}]},
        "semester_summary",
        llm=_llm("本学期加权均分90.5，表现优秀。"),
    )
    assert status == "llm"
    assert "90.5" in comment


@pytest.mark.unit
async def test_generate_comment_hallucination_retries_then_rule():
    """注入幻觉数字 → 核验拦截 → 重试仍错 → 规则化兜底（不空返回）。"""
    bad = "均分99分，非常优秀。"  # 99 不在数据中
    comment, status, _usage = await generate_comment(
        SNAPSHOT,
        {"values": [{"value": 90.5}]},
        "encouragement",
        llm=_llm(bad),
    )
    assert status == "rule"
    assert "90.5" in comment or "2" in comment  # 规则化评语引用真实数值
    assert "99" not in comment


@pytest.mark.unit
async def test_generate_comment_llm_failure_rules():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=RuntimeError("down"))
    comment, status, _usage = await generate_comment(SNAPSHOT, {"values": []}, "recommendation", llm=llm)
    assert status == "rule"
    assert comment  # 非空


@pytest.mark.unit
def test_rule_based_comment_uses_real_numbers():
    comment = rule_based_comment(SNAPSHOT, {"values": []}, "semester_summary")
    assert "2" in comment
    assert "8" in comment  # 总学分
    assert "90.5" in comment


# ── 层② 降级 ───────────────────────────────────────────────────────────
@pytest.mark.unit
async def test_design_dimensions_fallback_default():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=RuntimeError("down"))
    result = await design_dimensions(SNAPSHOT, llm=llm)
    assert result["status"] == "default"
    assert len(result["dimensions"]) == 5
    assert result["dimensions"][0]["metric"] == "weighted_gpa"
    assert result["errors"]


@pytest.mark.unit
def test_default_dimensions_match_metrics():
    for d in default_dimensions():
        assert d["metric"] in ("weighted_gpa", "stability", "top_subject", "pass_rate", "credit_load")
