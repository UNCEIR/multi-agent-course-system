# -*- coding: utf-8 -*-
"""评价维度提案 — 反幻觉分层第2层（LLM 设计体系，代码校验）。

- LLM 输出必须为结构化 JSON（Pydantic 硬校验）：dimensions[] + overall_theme
- 维度数必须恰为 evaluation_radar_axis_count（默认 5）
- metric 必须是代码枚举（第③层计算），未知引用 → 拒绝该维
- 校验失败 → 错误回灌重试 1 次 → 默认维度集（代码内置 5 维等权重）
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field, ValidationError, field_validator

from ai.llm_client import build_chat_openai
from ai.llm_task_name import LLMTaskName

logger = logging.getLogger(__name__)

# 代码可计算的 metric 枚举（第③层 compute_radar_values 实现）
METRICS = ("weighted_gpa", "stability", "top_subject", "pass_rate", "credit_load")

# 默认维度集（LLM 提案失败时的确定性降级）
DEFAULT_DIMENSIONS = [
    {"name": "学业水平", "weight": 0.3, "metric": "weighted_gpa", "rationale": "学分加权均分，反映整体学业表现"},
    {"name": "稳定性", "weight": 0.2, "metric": "stability", "rationale": "成绩波动程度，方差越低越稳定"},
    {"name": "优势科目", "weight": 0.2, "metric": "top_subject", "rationale": "最高分科目强度"},
    {"name": "基础扎实度", "weight": 0.15, "metric": "pass_rate", "rationale": "及格率，反映基础掌握程度"},
    {"name": "学业投入", "weight": 0.15, "metric": "credit_load", "rationale": "学分负荷，反映学业投入量"},
]


class DimensionProposal(BaseModel):
    name: str = Field(..., max_length=8, description="维度名（≤8 字）")
    weight: float = Field(..., ge=0, le=1, description="权重（合计≈1）")
    metric: str = Field(..., description="指标枚举")
    rationale: str = Field(..., max_length=50, description="理由（≤50 字）")

    @field_validator("metric")
    @classmethod
    def _metric_must_be_known(cls, v: str) -> str:
        if v not in METRICS:
            raise ValueError(f"未知 metric: {v}")
        return v


class DimensionDesignOutput(BaseModel):
    dimensions: list[DimensionProposal]
    overall_theme: str = Field(..., max_length=20, description="总体主题（≤20 字）")


def _prompt() -> str:
    path = Path(__file__).resolve().parent / "prompts" / "dimension_design.txt"
    return path.read_text(encoding="utf-8")


def build_dimension_llm() -> BaseChatModel:
    return build_chat_openai(
        temperature=0.3,
        max_tokens=1024,
        task_name=LLMTaskName.EVALUATION_DIMENSION_DESIGN,
    )


def default_dimensions() -> list[dict]:
    return [dict(d) for d in DEFAULT_DIMENSIONS]


def validate_proposal(raw: dict, axis_count: int) -> tuple[DimensionDesignOutput | None, list[str]]:
    """Pydantic 硬校验：结构 + 枚举 + 维度数。返回 (解析结果, 错误清单)。"""
    try:
        parsed = DimensionDesignOutput.model_validate(raw)
    except ValidationError as exc:
        return None, [f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}" for e in exc.errors()[:5]]
    if len(parsed.dimensions) != axis_count:
        return None, [f"维度数 {len(parsed.dimensions)} != 要求 {axis_count}"]
    total_weight = round(sum(d.weight for d in parsed.dimensions), 2)
    if abs(total_weight - 1.0) > 0.05:
        return None, [f"权重合计 {total_weight} != 1.0"]
    return parsed, []


def _extract_json(text: str) -> dict | None:
    """从 LLM 输出提取 JSON 对象（容忍围栏/前后缀）。"""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


async def design_dimensions(
    snapshot: dict,
    llm: BaseChatModel | None = None,
    *,
    axis_count: int = 5,
    timeout_seconds: float = 30.0,
) -> dict:
    """维度提案主流程：LLM 提案 → 硬校验 → 回灌重试 1 次 → 默认维度集。

    Returns:
        {"status": "llm"|"default", "dimensions": [...], "overall_theme": str, "errors": []}
    """
    from config import get_settings

    llm = llm or build_dimension_llm()
    prompt = _prompt()
    data = json.dumps(
        {
            "snapshot": snapshot,
            "required_dimension_count": axis_count,
            "allowed_metrics": list(METRICS),
        },
        ensure_ascii=False,
        indent=2,
    )
    content = f"{prompt}\n\n输入数据：\n```json\n{data}\n```"
    errors: list[str] = []
    usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
    for attempt in range(2):
        try:
            resp = await asyncio.wait_for(llm.ainvoke([HumanMessage(content=content)]), timeout=timeout_seconds)
            text = str(resp.content or "")
            um = getattr(resp, "usage_metadata", None) or {}
            usage["input_tokens"] += int(um.get("input_tokens", 0) or 0)
            usage["output_tokens"] += int(um.get("output_tokens", 0) or 0)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"LLM 调用失败: {str(exc)[:100]}")
            break
        raw = _extract_json(text)
        if raw is None:
            errors.append("输出不是合法 JSON")
            content += "\n\n上一轮输出不是合法 JSON，请只输出 JSON。"
            continue
        parsed, errs = validate_proposal(raw, axis_count)
        if parsed is not None:
            return {
                "status": "llm",
                "dimensions": [d.model_dump() for d in parsed.dimensions],
                "overall_theme": parsed.overall_theme,
                "errors": [],
                "usage": usage,
            }
        errors = errs
        content += f"\n\n上一轮校验失败：{errs}\n请修正后只输出 JSON。"
    return {
        "status": "default",
        "dimensions": default_dimensions(),
        "overall_theme": "综合学业表现",
        "errors": errors,
        "usage": usage,
    }
