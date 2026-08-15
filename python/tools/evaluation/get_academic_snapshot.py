# -*- coding: utf-8 -*-
"""学业快照工具 — evaluation 反幻觉分层第①层（代码唯一事实源，零 LLM）。

直查 document_chunks.metadata_json 的结构化课程（摄入时写入），派生统计全部
确定性计算；无数据 → 结构化错误（不空跑 LLM）。

user_id 从 agent.main.context 注入（AGENTS.md 约束，不进 args_schema）。
"""

from __future__ import annotations

import json
import statistics

from langchain_core.tools import tool
from pydantic import BaseModel


class GetAcademicSnapshotInput(BaseModel):
    """get_academic_snapshot 工具输入参数（user_id 从请求上下文注入）。"""

    pass  # noqa: PIE790


def _dedupe_courses(chunks: list[dict]) -> list[dict]:
    """跨 chunk 聚合课程（同课程名保留最后成绩）。"""
    merged: dict[str, dict] = {}
    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        courses = metadata.get("courses") or []
        for c in courses:
            name = str(c.get("name", "")).strip()
            if not name:
                continue
            merged[name] = c
    return list(merged.values())


def compute_derived(courses: list[dict]) -> dict:
    """派生统计（确定性，手算可核对）。"""
    numeric = [c for c in courses if c.get("numeric_score") is not None]
    scores = [float(c["numeric_score"]) for c in numeric]
    total_credits = round(sum(float(c.get("credits") or 0) for c in courses), 2)
    scored_credits = round(sum(float(c.get("credits") or 0) for c in numeric), 2)

    avg = round(statistics.mean(scores), 2) if scores else None
    weighted = (
        round(sum(float(c["numeric_score"]) * float(c.get("credits") or 0) for c in numeric) / scored_credits, 2)
        if numeric and scored_credits
        else None
    )
    variance = round(statistics.pstdev(scores), 2) if len(scores) >= 2 else 0.0
    top = max(numeric, key=lambda c: float(c["numeric_score"])) if numeric else None
    weak = min(numeric, key=lambda c: float(c["numeric_score"])) if numeric else None
    passed = sum(1 for c in courses if _is_pass(c))
    return {
        "course_count": len(courses),
        "total_credits": total_credits,
        "avg": avg,
        "weighted_avg": weighted,
        "variance": variance,
        "top_subject": {"name": top["name"], "score": top["numeric_score"]} if top else None,
        "weak_subject": {"name": weak["name"], "score": weak["numeric_score"]} if weak else None,
        "pass_rate": round(passed / len(courses), 4) if courses else None,
    }


def _is_pass(course: dict) -> bool:
    num = course.get("numeric_score")
    if num is not None:
        return float(num) >= 60
    score = str(course.get("score", ""))
    return any(k in score for k in ("及格", "通过", "合格", "优秀", "良好", "中等"))


def build_snapshot() -> dict:
    """快照主逻辑（工具与测试共用）。"""
    from agent.main.context import get_current_user_id
    from agent import runtime

    user_id = get_current_user_id()
    if not user_id:
        return {"code": "no_user", "hint": "缺少用户身份"}

    try:
        chunks = runtime.document_repo.get_chunks_by_user(user_id)
    except Exception as exc:  # noqa: BLE001
        return {"code": "repo_error", "hint": str(exc)[:200]}

    courses = _dedupe_courses(chunks)
    if not courses:
        return {
            "code": "no_transcript_data",
            "hint": "该用户尚未摄入成绩单，请先上传并重灌成绩单",
        }

    return {
        "user_id": user_id,
        "courses": courses,
        "derived": compute_derived(courses),
        "sources": [c["chunk_id"] for c in chunks],
    }


@tool(args_schema=GetAcademicSnapshotInput)
def get_academic_snapshot() -> dict:
    """读取当前用户的学业快照（课程/学分/成绩 + 派生统计），evaluation 数据基准。

    无成绩单数据 → {code: "no_transcript_data", hint}；调用方不得继续生成。
    """
    return build_snapshot()
