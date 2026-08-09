# -*- coding: utf-8 -*-
"""用户上下文统一注入基座。

通过 ContextVar 把当前请求的用户 user_id 穿透到所有工具/插件，
避免依赖 LLM 从对话中猜测 user_id。工具统一调用 ``get_current_user_id()`` 读取。

写入时机：
- /api/v1/chat 与 /api/v1/chat/stream 用 ``user_context(req.user_id)`` 包裹 agent 调用
  （主机制，同一 event loop 内 100% 可靠）。
- UserContextMiddleware 作为补充：从 RunnableConfig.configurable.user_id 注入，
  让未来不经 chat 的入口（如 /recommend）也能统一受益。
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

_current_user_id: ContextVar[str] = ContextVar("current_user_id", default="")

# 匿名/未登录标识
ANONYMOUS_USER = ""

# 请求级 embedding 缓存：{(user_id, query): vector}
# 用 dict + Lock 而非 ContextVar，因为 asyncio.gather 的 child task 上下文独立，
# ContextVar 跨任务无法共享（子 agent 检验结论）。
_embedding_cache: dict[tuple[str, str], list[float]] = {}
_embedding_lock: asyncio.Lock | None = None


def get_current_user_id() -> str:
    """读取当前请求的用户 user_id；未登录返回空字符串。"""
    return _current_user_id.get()


def is_authenticated() -> bool:
    return bool(get_current_user_id())


def set_current_user_id(user_id: str) -> None:
    """设置当前 ContextVar（一般通过 user_context 上下文管理器使用）。"""
    _current_user_id.set(user_id or "")


@contextmanager
def user_context(user_id: str) -> Iterator[None]:
    """在 agent 调用期间注入用户上下文，退出后自动还原。

    Args:
        user_id: 当前登录用户 id；空字符串表示匿名。

    Example:
        with user_context(req.user_id):
            await agent.ainvoke(...)
    """
    token = _current_user_id.set(user_id or "")
    try:
        yield
    finally:
        _current_user_id.reset(token)


def get_embedding_lock() -> asyncio.Lock:
    """获取全局 embedding 缓存锁（线程安全）。"""
    global _embedding_lock
    if _embedding_lock is None:
        _embedding_lock = asyncio.Lock()
    return _embedding_lock


def get_embedding_cache(query: str) -> list[float] | None:
    """按 (user_id, query) 取缓存向量。"""
    return _embedding_cache.get((get_current_user_id(), query))


def set_embedding_cache(query: str, vector: list[float]) -> None:
    """写入 (user_id, query) 缓存向量，容量超限时清空最旧（简单 FIFO 兜底）。"""
    if len(_embedding_cache) >= 100:
        # 防无限增长：超 100 条时清空，重新缓存
        _embedding_cache.clear()
    _embedding_cache[(get_current_user_id(), query)] = vector


def reset_embedding_cache() -> None:
    """清空请求级 embedding 缓存（请求结束调用）。"""
    _embedding_cache.clear()
