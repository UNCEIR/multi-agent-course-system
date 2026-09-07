# -*- coding: utf-8 -*-
"""eval/judge.py 单测（Phase 4 B5）：mock LLM 边界分 / 触发矩阵 / judge_failed。"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from eval.judge import (
    JudgeError,
    answer_relevancy,
    faithfulness,
    judge_case,
    rubric,
)


def _fake_llm(content: str, *, raise_error: bool = False):
    llm = MagicMock()
    if raise_error:

        async def _ainvoke(*a, **k):
            raise RuntimeError("quota exceeded")

    else:

        async def _ainvoke(*a, **k):
            resp = MagicMock()
            resp.content = content
            return resp

    llm.ainvoke = AsyncMock(side_effect=_ainvoke)
    return llm


def _patch_llm(content: str, *, raise_error: bool = False):
    return patch("eval.judge.build_chat_openai", return_value=_fake_llm(content, raise_error=raise_error))


# ── 三执行器边界 ────────────────────────────────────────────────────
@pytest.mark.unit
@pytest.mark.asyncio
async def test_faithfulness_high_score():
    with _patch_llm('{"score": 0.9, "verdict": "supported", "detail": "ok"}'):
        out = await faithfulness("q", "a", ["上下文1"], threshold=0.6)
    assert out["score"] == 0.9
    assert out["passed"] is True
    assert out["judge_failed"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_faithfulness_low_score():
    with _patch_llm("Score: 0.3"):
        out = await faithfulness("q", "a", ["上下文1"], threshold=0.6)
    assert out["passed"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_faithfulness_no_contexts_judge_failed():
    out = await faithfulness("q", "a", [])
    assert out["judge_failed"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_answer_relevancy():
    with _patch_llm('{"score": 0.8, "verdict": "relevant", "detail": "ok"}'):
        out = await answer_relevancy("q", "a")
    assert out["passed"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rubric_empty_rule_judge_failed():
    out = await rubric("q", "a", rubric_text="")
    assert out["judge_failed"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rubric_with_rule():
    with _patch_llm('{"score": 0.75, "verdict": "pass", "detail": "ok"}'):
        out = await rubric("q", "a", rubric_text="按完整度 0-1 打分", threshold=0.6)
    assert out["passed"] is True
    assert out["judge_failed"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_error_marks_judge_failed():
    with _patch_llm("", raise_error=True):
        out = await answer_relevancy("q", "a")
    assert out["judge_failed"] is True
    assert "quota exceeded" in out["detail"]


# ── 触发矩阵（judge_case） ──────────────────────────────────────────
_KB_CASE = {
    "case_id": "kb_01",
    "type": "kb_retrieval",
    "input": {"query": "奖学金申请条件", "top_k": 5},
    "reference": {"answer": "应命中奖学金章节", "contexts": ["奖学金评审办法"]},
    "judge": {"metric": "recall", "mode": "code", "threshold": 0.6, "k": 5, "rubric": ""},
}

_CHAT_CASE = {
    "case_id": "intent_01",
    "type": "chat_intent",
    "input": {"message": "帮我推荐课程"},
    "reference": {"answer": "调用推荐工具"},
    "judge": {"metric": "tool_chain", "mode": "code", "threshold": 1.0, "rubric": ""},
}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_judge_case_kb_triggers_faithfulness():
    with _patch_llm('{"score": 0.9, "detail": "ok"}'):
        out = await judge_case(_KB_CASE, {"reply": "奖学金条件如下"})
    assert "faithfulness" in out
    assert "answer_relevancy" in out
    assert "rubric" not in out  # rubric 为空 → 不触发


@pytest.mark.unit
@pytest.mark.asyncio
async def test_judge_case_chat_only_relevancy():
    with _patch_llm('{"score": 0.8, "detail": "ok"}'):
        out = await judge_case(_CHAT_CASE, {"reply": "推荐了课程"})
    assert "faithfulness" not in out
    assert "answer_relevancy" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_judge_case_rubric_triggered_when_present():
    case = dict(_KB_CASE)
    case["judge"] = dict(case["judge"], rubric="按引用完整性打分")
    with _patch_llm('{"score": 0.7, "detail": "ok"}'):
        out = await judge_case(case, {"reply": "引用来源"})
    assert "rubric" in out
    assert out["rubric"]["judge_failed"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_judge_case_no_answer_text_marks_relevancy_failed():
    with _patch_llm('{"score": 0.8, "detail": "ok"}'):
        out = await judge_case(_CHAT_CASE, {})  # 无 reply/comment/joined/detail
    assert out["answer_relevancy"]["judge_failed"] is True


@pytest.mark.unit
def test_parse_score_json():
    from eval.judge import _parse_score

    assert _parse_score('{"score": 0.85}') == 0.85
    assert _parse_score("Score: 0.4") == 0.4
    assert _parse_score("garbage") == 0.0
