# -*- coding: utf-8 -*-
"""Phase 4 LangSmith 原生评测：target 函数（inputs -> outputs）。

统一输出形状（供 evaluator 消费）：
    {"answer": str | None,
     "tool_calls": [{"name": str, "args": dict}],   # 编排型：真实工具调用序列
     "structured": dict,                            # 结构化结果（RAG hits/硬约束结果等）
     "events": list[dict]}                          # SSE/事件序列（流式功能点）

- mock_*：从 ground truth 构造"理想输出"，用于 --dry-run 与单测（不烧 LLM）。
- *_live：真调本地 API/管线（httpx，127.0.0.1:8000），Phase 3 配额就绪后启用。
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

BASE_URL = "http://127.0.0.1:8000"


def _reference_of(reference_outputs: dict | None) -> dict:
    return dict((reference_outputs or {}).get("reference") or {})


def mock_chat_intent(inputs: dict, reference_outputs: dict | None = None) -> dict:
    """dry-run：按 ground truth 的 tool_chain 构造工具序列 + reference.answer。"""
    expected = dict((reference_outputs or {}).get("expected") or {})
    chain = list(expected.get("tool_chain") or [])
    ref = _reference_of(reference_outputs)
    return {
        "answer": ref.get("answer"),
        "tool_calls": [{"name": name, "args": {}} for name in chain],
        "structured": {"intent": expected.get("intent")},
        "events": [],
    }


def mock_kb_rag(inputs: dict, reference_outputs: dict | None = None) -> dict:
    """dry-run：按 reference.contexts 构造检索命中。"""
    ref = _reference_of(reference_outputs)
    contexts = ref.get("contexts") or []
    hits = [
        {"source_doc_name": "广东工业大学2025年学生手册", "page_number": 1 + i, "rank": i + 1, "score": 0.9 - i * 0.05, "content": str(ctx)[:200]}
        for i, ctx in enumerate(contexts[:5])
    ]
    return {
        "answer": ref.get("answer"),
        "tool_calls": [],
        "structured": {"retrieved": hits},
        "events": [],
    }


MOCK_TARGETS = {
    "chat_intent": mock_chat_intent,
    "kb_rag": mock_kb_rag,
}


def chat_intent_live(inputs: dict) -> dict:
    """live：真调 POST /api/v1/chat/stream，复用 eval.runner._parse_chat_stream_events 归一工具链。"""
    import httpx

    # runner 纯函数：SSE 行迭代器 -> {tool_chain(已归一 dispatch/task/噪音过滤), reply, usage, ...}
    from eval.runner import _parse_chat_stream_events

    payload = {
        "message": inputs.get("message", ""),
        "session_id": inputs.get("session_id", f"eval-{inputs.get('case_id', 'x')}"),
        "user_id": inputs.get("user_id", "eval_user"),
    }
    # host->container SSE 偶发 502（已知 bug）：重试 3 次，退避 2s
    last_err: Exception | None = None
    for attempt in range(5):
        try:
            with httpx.Client(timeout=300.0) as client:
                with client.stream("POST", f"{BASE_URL}/api/v1/chat/stream", json=payload) as resp:
                    if resp.status_code == 502 and attempt < 4:
                        import time
                        time.sleep(2)
                        continue
                    resp.raise_for_status()
                    parsed = _parse_chat_stream_events(resp.iter_lines())
            break
        except httpx.HTTPStatusError as exc:
            last_err = exc
            if attempt < 4:
                import time
                time.sleep(3)
                continue
            raise
    else:
        raise RuntimeError(f"chat/stream 5 次重试均失败: {last_err}")
    chain = list(parsed.get("tool_chain") or [])
    return {
        "answer": parsed.get("reply") or "",
        "tool_calls": [{"name": name, "args": {}} for name in chain],
        "structured": {
            "usage": parsed.get("usage") or {},
            "latency_ms": parsed.get("latency_ms"),
            "ttft_ms": parsed.get("ttft_ms"),
        },
        "events": [],
    }


LIVE_TARGETS = {
    "chat_intent": chat_intent_live,
}


def get_target(feature: str, live: bool):
    """返回 target 可调用对象；live 需要对应功能点已实现，否则回退 mock 并告警。"""
    if live:
        target = LIVE_TARGETS.get(feature)
        if target is not None:
            return target
        logger.warning("feature %s 的 live target 未实现，回退 mock（dry-run 语义）", feature)
    return MOCK_TARGETS.get(feature) or mock_chat_intent
