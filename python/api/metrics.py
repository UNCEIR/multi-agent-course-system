# -*- coding: utf-8 -*-
"""指标端点（Phase 4 C2）。

- GET /metrics → Prometheus 文本（供 prometheus 抓取，豁免 SSE / 信封）
- /api/v1/metrics JSON 契约冻结见 health.py（统一信封 {code, success, data, msg}，
  data: {agents, business, generated_at}）
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse, Response

from observability.prometheus import content_type, render

router = APIRouter()


@router.get("/metrics")
async def metrics() -> Response:
    """Prometheus 文本格式（generate_latest）。"""
    return PlainTextResponse(render().decode("utf-8"), media_type=content_type())
