# -*- coding: utf-8 -*-
"""eval runner v2 测试：断言器（权重/多类型）、context 指标、分档聚合、smoke 执行。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.runner import aggregate, context_metrics, execute_case, load_set, run_assertions

EVAL_SETS = Path(__file__).resolve().parent.parent / "eval_sets"


@pytest.mark.unit
def test_eval_sets_v2_schema():
    """v2 契约：必填字段齐全（case_id/type/input/expected/judge）；case_id 唯一。"""
    seen: set[str] = set()
    for name in ["chat_intent", "report_math", "evaluation_comment", "kb_retrieval"]:
        cases = load_set(name)
        assert cases, f"{name} 为空"
        for c in cases:
            assert c["case_id"] not in seen, f"重复 case_id: {c['case_id']}"
            seen.add(c["case_id"])
            for key in ("type", "input", "expected", "judge"):
                assert key in c, f"{c['case_id']} 缺 {key}"
            assert c["judge"].get("mode") in ("exact", "code", "llm")
            assert c.get("difficulty") in ("easy", "medium", "hard")


@pytest.mark.unit
def test_assertion_weighted_scoring():
    """多断言权重求和：1/2 命中 + threshold 0.5 → 通过。"""
    case = {
        "case_id": "t",
        "judge": {"threshold": 0.5},
        "assertions": [
            {"kind": "contains", "field": "reply", "value": "甲", "weight": 1.0},
            {"kind": "contains", "field": "reply", "value": "乙", "weight": 1.0},
        ],
    }
    ok, fails = run_assertions(case, {"reply": "甲"})
    assert ok and len(fails) == 1
    ok, fails = run_assertions(case, {"reply": "甲乙"})
    assert ok and not fails
    ok, _ = run_assertions(case, {"reply": "丙"})
    assert not ok


@pytest.mark.unit
def test_reference_assertion_catches_hallucination():
    case = {
        "case_id": "t",
        "judge": {"threshold": 1.0},
        "assertions": [{"kind": "reference", "field": "comment", "value": [90.5, 8.0, 2], "weight": 1.0}],
    }
    ok, _ = run_assertions(case, {"comment": "加权均分90.5，共修2门"})
    assert ok
    ok, fails = run_assertions(case, {"comment": "均分99，非常优秀"})
    assert not ok and any("99" in f for f in fails)


@pytest.mark.unit
def test_context_metrics():
    """context recall / precision 手算核对。"""
    case = {"case_id": "t", "expected": {"chunk_ids": ["a", "b"]}, "reference": {"contexts": ["a", "b"]}}
    out = {"hit_chunk_ids": ["a", "c", "d"]}
    m = context_metrics(case, out)
    assert m["context_recall"] == 0.5  # a 命中 / 期望 a,b
    assert m["context_precision"] == round(1 / 3, 3)  # a 相关 / 命中 3 条
    assert context_metrics(case, {"hit_chunk_ids": ["a", "b"]})["context_recall"] == 1.0


@pytest.mark.unit
def test_aggregate_by_difficulty():
    results = [
        {"case_id": "a", "difficulty": "easy", "pass": True, "latency_ms": 10, "metrics": {"context_recall": 1.0, "context_precision": 1.0}},
        {"case_id": "b", "difficulty": "easy", "pass": False, "latency_ms": 20, "metrics": {"context_recall": None, "context_precision": None}},
        {"case_id": "c", "difficulty": "hard", "pass": True, "latency_ms": 30, "metrics": {}},
    ]
    agg = aggregate(results)
    assert agg["pass_rate"] == round(2 / 3, 3)
    assert agg["latency_p50"] == 20
    assert agg["latency_p95"] == 30
    assert agg["by_difficulty"]["easy"] == {"total": 2, "passed": 1}
    assert agg["context_recall_avg"] == 1.0


@pytest.mark.unit
def test_smoke_execute_all_sets():
    """四个集 smoke 全跑：chat/report/kb 自洽通过；evaluation_comment 按设计预期（正例过、反例拦）。"""
    for name in ["chat_intent", "report_math", "kb_retrieval"]:
        cases = load_set(name)
        results = [execute_case(c, live=False, judge=False) for c in cases]
        assert all(r["mode"] == "smoke" for r in results), name
        assert sum(1 for r in results if r["pass"]) == len(results), name
    # evaluation_comment：02/04 是幻觉反例，smoke 必须拦截（断言器工作正常）
    cases = load_set("evaluation_comment")
    results = [execute_case(c, live=False, judge=False) for c in cases]
    by_id = {r["case_id"]: r["pass"] for r in results}
    assert by_id["eval_comment_01"] is True
    assert by_id["eval_comment_02"] is False  # 幻觉 99 被拦
    assert by_id["eval_comment_03"] is True
    assert by_id["eval_comment_04"] is False  # 幻觉 120 被拦
