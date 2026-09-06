# -*- coding: utf-8 -*-
"""评语生成 — 反幻觉分层第4层（LLM 叙述 + 数值引用核验硬闸）。

- 输入 = 快照 + 雷达值 + comment_type（评语中每个数字必须来自给定数据）
- 数值引用核验：正则提取评语数字 vs 快照/雷达数值集（容差 0.5）
  → 不一致错误回灌重试 1 次 → 规则化评语（模板 + 真实数值）兜底，绝不空返回
- 流式 token 经回调上报（可选）
"""

from __future__ import annotations

import asyncio
import json
import re
import statistics
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

from ai.llm_client import build_chat_openai
from ai.llm_task_name import LLMTaskName

COMMENT_TYPES = ("semester_summary", "encouragement", "improvement_advice", "recommendation")

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _prompt() -> str:
    path = Path(__file__).resolve().parent / "prompts" / "comment.txt"
    return path.read_text(encoding="utf-8")


def build_comment_llm() -> BaseChatModel:
    return build_chat_openai(
        temperature=0.5,
        max_tokens=1024,
        task_name=LLMTaskName.EVALUATION_GENERATOR,
    )


def allowed_numbers(snapshot: dict, radar: dict) -> list[float]:
    """数据源全部数值（快照派生 + 雷达值）——核验白名单。"""
    nums: list[float] = []
    derived = snapshot.get("derived", {})
    for key in ("avg", "weighted_avg", "variance", "total_credits", "course_count", "pass_rate"):
        v = derived.get(key)
        if v is not None:
            nums.append(float(v))
    for sub in ("top_subject", "weak_subject"):
        s = derived.get(sub) or {}
        if s.get("score") is not None:
            nums.append(float(s["score"]))
    for v in radar.get("values", []):
        nums.append(float(v["value"]))
    return nums


def verify_numbers(comment: str, allowed: list[float], tolerance: float = 0.5) -> list[str]:
    """数值引用核验：评语中的每个数字都能在数据集中找到（容差内）。"""
    violations: list[str] = []
    for num_str in _NUM_RE.findall(comment):
        value = float(num_str)
        if not any(abs(value - a) <= tolerance for a in allowed):
            violations.append(num_str)
    return violations


def rule_based_comment(snapshot: dict, radar: dict, comment_type: str) -> str:
    """规则化评语（核验不过/LLM 失败时的确定性兜底，只引用真实数值）。"""
    derived = snapshot.get("derived", {})
    count = derived.get("course_count", 0)
    credits = derived.get("total_credits", 0)
    weighted = derived.get("weighted_avg")
    top = (derived.get("top_subject") or {}).get("name", "")
    weak = (derived.get("weak_subject") or {}).get("name", "")
    score_desc = f"加权均分 {weighted}" if weighted is not None else f"平均分 {derived.get('avg')}"
    base = f"本学期共修读 {count} 门课程，总学分 {credits}，{score_desc}"
    if top:
        base += f"，优势科目为{top}"
    if weak:
        base += f"；建议重点关注{weak}的学习"
    endings = {
        "semester_summary": "，整体学业表现平稳，望继续保持。",
        "encouragement": "。老师相信你下个学期会做得更好，加油！",
        "improvement_advice": "。建议制定针对性学习计划，逐步提升。",
        "recommendation": "。该生学业基础扎实，具备继续深造的良好潜力。",
    }
    return base + endings.get(comment_type, "。")


async def generate_comment(
    snapshot: dict,
    radar: dict,
    comment_type: str,
    llm: BaseChatModel | None = None,
    *,
    timeout_seconds: float = 60.0,
    on_token=None,
) -> tuple[str, str, dict]:
    """生成评语；返回 (评语, 状态：llm|rule|failed, usage)。绝不返回空。"""
    if comment_type not in COMMENT_TYPES:
        comment_type = "semester_summary"
    llm = llm or build_comment_llm()
    allowed = allowed_numbers(snapshot, radar)
    prompt = _prompt()
    payload = json.dumps(
        {"snapshot": snapshot, "radar": radar, "comment_type": comment_type},
        ensure_ascii=False,
        indent=2,
    )
    content = f"{prompt}\n\n数据：\n```json\n{payload}\n```"
    usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
    for attempt in range(2):
        try:
            resp = await asyncio.wait_for(llm.ainvoke([HumanMessage(content=content)]), timeout=timeout_seconds)
            text = str(resp.content or "").strip()
            um = getattr(resp, "usage_metadata", None) or {}
            usage["input_tokens"] += int(um.get("input_tokens", 0) or 0)
            usage["output_tokens"] += int(um.get("output_tokens", 0) or 0)
        except Exception:  # noqa: BLE001
            break
        if not text:
            content += "\n\n输出为空，请生成评语。"
            continue
        if on_token is not None:
            try:
                on_token(text)
            except Exception:  # noqa: BLE001
                pass
        violations = verify_numbers(text, allowed)
        if not violations:
            return text, "llm", usage
        content += f"\n\n上一轮评语中的数字 {violations[:5]} 不在数据中，请只引用给定数据重新生成。"
    rule = rule_based_comment(snapshot, radar, comment_type)
    return rule, "rule", usage
