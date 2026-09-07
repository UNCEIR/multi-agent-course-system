# -*- coding: utf-8 -*-
"""ApiEnvelopeMiddleware — 把非流式 /api/v1/* JSON 响应统一封装为 BaseResult 信封。

覆盖：
- 所有非流式 JSON 接口（auth/chat 同步/会话/知识库/评价查询/报告批次/健康检查等）
- 错误响应同样转信封：{code: <HTTP 状态码>, success: false, data: null, msg: <detail>}，
  保证「其他 http 码也能表现指定接口响应特性」

跳过（保持原样）：
- SSE 流式端点（StreamingResponse：chat/stream、recommend/stream、report、evaluation）
- 非 JSON 响应（如 /api/v1/report/download 二进制文件、/health 探活）
- 已封装为 BaseResult 的响应（避免二次封装）

注意：CORS 需在更外层（本中间件内层先处理 CORS 再到这里），封装时保留原响应头。
"""

from __future__ import annotations

import json

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from models.base_result import BaseResult, is_base_result

_ENVELOPE_KEYS = {"code", "success", "data", "msg"}


def _strip_body_length_headers(headers: dict) -> dict:
    """剔除会与新 body 冲突的长度/传输头，交由 JSONResponse 基于实际内容重新计算。

    Bug（2026-09-05）：内层 JSONResponse 的 headers 自带旧 content-length；信封包装后 body
    长度变化但 header 没更新 → h11 LocalProtocolError: Too much data for declared
    Content-Length → 客户端拿到 200 但空 body（IncompleteRead），chat sessions/messages 等
    所有非流式 JSON 端点全部受影响。
    """
    return {k: v for k, v in headers.items() if k.lower() not in ("content-length", "transfer-encoding")}


class ApiEnvelopeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path

        # 只处理 /api/v1/* 的非流式 JSON 响应
        if not path.startswith("/api/v1/"):
            return response
        if isinstance(response, StreamingResponse):
            return response
        ctype = response.headers.get("content-type", "")
        if "application/json" not in ctype:
            return response

        # 读取并解析 body
        body = b"".join([chunk async for chunk in response.body_iterator])
        try:
            payload = json.loads(body.decode("utf-8") or "null")
        except (ValueError, UnicodeDecodeError):
            # 解析失败：原样返回（不破坏非标准 JSON 响应）
            return Response(content=body, status_code=response.status_code, headers=dict(response.headers))

        if is_base_result(payload):
            return JSONResponse(content=payload, status_code=response.status_code, headers=_strip_body_length_headers(response.headers))

        if response.status_code < 400:
            enveloped = BaseResult.ok(payload).model_dump(mode="json")
        else:
            detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
            enveloped = BaseResult.from_http_exception(response.status_code, detail).model_dump(mode="json")

        return JSONResponse(content=enveloped, status_code=response.status_code, headers=_strip_body_length_headers(response.headers))
