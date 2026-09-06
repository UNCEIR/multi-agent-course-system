# -*- coding: utf-8 -*-
"""LLM-as-judge 三执行器（Phase 4 P0-B / B2）。

- faithfulness(question, answer, contexts)：逐句核对 answer 陈述是否可被 contexts 支持（防幻觉）
- answer_relevancy(question, answer)：answer 是否切题
- rubric(question, answer, reference, rubric)：按 case `judge.rubric` 规则打分（Phase 4 降 P1，代码就绪待 authoring）

触发矩阵（v1.2）：faithfulness 仅 kb_retrieval（需 contexts）；answer_relevancy 全集（带 reference.answer）；
rubric 仅当 `judge.rubric` 非空。LLM 失败 → `judge_failed: True`（不静默，由 runner 计入失败）。

成本控制（B2）：调用方传 `model`（--judge-model，默认同主模型）；采样/缓存由 runner 层负责。
"""

from __future__ import annotations

import json
import logging
import re

from ai.llm_client import build_chat_openai
from ai.llm_task_name import LLMTaskName

logger = logging.getLogger(__name__)

_SCORE_RE = re.compile(r"(?:score|得分)\s*[:：]?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)

_FAITHFULNESS_PROMPT = """你是评测裁判。请判断「回答」中的每个陈述是否可以被给定「参考上下文」支持（faithfulness）。

回答中的事实若在上下文中找不到依据，或与上下文矛盾，视为不支持（幻觉）。
输出格式（只输出 JSON）：
{{"score": 0~1, "verdict": "supported|partial|unsupported", "detail": "逐条说明"}}

参考上下文：
{contexts}

问题：{question}
回答：
{answer}
"""

_ANSWER_RELEVANCY_PROMPT = """你是评测裁判。请判断「回答」是否切题：是否直接回应了「问题」，是否存在答非所问。

输出格式（只输出 JSON）：
{{"score": 0~1, "verdict": "relevant|partial|irrelevant", "detail": "说明"}}

问题：{question}
回答：
{answer}
"""

_RUBRIC_PROMPT = """你是评测裁判。请按给定评分规则（rubric）对「回答」打分。

输出格式（只输出 JSON）：
{{"score": 0~1, "verdict": "pass|partial|fail", "detail": "按 rubric 逐条说明"}}

评分规则：
{rubric}

问题：{question}
参考答案（reference）：
{reference}
回答：
{answer}
"""


class JudgeError(Exception):
    """LLM-as-judge 调用失败（调用方标记 judge_failed，不静默）。"""


async def _judge_llm(prompt: str, *, model: str | None = None) -> tuple[float, str]:
    """调 LLM 打分并解析 score/detail；失败抛 JudgeError。"""
    llm = build_chat_openai(
        temperature=0.0,
        max_tokens=512,
        task_name=LLMTaskName.EVAL_JUDGE,
        model=model,
    )
    try:
        resp = await llm.ainvoke(prompt)
    except Exception as exc:  # noqa: BLE001
        raise JudgeError(f"LLM judge 调用失败: {exc}") from exc
    text = str(getattr(resp, "content", "") or "")
    if not text.strip():
        raise JudgeError("LLM judge 返回空")
    score = _parse_score(text)
    return score, text[:400]


def _parse_score(text: str) -> float:
    """从 LLM 输出解析 0~1 分数（JSON score / 文本 Score: N）。"""
    m = _SCORE_RE.search(text)
    if m:
        val = float(m.group(1))
        return min(1.0, max(0.0, val))
    try:
        data = json.loads(text)
        val = float(data.get("score", 0.0))
        return min(1.0, max(0.0, val))
    except (ValueError, TypeError):
        return 0.0


def _failed(detail: str) -> dict:
    return {"score": 0.0, "passed": False, "judge_failed": True, "detail": detail}


def _ctx_text(contexts) -> str:
    if isinstance(contexts, str):
        return contexts
    return "\n".join(str(c) for c in (contexts or []))


async def faithfulness(
    question: str,
    answer: str,
    contexts,
    *,
    model: str | None = None,
    threshold: float = 0.6,
) -> dict:
    """faithfulness：answer 陈述是否被 contexts 支持。无 contexts 时直接 judge_failed。"""
    ctx = _ctx_text(contexts)
    if not ctx.strip():
        return _failed("faithfulness 需要 contexts（仅 kb 集触发）")
    try:
        score, detail = await _judge_llm(
            _FAITHFULNESS_PROMPT.format(contexts=ctx, question=question, answer=answer),
            model=model,
        )
    except JudgeError as exc:
        return _failed(str(exc))
    return {"score": round(score, 3), "passed": score >= threshold, "judge_failed": False, "detail": detail}


async def answer_relevancy(
    question: str,
    answer: str,
    *,
    model: str | None = None,
    threshold: float = 0.6,
) -> dict:
    """answer_relevancy：answer 是否切题。全集触发。"""
    try:
        score, detail = await _judge_llm(
            _ANSWER_RELEVANCY_PROMPT.format(question=question, answer=answer),
            model=model,
        )
    except JudgeError as exc:
        return _failed(str(exc))
    return {"score": round(score, 3), "passed": score >= threshold, "judge_failed": False, "detail": detail}


async def rubric(
    question: str,
    answer: str,
    reference: str = "",
    rubric_text: str = "",
    *,
    model: str | None = None,
    threshold: float = 0.6,
) -> dict:
    """rubric：按 case `judge.rubric` 规则打分。rubric 为空 → judge_failed（需 authoring）。"""
    if not rubric_text.strip():
        return _failed("rubric 规则为空（Phase 4 P1 待 authoring）")
    try:
        score, detail = await _judge_llm(
            _RUBRIC_PROMPT.format(rubric=rubric_text, question=question, reference=reference, answer=answer),
            model=model,
        )
    except JudgeError as exc:
        return _failed(str(exc))
    return {"score": round(score, 3), "passed": score >= threshold, "judge_failed": False, "detail": detail}


async def judge_case(case: dict, output: dict, *, model: str | None = None) -> dict:
    """按触发矩阵对单个 case 跑 judge，返回 {faithfulness?, answer_relevancy?, rubric?}。"""
    result: dict = {}
    question = str((case.get("input") or {}).get("query") or (case.get("input") or {}).get("message") or "")
    answer = str(output.get("reply") or output.get("comment") or output.get("joined") or output.get("detail") or "")
    reference = case.get("reference") or {}
    judge = case.get("judge") or {}
    threshold = float(judge.get("threshold", 0.6))

    # faithfulness：仅 kb_retrieval（需 contexts）
    if case.get("type") == "kb_retrieval":
        result["faithfulness"] = await faithfulness(question, answer, reference.get("contexts", []), model=model, threshold=threshold)
    # answer_relevancy：全集（带 reference.answer 即触发；无输出文本则失败标记）
    if reference.get("answer") is not None:
        if not answer:
            result["answer_relevancy"] = _failed("无输出文本可评")
        else:
            result["answer_relevancy"] = await answer_relevancy(question, answer, model=model, threshold=threshold)
    # rubric：仅当 judge.rubric 非空（P1 authoring 后启用）
    if (judge.get("rubric") or "").strip():
        result["rubric"] = await rubric(
            question,
            answer,
            reference=str(reference.get("answer", "")),
            rubric_text=str(judge.get("rubric", "")),
            model=model,
            threshold=threshold,
        )
    return result
