# -*- coding: utf-8 -*-
"""evaluation 编排门面 — 五层反幻觉管线（端点直管，不建 agent 壳）。

层① 快照（get_academic_snapshot，确定性唯一事实源）
层② 维度提案（design_dimensions，LLM + Pydantic 硬校验 → 默认维度集）
层③ 雷达数值（compute_radar_values，代码算值）
层④ 评语（generate_comment，LLM + 数值引用核验硬闸 → 规则化兜底）
层⑤ 链路兜底（每层独立 CircuitBreaker acall；失败走确定性降级）

SSE 事件：stage / radar / comment_token / done / error；完成自动落 evaluation_records。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from tools.evaluation.compute_radar_values import compute_radar_values
from tools.evaluation.design_dimensions import design_dimensions
from tools.evaluation.generate_comment import generate_comment
from tools.evaluation.get_academic_snapshot import build_snapshot

logger = logging.getLogger(__name__)


def _merge_usage(total: dict, add: dict | None) -> dict:
    """聚合两段 LLM 调用的 token 消耗。"""
    add = add or {}
    return {
        "input_tokens": total.get("input_tokens", 0) + int(add.get("input_tokens", 0) or 0),
        "output_tokens": total.get("output_tokens", 0) + int(add.get("output_tokens", 0) or 0),
    }


class _Breaker:
    """极简熔断（独立实例 per 层；失败连续 N 次 → 熔断直通降级）。"""

    def __init__(self, failure_threshold: int = 3, reset_timeout: float = 30.0):
        self._failures = 0
        self._opened_at = 0.0
        self.threshold = failure_threshold
        self.reset_timeout = reset_timeout

    def _is_open(self) -> bool:
        import time

        if self._failures >= self.threshold:
            if time.monotonic() - self._opened_at > self.reset_timeout:
                self._failures = 0
            else:
                return True
        return False

    async def acall(self, coro_factory):
        if self._is_open():
            raise RuntimeError("circuit open")
        try:
            result = await coro_factory()
            self._failures = 0
            return result
        except Exception as exc:  # noqa: BLE001
            import time

            self._failures += 1
            if self._failures >= self.threshold:
                self._opened_at = time.monotonic()
            raise exc


async def stream_evaluation(
    *,
    target_user_id: str,
    comment_type: str,
    generated_by: str = "",
    out_queue: asyncio.Queue,
) -> None:
    """五层管线 → 事件进 out_queue（stage/radar/comment_token/done/error）。"""
    from agent.main.context import user_context

    breaker_dim = _Breaker()
    breaker_comment = _Breaker()

    async def _emit(event: str, data: dict) -> None:
        with contextlib.suppress(Exception):
            out_queue.put_nowait((event, data))

    try:
        # ── 层① 快照（user_id 从 context 注入）───────────────────────
        await _emit("stage", {"stage": "snapshot", "detail": "读取学业快照"})
        with user_context(target_user_id):
            snapshot = await asyncio.to_thread(build_snapshot)
        if "code" in snapshot:
            await _emit("error", {"code": snapshot["code"], "message": snapshot.get("hint", "无成绩单数据")})
            return

        # ── 层② 维度提案 ─────────────────────────────────────────────
        await _emit("stage", {"stage": "dimensions", "detail": "设计评价维度"})
        from config import get_settings

        axis_count = get_settings().evaluation_radar_axis_count
        usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
        try:
            proposal = await breaker_dim.acall(lambda: design_dimensions(snapshot, axis_count=axis_count))
            usage = _merge_usage(usage, proposal.get("usage"))
        except Exception:  # noqa: BLE001
            from tools.evaluation.design_dimensions import default_dimensions

            proposal = {"status": "default", "dimensions": default_dimensions(), "overall_theme": "综合学业表现", "errors": ["熔断降级"]}
        status = "fallback" if proposal["status"] != "llm" else "generated"

        # ── 层③ 雷达数值（代码，确定性）──────────────────────────────
        await _emit("stage", {"stage": "radar", "detail": "计算雷达数值"})
        radar = compute_radar_values(proposal["dimensions"], snapshot)
        radar_payload = {
            "dimensions": radar["values"],
            "rejected": radar["rejected"],
            "overall_theme": proposal["overall_theme"],
            "status": proposal["status"],
        }
        await _emit("radar", {"target_user_id": target_user_id, **radar_payload})

        # ── 层④ 评语（数值核验硬闸）──────────────────────────────────
        await _emit("stage", {"stage": "comment", "detail": "生成评语"})
        tokens: list[str] = []

        def _on_token(text: str) -> None:
            for ch in text:
                tokens.append(ch)

        try:
            comment, cstatus, comment_usage = await breaker_comment.acall(
                lambda: generate_comment(snapshot, radar, comment_type, on_token=_on_token)
            )
            usage = _merge_usage(usage, comment_usage)
        except Exception:  # noqa: BLE001
            from tools.evaluation.generate_comment import rule_based_comment

            comment = rule_based_comment(snapshot, radar, comment_type)
            cstatus = "rule"
        if cstatus != "llm":
            status = "fallback"
        # token 流式回放（LLM 路径）
        for ch in tokens:
            await _emit("comment_token", {"token": ch})

        # ── 落库（教师端生成 → 学生端同步）───────────────────────────
        try:
            from agent import runtime

            evaluation_id = await asyncio.to_thread(
                runtime.evaluation_repo.insert,
                target_user_id=target_user_id,
                comment_type=comment_type,
                radar=radar_payload,
                comment=comment,
                status=status,
                generated_by=generated_by,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("evaluation insert failed: %s", exc)
            evaluation_id = None

        await _emit(
            "done",
            {
                "evaluation_id": evaluation_id,
                "target_user_id": target_user_id,
                "comment_type": comment_type,
                "radar": radar_payload,
                "comment": comment,
                "status": status,
                "comment_status": cstatus,
                "usage": usage,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("evaluation stream failed")
        await _emit("error", {"code": type(exc).__name__.upper(), "message": str(exc)})
