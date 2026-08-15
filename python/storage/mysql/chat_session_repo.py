"""chat 会话/记忆仓储 — MySQL chat_sessions / chat_messages / chat_memory_entries。

表结构由 sql/init-db.sql 定义，本仓储只做 CRUD，不建表。
写纪律（pi 移植）：
- append-only：chat_messages 只增不删，seq 事务内原子自增分配（并发安全）
- (session_id, user_id) 复合键：防跨用户串会话
- content_hash 唯一索引：NFKC 归一精确去重（记忆条目）
"""

from __future__ import annotations

import asyncio
import hashlib
import unicodedata

import structlog
from sqlalchemy import text

from .base import MySQLRepository

logger = structlog.get_logger()


class ChatSessionRepository(MySQLRepository):
    """chat 会话记录 + 跨会话记忆条目 CRUD。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._locks: dict[str, asyncio.Lock] = {}

    def session_lock(self, session_id: str) -> asyncio.Lock:
        """per-session 并发锁（seq 分配与提取水位串行）。"""
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    # ── chat_sessions ─────────────────────────────────────────────────
    def get_or_create_session(self, session_id: str, user_id: str) -> dict:
        """以 (session_id, user_id) 复合键取会话；不匹配则新开（防串会话）。"""
        if not self.ping():
            return {"session_id": session_id, "user_id": user_id, "message_count": 0, "last_extracted_seq": 0}
        assert self._engine is not None
        with self._engine.begin() as conn:
            row = conn.execute(
                text("SELECT session_id, user_id, message_count, last_extracted_seq, status FROM chat_sessions WHERE session_id = :sid"),
                {"sid": session_id},
            ).mappings().first()
            if row and row["user_id"] == user_id:
                return dict(row)
            # 新开会话（不存在或 user 不匹配）
            conn.execute(
                text(
                    "INSERT INTO chat_sessions (session_id, user_id) VALUES (:sid, :uid) "
                    "ON DUPLICATE KEY UPDATE user_id = VALUES(user_id)"
                ),
                {"sid": session_id, "uid": user_id},
            )
        return {"session_id": session_id, "user_id": user_id, "message_count": 0, "last_extracted_seq": 0}

    def append_message(self, session_id: str, user_id: str, role: str, content: str, tool_calls_json=None, usage_json=None) -> int:
        """追加消息：事务内原子自增分配 seq + message_count。返回 seq。"""
        if not self.ping():
            return -1
        assert self._engine is not None
        with self._engine.begin() as conn:
            conn.execute(
                text("INSERT INTO chat_sessions (session_id, user_id) VALUES (:sid, :uid) ON DUPLICATE KEY UPDATE user_id = VALUES(user_id)"),
                {"sid": session_id, "uid": user_id},
            )
            row = conn.execute(
                text("SELECT message_count FROM chat_sessions WHERE session_id = :sid FOR UPDATE"),
                {"sid": session_id},
            ).mappings().first()
            seq = int(row["message_count"]) + 1 if row else 1
            conn.execute(
                text(
                    "INSERT INTO chat_messages (session_id, user_id, seq, role, content, tool_calls_json, usage_json) "
                    "VALUES (:sid, :uid, :seq, :role, :content, :tool_calls, :usage)"
                ),
                {
                    "sid": session_id,
                    "uid": user_id,
                    "seq": seq,
                    "role": role,
                    "content": content,
                    "tool_calls": tool_calls_json,
                    "usage": usage_json,
                },
            )
            conn.execute(
                text("UPDATE chat_sessions SET message_count = :cnt WHERE session_id = :sid"),
                {"cnt": seq, "sid": session_id},
            )
        return seq

    def list_messages(self, session_id: str, after_seq: int = 0, limit: int = 500) -> list[dict]:
        if not self.ping():
            return []
        assert self._engine is not None
        sql = text(
            "SELECT seq, role, content, tool_calls_json FROM chat_messages "
            "WHERE session_id = :sid AND seq > :after ORDER BY seq LIMIT :limit"
        )
        with self._engine.connect() as conn:
            rows = conn.execute(sql, {"sid": session_id, "after": after_seq, "limit": limit}).mappings().all()
        return [dict(r) for r in rows]

    def count_unextracted(self, session_id: str) -> int:
        """未提取消息数（message_count - last_extracted_seq）。"""
        if not self.ping():
            return 0
        assert self._engine is not None
        with self._engine.connect() as conn:
            row = conn.execute(
                text("SELECT message_count, last_extracted_seq FROM chat_sessions WHERE session_id = :sid"),
                {"sid": session_id},
            ).mappings().first()
        if not row:
            return 0
        return max(0, int(row["message_count"]) - int(row["last_extracted_seq"]))

    def get_extract_state(self, session_id: str) -> dict:
        """提取水位 + 上次失败时间戳（退避判断）。"""
        if not self.ping():
            return {"last_extracted_seq": 0, "last_failure_at": 0}
        assert self._engine is not None
        with self._engine.connect() as conn:
            row = conn.execute(
                text("SELECT message_count, last_extracted_seq, last_failure_at FROM chat_sessions WHERE session_id = :sid"),
                {"sid": session_id},
            ).mappings().first()
        if not row:
            return {"last_extracted_seq": 0, "last_failure_at": 0}
        return {"last_extracted_seq": int(row["last_extracted_seq"]), "last_failure_at": int(row["last_failure_at"] or 0)}

    def update_extracted_seq(self, session_id: str, seq: int) -> None:
        """提取水位推进（全部 upsert 成功后才调用，幂等）。"""
        if not self.ping():
            return
        assert self._engine is not None
        with self._engine.begin() as conn:
            conn.execute(
                text("UPDATE chat_sessions SET last_extracted_seq = :seq WHERE session_id = :sid AND last_extracted_seq < :seq"),
                {"seq": seq, "sid": session_id},
            )

    def mark_extract_failure(self, session_id: str) -> None:
        """记录提取失败时间戳（退避用）。"""
        if not self.ping():
            return
        assert self._engine is not None
        import time

        with self._engine.begin() as conn:
            conn.execute(
                text("UPDATE chat_sessions SET last_failure_at = :t WHERE session_id = :sid"),
                {"t": int(time.time()), "sid": session_id},
            )

    # ── chat_memory_entries ───────────────────────────────────────────
    def upsert_memory_entry(self, user_id: str, kind: str, content: str, source_session_id: str = "") -> None:
        """记忆条目 upsert：NFKC 归一 + md5 唯一键精确去重。"""
        if not self.ping():
            return
        assert self._engine is not None
        norm = unicodedata.normalize("NFKC", content).strip()
        if not norm:
            return
        digest = hashlib.md5(norm.encode("utf-8")).hexdigest()
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO chat_memory_entries (user_id, kind, content, content_hash, source_session_id) "
                    "VALUES (:uid, :kind, :content, :hash, :src) "
                    "ON DUPLICATE KEY UPDATE content = VALUES(content), source_session_id = VALUES(source_session_id)"
                ),
                {"uid": user_id, "kind": kind, "content": norm, "hash": digest, "src": source_session_id},
            )

    def list_memory_entries(self, user_id: str, limit: int = 50, max_chars: int = 2000) -> list[dict]:
        if not self.ping():
            return []
        assert self._engine is not None
        sql = text(
            "SELECT kind, content, source_session_id, updated_at FROM chat_memory_entries "
            "WHERE user_id = :uid ORDER BY updated_at DESC LIMIT :limit"
        )
        with self._engine.connect() as conn:
            rows = conn.execute(sql, {"uid": user_id, "limit": limit}).mappings().all()
        entries = [dict(r) for r in rows]
        # 总字符上限（注入容量保护）
        total = 0
        trimmed: list[dict] = []
        for e in entries:
            if total >= max_chars:
                break
            trimmed.append(e)
            total += len(str(e["content"]))
        return trimmed
