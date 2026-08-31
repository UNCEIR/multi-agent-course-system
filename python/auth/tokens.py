"""轻量认证 token 工具 — HMAC-SHA256 签名（Phase 3.5 临时口径）。

payload = {user_id, role, exp}；签名 = base64url(payload).signature。
业务接口仍维持 user_id 参数临时口径（Java 身份体系落地时统一替换）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from config import get_settings


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload_b64: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()


def issue_token(user_id: str, role: str) -> str:
    """签发 token：payload(uid/role/exp).签名。"""
    settings = get_settings()
    ttl = settings.auth_token_ttl_seconds
    payload = {"user_id": user_id, "role": role, "exp": int(time.time()) + ttl}
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{payload_b64}.{_sign(payload_b64, settings.auth_token_secret)}"


def verify_token(token: str) -> dict | None:
    """校验 token：签名与过期。有效返回 {user_id, role}。"""
    settings = get_settings()
    try:
        payload_b64, signature = token.split(".", 1)
        # 恒定时间比较，防时序侧信道
        if not hmac.compare_digest(_sign(payload_b64, settings.auth_token_secret), signature):
            return None
        payload = json.loads(_unb64url(payload_b64))
        if int(payload.get("exp", 0)) < time.time():
            return None
        return {"user_id": str(payload["user_id"]), "role": str(payload.get("role", "student"))}
    except (ValueError, KeyError, json.JSONDecodeError):
        return None