# -*- coding: utf-8 -*-
"""D 层确定性 evaluator：target outputs 与 ground truth 比对（不调 LLM）。

evaluator 统一签名：(inputs: dict, outputs: dict, reference_outputs: dict) -> dict
返回 {"key": str, "score": 0~1, "comment": str}（LangSmith feedback 兼容形状）。
单测友好：不依赖 langsmith 框架，可直接 await。
"""

from __future__ import annotations


def _tool_chain(outputs: dict | None) -> list[str]:
    return [str(tc.get("name", "")) for tc in ((outputs or {}).get("tool_calls") or []) if tc.get("name")]


def _is_subsequence(needle: list[str], haystack: list[str]) -> bool:
    """needle 是否按序出现于 haystack（允许中间有辅助工具）。"""
    it = iter(haystack)
    return all(item in it for item in needle)


def tool_chain_evaluator(inputs: dict, outputs: dict, reference_outputs: dict | None = None) -> dict:
    """编排型（chat/recommend 等）：期望工具链是实际工具链的有序子序列。

    语义：核心工具不漏调、顺序不颠倒（如先查成绩再推荐），同时允许真实 agent
    追加合理辅助工具（inspect_score_excels/glob/query_transcript 等）。
    空期望链 = 反例（不该调任何业务工具）；实际必须也为空。
    """
    expected = list(((reference_outputs or {}).get("expected") or {}).get("tool_chain") or [])
    actual = _tool_chain(outputs)
    if not expected:
        ok = not actual
    else:
        ok = _is_subsequence(expected, actual)
    if ok:
        return {"key": "tool_chain", "score": 1.0, "comment": f"tool_chain 命中(子序列): 期望 {expected} ⊆ 实际 {actual}"}
    return {
        "key": "tool_chain",
        "score": 0.0,
        "comment": f"tool_chain 不符: 期望 {expected} 非实际 {actual} 的有序子序列",
    }


def non_empty_answer_evaluator(inputs: dict, outputs: dict, reference_outputs: dict | None = None) -> dict:
    """生成型兜底：answer 非空且不为占位。"""
    answer = str((outputs or {}).get("answer") or "").strip()
    if not answer:
        return {"key": "non_empty_answer", "score": 0.0, "comment": "answer 为空"}
    return {"key": "non_empty_answer", "score": 1.0, "comment": f"answer 长度 {len(answer)}"}


DETERMINISTIC_EVALUATORS = {
    "chat_intent": [tool_chain_evaluator],
    "kb_rag": [non_empty_answer_evaluator],
}


def get_deterministic(feature: str):
    """返回该功能点的确定性 evaluator 列表（默认给非空兜底）。"""
    return DETERMINISTIC_EVALUATORS.get(feature) or [non_empty_answer_evaluator]
