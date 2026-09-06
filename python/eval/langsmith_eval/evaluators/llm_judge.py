# -*- coding: utf-8 -*-
"""J 层 LLM-as-judge evaluator：包装 eval/judge.py 三执行器（触发矩阵语义一致）。

LLM 一律走 eval.judge 内部的 build_chat_openai(task_name=LLMTaskName.EVAL_JUDGE)，
不在此处新建 ChatOpenAI。返回 {"key": "llm_judge", "score", "comment"}；LLM 失败 →
judge_failed=True 时 score=0 且 comment 含原因（不静默，与 judge.py 契约一致）。
"""

from __future__ import annotations

import json

from eval.judge import judge_case


async def llm_judge_evaluator(inputs: dict, outputs: dict, reference_outputs: dict | None = None, *, model: str | None = None) -> dict:
    """按 reference 里的触发矩阵（type/reference/judge）对单 case 跑 judge 并聚合成一分。"""
    ro = reference_outputs or {}
    ref = ro.get("reference") or {}
    judge_cfg = ro.get("judge") or {}
    case = {
        "type": ro.get("case_type") or inputs.get("type") or ref.get("type") or "",
        "input": {k: v for k, v in inputs.items() if k != "case_id"},
        "reference": ref,
        "judge": judge_cfg,
    }
    out = (outputs or {})
    output = {
        "reply": out.get("answer") or out.get("reply") or "",
        "comment": out.get("answer") or "",
        "detail": json.dumps(out.get("structured", {}), ensure_ascii=False)[:500],
    }
    res = await judge_case(case, output, model=model)
    if not res:
        return {"key": "llm_judge", "score": 0.0, "comment": "触发矩阵为空（无 reference.answer / 非 kb 且无 rubric）"}
    scores = [v.get("score", 0.0) for v in res.values() if isinstance(v, dict) and not v.get("judge_failed")]
    failed = [k for k, v in res.items() if isinstance(v, dict) and v.get("judge_failed")]
    avg = round(sum(scores) / len(scores), 3) if scores else 0.0
    detail = {k: v.get("detail", "") for k, v in res.items() if isinstance(v, dict)}
    comment = json.dumps({"avg": avg, "failed": failed, "detail": detail}, ensure_ascii=False)[:500]
    return {"key": "llm_judge", "score": avg, "comment": comment}


def llm_judge_evaluator_sync(inputs: dict, outputs: dict, reference_outputs: dict | None = None, *, model: str | None = None) -> dict:
    """同步入口：供 langsmith.evaluate（同步 runner）在 threadpool 中调用。"""
    import asyncio

    return asyncio.run(llm_judge_evaluator(inputs, outputs, reference_outputs, model=model))
