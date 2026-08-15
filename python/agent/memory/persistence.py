# -*- coding: utf-8 -*-
"""chat 写纪律（pi 移植）：turn 消息逐条落库 + 匿名跳过 + 尽力而为。

- persist_turn：user 消息 + assistant 消息（含工具调用）逐条 append，
  每条独立提交（中断不丢已落）；MySQL 不可用 → 告警不阻塞对话
- 崩溃保守：seq 原子自增，重复调用幂等由调用方控制（每 turn 只调一次）
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def _content_of(message) -> str:
    if isinstance(message, dict):
        return str(message.get("content", "") or "")
    return str(getattr(message, "content", "") or "")


def _tool_calls_of(message) -> str | None:
    """assistant 消息的工具调用（审计用）→ JSON 字符串。"""
    calls = getattr(message, "tool_calls", None)
    if calls:
        try:
            return json.dumps([{"name": c.get("name", ""), "args": c.get("args", {})} for c in calls], ensure_ascii=False)
        except Exception:  # noqa: BLE001
            return None
    return None


async def persist_turn(
    repo,
    *,
    session_id: str,
    user_id: str,
    user_msg: str,
    assistant_msgs: list | None = None,
) -> None:
    """把一轮对话落库（user + assistant 逐条；匿名 user 跳过）。"""
    if not user_id:
        logger.debug("persist_turn skipped (anonymous user)")
        return
    try:
        lock = repo.session_lock(session_id)
        async with lock:
            repo.append_message(session_id, user_id, "user", user_msg)
            for msg in assistant_msgs or []:
                role = "assistant"
                tool_calls = _tool_calls_of(msg)
                repo.append_message(
                    session_id,
                    user_id,
                    role,
                    _content_of(msg),
                    tool_calls_json=tool_calls,
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("persist_turn failed (best effort): %s", exc)
