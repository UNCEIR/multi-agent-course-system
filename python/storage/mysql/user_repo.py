"""轻量认证用户仓储 — MySQL users 表。

注册/登录用：user_id（学号/工号）唯一，角色 student | teacher。
密码 = sha256(salt + password)，salt 随机生成（每用户独立）。
"""

from __future__ import annotations

import hashlib
import os

import structlog
from sqlalchemy import text

from .base import MySQLRepository

logger = structlog.get_logger()


def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


def new_salt() -> str:
    return os.urandom(16).hex()


class UserRepository(MySQLRepository):
    """users 表 CRUD（注册 / 登录校验）。"""

    def create_user(self, *, user_id: str, name: str, role: str, password: str) -> bool:
        """注册用户；user_id 已存在返回 False。"""
        if not self.ping():
            return False
        assert self._engine is not None
        salt = new_salt()
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (user_id, name, role, password_hash, salt) "
                    "VALUES (:uid, :name, :role, :hash, :salt)"
                ),
                {
                    "uid": user_id,
                    "name": name,
                    "role": role if role in ("student", "teacher") else "student",
                    "hash": hash_password(password, salt),
                    "salt": salt,
                },
            )
        return True

    def get_user(self, user_id: str) -> dict | None:
        if not self.ping():
            return None
        assert self._engine is not None
        with self._engine.connect() as conn:
            row = conn.execute(
                text("SELECT user_id, name, role, password_hash, salt FROM users WHERE user_id = :uid"),
                {"uid": user_id},
            ).mappings().first()
        return dict(row) if row else None

    def verify_password(self, user_id: str, password: str) -> dict | None:
        """登录校验：密码正确返回用户信息，否则 None。"""
        user = self.get_user(user_id)
        if user is None:
            return None
        if hash_password(password, user["salt"]) != user["password_hash"]:
            return None
        return {"user_id": user["user_id"], "name": user["name"], "role": user["role"]}