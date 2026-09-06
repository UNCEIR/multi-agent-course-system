# -*- coding: utf-8 -*-
"""规则式 monitor agent（Phase 4 P1-C / C3）。

确定性规则（非 LLM）：扫描指标退化 → 告警（落 business_events）+ 调优建议。
- 阈值表：每规则（指标/窗口/阈值/严重级）
- 数据源：metrics_collector.get_agent_stats() + business_events
- 调度：周期扫描（调用方控制频率；本类无自循环）
- 告警去重：同 code+agent 短窗（默认 300s）只发一次
"""

from __future__ import annotations

import time
from typing import Any

# 阈值表：code / 指标口径 / 阈值 / 严重级 / 说明
RULES: list[dict] = [
    {"code": "success_rate_drop", "metric": "success_rate", "threshold": 0.8, "window": 60, "severity": "warning"},
    {"code": "avg_latency_high", "metric": "avg_latency_ms", "threshold": 30000, "window": 60, "severity": "warning"},
    {"code": "error_spike", "metric": "error_count", "threshold": 10, "window": 60, "severity": "critical"},
]

QUOTA_ERROR_MARKERS = ("quota", "rate limit", "insufficient_quota", "429")

_SUGGESTIONS = {
    "success_rate_drop": ["检查 LLM 配额/上游可用性", "kb 检索 top_k 调低以减少无效召回", "语义缓存阈值可下调（0.95→0.9）扩大命中"],
    "avg_latency_high": ["确认是否触发 compaction 长摘要", "分块策略检查（chunk 过大拖慢解析）", "rerank 权重/候选集过大检查"],
    "error_spike": ["查看 business_events 聚合 error code", "工具熔断状态检查（circuit_breaker）", "外部依赖（tavily/即梦/MCP）可用性检查"],
    "quota_error": ["LLM 配额耗尽：降级 --judge-sample / 缓存复用", "换便宜模型（--judge-model）", "等待配额恢复或升级"],
}


class MonitorAgent:
    """规则式 monitor：scan() 返回新告警（已按 code+agent 去重）。"""

    def __init__(self, *, metrics_collector: Any = None, dedupe_window: float = 300.0):
        self._metrics = metrics_collector
        self._dedupe_window = dedupe_window
        self._last_alert: dict[str, float] = {}

    def _dedupe(self, key: str) -> bool:
        now = time.time()
        if now - self._last_alert.get(key, 0.0) < self._dedupe_window:
            return False
        self._last_alert[key] = now
        return True

    def suggest(self, code: str) -> list[str]:
        return list(_SUGGESTIONS.get(code, ["人工排查"]))

    def to_config_patch(self, alert: dict) -> dict | None:
        """告警 → 建议配置变更（Phase 4 G3：仅输出供人工确认，不自动改生产）。"""
        code = alert.get("code")
        if code == "success_rate_drop":
            return {"course_recall_cache_semantic_threshold": 0.9, "note": "下调语义缓存阈值扩大命中（人工确认后改 .env）"}
        if code == "avg_latency_high":
            return {"agent_compaction_keep_tokens": 30000, "note": "压缩保留 token 上调以降频（人工确认后改 .env）"}
        if code == "quota_error":
            return {"judge_sample": 3, "note": "judge 采样降级 + 缓存复用（人工确认）"}
        return None

    def scan(self) -> list[dict]:
        """扫描当前指标，返回新告警列表（已去重）。"""
        alerts: list[dict] = []
        if self._metrics is None:
            return alerts
        try:
            stats = self._metrics.get_agent_stats()
        except Exception:  # noqa: BLE001
            return alerts
        for agent, m in stats.items():
            # 配额类 error（类型化错误码，D7）不设样本门槛：1 次即告警（严重级）
            for err in m.get("recent_errors", []) or []:
                low = str(err).lower()
                if any(marker in low for marker in QUOTA_ERROR_MARKERS):
                    self._emit(
                        alerts,
                        {"code": "quota_error", "metric": "quota", "threshold": 1, "window": 60, "severity": "critical"},
                        agent,
                        f"quota error: {str(err)[:80]}",
                    )
                    break
            call_count = int(m.get("call_count", m.get("total_calls", 0)) or 0)
            if call_count < 3:
                continue  # 样本不足不告警（常规规则）
            success_rate = float(m.get("success_rate", 1.0))  # 注意：0.0 是合法值，不能用 or 兜底
            for rule in RULES:
                metric = rule["metric"]
                if metric == "success_rate" and success_rate < float(rule["threshold"]):
                    self._emit(alerts, rule, agent, f"success_rate={success_rate:.2f}")
                elif metric == "avg_latency_ms" and float(m.get("avg_latency_ms", 0) or 0) > float(rule["threshold"]):
                    self._emit(alerts, rule, agent, f"avg_latency_ms={m.get('avg_latency_ms')}")
                elif metric == "error_count" and len(m.get("recent_errors", [])) > int(rule["threshold"]):
                    self._emit(alerts, rule, agent, f"errors={len(m.get('recent_errors', []))}")
        return alerts

    def _emit(self, alerts: list[dict], rule: dict, agent: str, detail: str) -> None:
        code = rule["code"]
        key = f"{code}:{agent}"
        if not self._dedupe(key):
            return
        alerts.append(
            {
                "code": code,
                "agent": agent,
                "severity": rule["severity"],
                "detail": detail,
                "suggestions": self.suggest(code),
                "ts": time.time(),
            }
        )
