# -*- coding: utf-8 -*-
"""eval/langsmith_eval 单测（Phase 4 LangSmith 原生轨骨架）：mock LLM，不烧配额。

覆盖：数据集加载/映射、确定性 tool_chain evaluator（含空链反例）、mock target 与 evaluator 闭环、
llm_judge evaluator（patch eval.judge.build_chat_openai）、dry-run 报告。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from eval.langsmith_eval import datasets, targets
from eval.langsmith_eval.evaluators.deterministic import tool_chain_evaluator
from eval.langsmith_eval.evaluators.llm_judge import llm_judge_evaluator


def _fake_llm(content: str):
    async def _ainvoke(*a, **k):
        resp = MagicMock()
        resp.content = content
        return resp

    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=_ainvoke)
    return llm


def _patch_judge_llm(content: str):
    return patch("eval.judge.build_chat_openai", return_value=_fake_llm(content))


# ── 数据集 ──────────────────────────────────────────────────────────
@pytest.mark.unit
def test_load_cases_phase4_chat_intent():
    cases = datasets.load_cases("chat_intent")
    assert len(cases) == 10
    ids = [c["case_id"] for c in cases]
    assert len(ids) == len(set(ids))
    for c in cases:
        assert "input" in c and "expected" in c and "reference" in c and "judge" in c


@pytest.mark.unit
def test_map_examples_shape():
    cases = datasets.load_cases("chat_intent")
    examples = datasets.map_examples(cases)
    assert len(examples) == 10
    ex = examples[0]
    assert "case_id" in ex["inputs"] and "message" in ex["inputs"]
    assert {"expected", "reference", "judge", "assertions"} <= set(ex["outputs"])
    assert ex["metadata"]["difficulty"] in {"easy", "medium", "hard"}
    assert ex["metadata"]["mode"] == "offline"


# ── 确定性 evaluator ───────────────────────────────────────────────
@pytest.mark.unit
def test_tool_chain_match():
    out = {"tool_calls": [{"name": "query_handbook", "args": {}}]}
    ref = {"expected": {"tool_chain": ["query_handbook"]}}
    r = tool_chain_evaluator({"message": "x"}, out, ref)
    assert r["score"] == 1.0


@pytest.mark.unit
def test_tool_chain_mismatch():
    out = {"tool_calls": [{"name": "query_transcript", "args": {}}]}
    ref = {"expected": {"tool_chain": ["query_handbook"]}}
    r = tool_chain_evaluator({"message": "x"}, out, ref)
    assert r["score"] == 0.0
    assert "期望" in r["comment"]


@pytest.mark.unit
def test_tool_chain_empty_expectation_is_counter_example():
    # intent_19：不该调工具；实际调了工具必须判负
    out = {"tool_calls": [{"name": "recommend_courses", "args": {}}]}
    ref = {"expected": {"tool_chain": []}}
    r = tool_chain_evaluator({"message": "闲聊"}, out, ref)
    assert r["score"] == 0.0
    out2 = {"tool_calls": []}
    r2 = tool_chain_evaluator({"message": "闲聊"}, out2, ref)
    assert r2["score"] == 1.0


# ── mock target 与 evaluator 闭环（等价 dry-run 单条）──────────────
@pytest.mark.unit
def test_mock_target_closes_with_deterministic():
    cases = datasets.load_cases("chat_intent")
    for c in cases:
        ex = datasets.map_examples([c])[0]
        out = targets.mock_chat_intent(ex["inputs"], ex["outputs"])
        r = tool_chain_evaluator(ex["inputs"], out, ex["outputs"])
        assert r["score"] == 1.0, (c["case_id"], r)


# ── llm_judge evaluator（mock LLM）─────────────────────────────────
@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_judge_evaluator_scores_relevancy():
    inputs = {"case_id": "intent_08", "message": "奖学金申请条件是什么"}
    ref = {
        "expected": {"tool_chain": ["query_handbook"]},
        "reference": {"answer": "应调用 query_handbook 检索学生手册并引用来源页码", "contexts": ["奖学金评审办法"]},
        "judge": {"metric": "tool_chain", "mode": "exact", "threshold": 1.0, "rubric": ""},
        "case_type": "chat_intent",
    }
    outputs = {"answer": "依据学生手册，奖学金需满足……", "tool_calls": [{"name": "query_handbook", "args": {}}]}
    with _patch_judge_llm('{"score": 0.8, "verdict": "relevant", "detail": "切题"}'):
        r = await llm_judge_evaluator(inputs, outputs, ref)
    assert r["key"] == "llm_judge"
    assert r["score"] == 0.8
    assert "failed" in r["comment"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_judge_evaluator_no_trigger():
    # 无 reference.answer → 触发矩阵为空 → score=0 comment 说明
    inputs = {"case_id": "c1", "message": "你好"}
    ref = {"expected": {"tool_chain": []}, "reference": {}, "judge": {}, "case_type": "chat_intent"}
    outputs = {"answer": None, "tool_calls": []}
    r = await llm_judge_evaluator(inputs, outputs, ref)
    assert r["score"] == 0.0
    assert "触发矩阵为空" in r["comment"]


# ── dry-run 报告 ───────────────────────────────────────────────────
@pytest.mark.unit
def test_cli_dry_run_report(tmp_path):
    from eval.langsmith_eval import cli

    report = asyncio.run(cli._run_dry("chat_intent"))
    assert report["total"] == 10
    assert report["passed"] == 10
    assert report["mode"] == "dry-run"
    for row in report["results"]:
        assert all(e["score"] == 1.0 for e in row["evaluations"])


# ── tool_chain 子序列语义（真实 agent 允许合理辅助工具）──────────────
@pytest.mark.unit
def test_tool_chain_subsequence_allows_aux():
    # 期望核心工具出现即可，允许真实链路追加辅助工具（如 report 后 inspect_score_excels/glob）
    out = {"tool_calls": [{"name": "report", "args": {}}, {"name": "report", "args": {}}, {"name": "inspect_score_excels", "args": {}}, {"name": "glob", "args": {}}]}
    ref = {"expected": {"tool_chain": ["report"]}}
    r = tool_chain_evaluator({"message": "出报告"}, out, ref)
    assert r["score"] == 1.0, r


@pytest.mark.unit
def test_tool_chain_keeps_order():
    # 顺序语义：期望 [query_transcript, recommend_courses]（先查已选再推荐）不可颠倒
    out = {"tool_calls": [{"name": "recommend_courses", "args": {}}, {"name": "query_transcript", "args": {}}]}
    ref = {"expected": {"tool_chain": ["query_transcript", "recommend_courses"]}}
    r = tool_chain_evaluator({"message": "先查再推"}, out, ref)
    assert r["score"] == 0.0, r
