# -*- coding: utf-8 -*-
"""即梦 4.0（火山引擎）HTTP 客户端封装 — 自建 MCP server 的底层能力。

- 签名：volcengine SDK（Region=cn-north-1, Service=cv）
- 提交：CVSync2AsyncSubmitTask → task_id
- 查询：CVSync2AsyncGetResult → status（in_queue/generating/done/not_found/expired）
- 错误码分类：审核码不可重试 / 限流可重试 / 后审核可重试一次

Phase: 2 (implemented)
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# 错误码分类（文档错误码表）
RETRYABLE_CODES = {50429, 50430, 50511, 50519}  # 限流/后审核可重试
NON_RETRYABLE_CODES = {50411, 50412, 50413, 50518, 50520, 50521, 50522, 50500, 50501}  # 审核/内部错误不可重试


class JimengError(Exception):
    """即梦调用错误（带码与可重试标记）。"""

    def __init__(self, code: int, message: str, *, retryable: bool = False, request_id: str = ""):
        self.code = code
        self.message = message
        self.retryable = retryable
        self.request_id = request_id
        super().__init__(f"[jimeng:{code}] {message}")


def _build_service():
    import os

    from config import get_settings
    from volcengine.visual.VisualService import VisualService

    s = get_settings()
    logger.info("jimeng _build_service ak=%s sk_len=%d env_ak=%s", s.volc_access_key[:8], len(s.volc_secret_key), os.environ.get("VOLC_ACCESS_KEY", "")[:8])
    service = VisualService()
    service.set_ak(s.volc_access_key)
    service.set_sk(s.volc_secret_key)
    return service


def _check_response(resp: dict) -> None:
    """业务返回校验：code != 10000 → 按错误码分类抛 JimengError。"""
    code = resp.get("code")
    if code == 10000:
        return
    message = str(resp.get("message", "unknown"))
    request_id = str(resp.get("request_id", ""))
    try:
        code_int = int(code)
    except (TypeError, ValueError):
        code_int = -1
    raise JimengError(
        code_int,
        message,
        retryable=code_int in RETRYABLE_CODES,
        request_id=request_id,
    )


def _parse_sdk_error(exc: Exception) -> JimengError:
    """volcengine SDK 对错误直接抛异常，消息形如 JSON（两种格式）：

    1. 业务错误：b'{"code":50430,"message":"...","request_id":"..."}'
    2. 通用错误：b'{"ResponseMetadata":{"RequestId":"...","Error":{"Code":"SignatureDoesNotMatch","Message":"..."}}}'

    统一解析提取 code/message/request_id，按错误码表分类。
    """
    import json
    import re

    msg = str(exc)
    match = re.search(r"b'(\{.*\})'", msg) or re.search(r"(\{.*\})", msg)
    if match:
        try:
            data = json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError, TypeError):
            data = None
        if data:
            # 业务错误格式
            if "code" in data:
                try:
                    code = int(data.get("code"))
                except (TypeError, ValueError):
                    code = -1
                return JimengError(
                    code,
                    str(data.get("message", msg))[:200],
                    retryable=code in RETRYABLE_CODES,
                    request_id=str(data.get("request_id", "")),
                )
            # 通用错误格式（ResponseMetadata）
            meta = data.get("ResponseMetadata") or {}
            error = meta.get("Error") or {}
            err_code = str(error.get("Code", "UnknownError"))
            request_id = str(meta.get("RequestId", ""))
            # 签名/参数类错误不可重试；其余保守标记可重试
            non_retryable_codes = {"SignatureDoesNotMatch", "InvalidAccessKey", "InvalidCredential", "RequestExpired"}
            return JimengError(
                -2 if err_code else -1,
                f"{err_code}: {error.get('Message', msg)}"[:200],
                retryable=err_code not in non_retryable_codes,
                request_id=request_id,
            )
    return JimengError(-1, msg[:200], retryable=True)


def submit_task(
    *,
    prompt: str,
    size: int | None = None,
    width: int | None = None,
    height: int | None = None,
    scale: float | None = None,
    force_single: bool | None = None,
    image_urls: list[str] | None = None,
) -> str:
    """提交文生图/图生图任务 → task_id。"""
    from config import get_settings

    s = get_settings()
    form: dict[str, Any] = {
        "req_key": s.jimeng_req_key,
        "prompt": prompt,
    }
    if size is not None:
        form["size"] = int(size)
    if width is not None and height is not None:
        form["width"] = int(width)
        form["height"] = int(height)
    if scale is not None:
        form["scale"] = float(scale)
    if force_single is not None:
        form["force_single"] = bool(force_single)
    if image_urls:
        form["image_urls"] = list(image_urls)

    service = _build_service()
    try:
        resp = service.cv_sync2async_submit_task(form)
    except Exception as exc:  # noqa: BLE001
        raise _parse_sdk_error(exc) from exc
    _check_response(resp)
    data = resp.get("data") or {}
    task_id = str(data.get("task_id", ""))
    if not task_id:
        raise JimengError(-2, "提交成功但未返回 task_id", request_id=str(resp.get("request_id", "")))
    return task_id


def query_task(task_id: str, req_json: dict | None = None) -> dict:
    """查询任务状态 → {status, image_urls, binary_data_base64, code, message}。

    默认请求 return_url=true（文档：返回图片链接 24h 有效）——否则服务端只回 base64。
    """
    from config import get_settings

    s = get_settings()
    form: dict[str, Any] = {"req_key": s.jimeng_req_key, "task_id": task_id}
    payload = dict(req_json or {})
    payload.setdefault("return_url", True)
    import json as _json

    form["req_json"] = _json.dumps(payload, ensure_ascii=False)

    service = _build_service()
    try:
        resp = service.cv_sync2async_get_result(form)
    except Exception as exc:  # noqa: BLE001
        raise _parse_sdk_error(exc) from exc
    _check_response(resp)
    data = resp.get("data") or {}
    return {
        "status": str(data.get("status", "unknown")),
        "image_urls": data.get("image_urls") or [],
        "binary_data_base64": data.get("binary_data_base64") or [],
        "code": resp.get("code"),
        "message": str(resp.get("message", "")),
    }


def poll_interval(attempt: int) -> float:
    """指数退避：min(base × 2^attempt, cap)。attempt 从 0 起。"""
    from config import get_settings

    s = get_settings()
    return min(s.jimeng_poll_interval_base * (2 ** attempt), s.jimeng_poll_interval_max)


def next_poll_after(task_id: str) -> float:
    """MCP get 工具的推荐下次查询间隔（基于已等待时间的自适应封顶）。"""
    return poll_interval(0)  # 默认返回基础间隔；实际递增由 client 侧维护


def poll_until_done(
    task_id: str,
    *,
    max_attempts: int | None = None,
    timeout: float | None = None,
    sleep_fn=None,
) -> dict:
    """完整轮询（供非 MCP 场景直用）：直到 done / 超时 / 尝试上限。

    Returns:
        {status, image_urls, attempts, elapsed}
    """
    from config import get_settings

    s = get_settings()
    max_attempts = max_attempts or s.jimeng_poll_max_attempts
    timeout = timeout or s.jimeng_poll_timeout
    sleep_fn = sleep_fn or time.sleep

    t0 = time.time()
    for attempt in range(max_attempts):
        result = query_task(task_id)
        status = result["status"]
        if status == "done":
            return {**result, "attempts": attempt + 1, "elapsed": round(time.time() - t0, 1)}
        if status in ("not_found", "expired"):
            raise JimengError(400, f"任务 {status}（可能已过期），请重新提交")
        if time.time() - t0 >= timeout:
            return {"status": "timeout", "image_urls": [], "attempts": attempt + 1, "elapsed": round(time.time() - t0, 1)}
        sleep_fn(poll_interval(attempt))
    return {"status": "attempts_exceeded", "image_urls": [], "attempts": max_attempts, "elapsed": round(time.time() - t0, 1)}
