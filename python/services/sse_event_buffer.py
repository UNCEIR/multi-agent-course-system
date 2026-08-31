# -*- coding: utf-8 -*-
"""SSE 事件环形缓冲 + Last-Event-ID 重连支持（路 2）。

设计动机
--------
- SSE 默认无续传协议，客户端断线后只能重新发起请求并接受重复生成代价。
- 本模块实现 RFC-9457 风格的 Last-Event-ID 续传：
  - 服务端每次 yield 事件时分配递增的 `event_id`（按 thread_id 单调递增），
    并写入 `id:` 字段；同一 thread_id 缓存最近 N 条事件到 Redis 环形缓冲。
  - 客户端重连时通过 `Last-Event-ID` HTTP header 告知最后收到的事件 id；
    服务端从缓存中回放缺失的事件，再继续后续生成。

关键不变量
----------
- 同一 thread_id 串行生成：event_id 单调递增；缓存只追加，不修改既有条目。
- TTL：缓存 key 在 stream 完成后 30 分钟内继续保留（足够客户端短重连）。
- 容错：Redis 不可用时降级为不缓存（不影响正常生成，仅失去续传能力）。

使用模式
--------
每个 SSE 端点的 `_generate()` 包装一个 EventBuffer 实例：

    async def _generate():
        buf = EventBuffer(thread_id=session_id)
        async for event in upstream_generator:
            payload = json.dumps(event["data"], ensure_ascii=False)
            event_id = await buf.append(event["event"], payload)
            yield _sse_with_id(event["event"], payload, event_id)
            if event["event"] in ("done", "error"):
                break

    async def _generate_resumable(req: Request, ...):
        buf = EventBuffer(thread_id=session_id)
        last_id = req.headers.get("Last-Event-ID")
        async for event_id, event, payload in buf.replay(last_id):
            yield _sse_with_id(event, payload, event_id)
        # 继续正常生成...
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import AsyncIterator

import redis.asyncio as redis

from config import get_settings
from storage.redis.feature_repo import RedisFeatureRepository


@dataclass(frozen=True)
class BufferedEvent:
    """缓冲中的单条事件（event_id 单调递增）。"""

    event_id: int
    event: str
    payload: str  # 已经 json.dumps 后的字符串（避免重复序列化）


class _RedisLike:
    """最小化 redis 客户端接口（用于测试 mock）。"""

    async def lpush(self, *args, **kwargs):  # noqa: D401
        ...

    async def ltrim(self, *args, **kwargs): ...
    async def expire(self, *args, **kwargs): ...
    async def lrange(self, *args, **kwargs): ...
    async def delete(self, *args, **kwargs): ...


class EventBuffer:
    """SSE 事件缓冲：append + replay_from(last_event_id)。

    Redis 不可用时降级为 noop（replay_from 永远返回空，append 直接返回递增 id）。
    """

    KEY_PREFIX = "sse:events:"
    COUNTER_PREFIX = "sse:counter:"  # 全局自增 key，保证跨请求 id 唯一
    BUFFER_TTL_SECONDS = 1800  # stream 结束后保留 30 分钟，足够客户端短重连
    COUNTER_TTL_SECONDS = 3600  # counter 比 buffer TTL 长（防过期被裁后再 append 重复）

    def __init__(
        self,
        thread_id: str,
        *,
        max_size: int | None = None,
    ):
        self.thread_id = thread_id
        self.max_size = max_size or get_settings().sse_event_buffer_size
        self._client: redis.Redis | None = None
        self._counter = 0  # 进程内单调递增计数器（Redis 不可用时仍能分配 id）

    async def _connect(self) -> redis.Redis | None:
        if self._client is not None:
            return self._client
        try:
            settings = get_settings()
            client = redis.from_url(settings.redis_url, decode_responses=True)
            await client.ping()
            self._client = client
            return client
        except Exception:  # noqa: BLE001
            self._client = None
            return None

    @property
    def key(self) -> str:
        return f"{self.KEY_PREFIX}{self.thread_id}"

    @property
    def counter_key(self) -> str:
        return f"{self.COUNTER_PREFIX}{self.thread_id}"

    async def append(self, event: str, payload: str) -> int:
        """追加一条事件，返回分配的 event_id。

        event_id 通过 Redis `INCR` 全局自增保证跨实例/跨请求单调；
        Redis 不可用时仅递增本地计数器（仍能 SSE 输出，但跨请求不保证唯一）。
        """
        client = await self._connect()
        if client is not None:
            try:
                # INCR 保证跨进程/跨重启单调递增；EXPIRE 防止 key 永久驻留
                event_id = int(await client.incr(self.counter_key))
                await client.expire(self.counter_key, self.COUNTER_TTL_SECONDS)
            except Exception as exc:  # noqa: BLE001
                logging.warning(
                    "sse_event_buffer.incr_failed thread_id=%s error=%s",
                    self.thread_id,
                    exc,
                )
                # INCR 失败时回退到本地计数器
                self._counter += 1
                event_id = self._counter
        else:
            # Redis 完全不可用：降级本地计数器（同一进程内仍单调）
            self._counter += 1
            event_id = self._counter

        if client is not None:
            try:
                # 用 lpush + ltrim 实现环形缓冲：左边追加、右边裁剪
                await client.lpush(self.key, json.dumps(
                    {"id": event_id, "event": event, "payload": payload},
                    ensure_ascii=False,
                ))
                await client.ltrim(self.key, 0, self.max_size - 1)
                await client.expire(self.key, self.BUFFER_TTL_SECONDS)
            except Exception as exc:  # noqa: BLE001
                logging.warning(
                    "sse_event_buffer.append_failed thread_id=%s event_id=%s error=%s",
                    self.thread_id,
                    event_id,
                    exc,
                )
        return event_id

    async def replay_from(self, last_event_id: int | None) -> list[BufferedEvent]:
        """从 Redis 回放 last_event_id 之后的所有事件。

        - last_event_id 为 None / 0：返回空列表（客户端从未收到事件，无可回放）。
        - Redis 不可用：返回空列表（降级，不阻塞新生成）。
        - Redis 可用：从右侧 (lrange -N..-1) 取最近 max_size 条，
          过滤出 id > last_event_id，按 id 升序返回。
        """
        if last_event_id is None or last_event_id <= 0:
            return []
        client = await self._connect()
        if client is None:
            return []
        try:
            raws = await client.lrange(self.key, 0, self.max_size - 1)
        except Exception as exc:  # noqa: BLE001
            logging.warning(
                "sse_event_buffer.replay_failed thread_id=%s last_event_id=%s error=%s",
                self.thread_id,
                last_event_id,
                exc,
            )
            return []
        out: list[BufferedEvent] = []
        for raw in raws:
            try:
                item = json.loads(raw)
                if item.get("id", 0) > last_event_id:
                    out.append(BufferedEvent(
                        event_id=int(item["id"]),
                        event=str(item["event"]),
                        payload=str(item["payload"]),
                    ))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        out.sort(key=lambda e: e.event_id)
        return out

    async def clear(self) -> None:
        """显式清空（用于测试 / 调试）。"""
        client = await self._connect()
        if client is None:
            return
        try:
            await client.delete(self.key)
        except Exception:  # noqa: BLE001
            pass


# ── 公共 SSE 工具 ──────────────────────────────────────────────

def sse_with_id(event: str, payload: str, event_id: int) -> str:
    """带 `id:` 字段的 SSE 帧（SSE 标准协议）。"""
    return f"id: {event_id}\nevent: {event}\ndata: {payload}\n\n"


def parse_last_event_id(header_value: str | None) -> int | None:
    """解析 Last-Event-ID HTTP header；非法值返回 None（视同无续传）。"""
    if not header_value:
        return None
    try:
        return int(header_value.strip())
    except (ValueError, AttributeError):
        return None


__all__ = [
    "BufferedEvent",
    "EventBuffer",
    "parse_last_event_id",
    "sse_with_id",
]


# 兼容旧引用：保留 RedisFeatureRepository 的导出（避免破坏现有导入）
_redis_repo_helper = RedisFeatureRepository  # noqa: F841
