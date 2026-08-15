# -*- coding: utf-8 -*-
"""雷达数值计算 — 反幻觉分层第③层（代码算值，LLM 给不出任何数字）。

metric 枚举 → 确定性计算并归一 0-100；未知 metric 拒绝该维度并记偏差。
"""

from __future__ import annotations

from .design_dimensions import METRICS


def _normalize(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """归一到 0-100（雷达图可比尺度）。"""
    if hi <= lo:
        return 50.0
    return round(max(lo, min(hi, value)) / hi * 100, 1)


def compute_radar_values(dimensions: list[dict], snapshot: dict) -> dict:
    """按维度提案计算雷达值（全部确定性，手算可核对）。

    Returns:
        {"values": [{"name", "metric", "value", "rationale"}], "rejected": [...]}
    """
    derived = snapshot.get("derived", {})
    values: list[dict] = []
    rejected: list[str] = []

    def _val(metric: str) -> float | None:
        if metric == "weighted_gpa":
            return _normalize(derived.get("weighted_avg") or derived.get("avg") or 0, 0, 100)
        if metric == "stability":
            # 方差越小越稳定：100 - 方差（方差以 10 分制刻度）
            return _normalize(100 - (derived.get("variance") or 0) * 10, 0, 100)
        if metric == "top_subject":
            return _normalize((derived.get("top_subject") or {}).get("score") or 0, 0, 100)
        if metric == "pass_rate":
            return _normalize((derived.get("pass_rate") or 0) * 100, 0, 100)
        if metric == "credit_load":
            # 学分负荷归一：假设满负荷 40 学分
            return _normalize(derived.get("total_credits") or 0, 0, 40)
        return None

    for dim in dimensions:
        metric = dim.get("metric", "")
        if metric not in METRICS:
            rejected.append(dim.get("name", metric))
            continue
        value = _val(metric)
        if value is None:
            rejected.append(dim.get("name", metric))
            continue
        values.append(
            {
                "name": dim.get("name", metric),
                "metric": metric,
                "value": value,
                "weight": dim.get("weight", 0),
                "rationale": dim.get("rationale", ""),
            }
        )
    return {"values": values, "rejected": rejected}
