# -*- coding: utf-8 -*-
"""记忆注入 — 仅会话首轮，独立 context 消息，绝不改写 req.message。

首轮判定：chat_sessions/chat_messages 无该 (session, user) 历史
（repo.get_or_create_session 返回新会话）→ 注入该 user 最近记忆。
注入内容作为独立消息（role=user 前缀「用户记忆：」），persist 不落此前缀。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def inject_memory_entries(repo, *, session_id: str, user_id: str) -> str | None:
    """返回待注入的记忆前缀消息；非首轮/匿名/无记忆 → None。"""
    if not user_id:
        return None
    session = repo.get_or_create_session(session_id, user_id)
    if session.get("message_count", 0) > 0:
        return None  # 续轮：不重复注入
    from config import get_settings

    settings = get_settings()
    entries = repo.list_memory_entries(user_id, limit=settings.memory_entries_per_user_limit, max_chars=2000)
    if not entries:
        return None
    lines = "\n".join(f"- {e['content']}" for e in entries)
    logger.info("memory injected", user_id=user_id, count=len(entries))
    return f"用户长期记忆：\n{lines}"
