# -*- coding: utf-8 -*-
"""轻量认证（Phase 3.5）：注册 / 登录签发 HMAC token。

范围声明：登录态仅服务"注册登录 → 入口页"体验闭环；业务接口维持
user_id 参数临时口径（Java 身份体系落地时统一替换）。
"""

from __future__ import annotations

import re

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from auth.tokens import issue_token
from storage.mysql.user_repo import UserRepository

logger = structlog.get_logger()
router = APIRouter()

_USER_ID_RE = re.compile(r"^[0-9A-Za-z_-]{3,64}$")


class RegisterRequest(BaseModel):
    user_id: str = Field(..., min_length=3, max_length=64)
    name: str = Field(..., min_length=1, max_length=32)
    role: str = Field(default="student", pattern="^(student|teacher)$")
    password: str = Field(..., min_length=6, max_length=64)


class LoginRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=64)


def _validate_user_id(user_id: str) -> bool:
    return bool(_USER_ID_RE.fullmatch(user_id))


@router.post("/api/v1/auth/register")
async def register(req: RegisterRequest):
    """注册：学号/工号唯一；成功返回 {status, user}。"""
    if not _validate_user_id(req.user_id):
        raise HTTPException(status_code=400, detail="user_id 只能含字母/数字/_/-，长度 3-64")
    repo = UserRepository()
    try:
        ok = repo.create_user(
            user_id=req.user_id, name=req.name.strip(), role=req.role, password=req.password
        )
    except IntegrityError as exc:
        # 唯一键冲突（学号/工号已注册）
        logger.warning("auth.register.duplicate", user_id=req.user_id, error=str(exc)[:100])
        raise HTTPException(status_code=409, detail="该学号/工号已注册")
    except Exception as exc:  # noqa: BLE001
        # 连接中断等瞬态错误：与"已注册"区分，便于排障
        logger.warning("auth.register.db_error", user_id=req.user_id, error=str(exc)[:100])
        raise HTTPException(status_code=503, detail="注册服务暂不可用，请稍后重试")
    if not ok:
        raise HTTPException(status_code=503, detail="数据库不可用")
    logger.info("auth.register", user_id=req.user_id, role=req.role)
    return {"status": "ok", "user": {"user_id": req.user_id, "name": req.name.strip(), "role": req.role}}


@router.post("/api/v1/auth/login")
async def login(req: LoginRequest):
    """登录：密码校验通过 → 签发 HMAC token。"""
    repo = UserRepository()
    user = repo.verify_password(req.user_id, req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="学号/工号或密码错误")
    token = issue_token(user["user_id"], user["role"])
    logger.info("auth.login", user_id=user["user_id"], role=user["role"])
    return {"status": "ok", "token": token, "user": user}