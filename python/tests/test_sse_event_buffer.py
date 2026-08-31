# -*- coding: utf-8 -*-
"""EventBuffer + sse_with_id 单测（路 2 后端）。

覆盖：
- 单调递增 event_id
- replay_from(None / 0 / 中间 id / 过期 id) 行为
- Redis 不可用降级（append 仍返回 id，replay 返回空）
- max_size 环形裁剪
- sse_with_id 帧格式
- parse_last_event_id 严格解析
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest


# ── sse_with_id / parse_last_event_id 纯函数 ──

def test_sse_with_id_format():
    from services.sse_event_buffer import sse_with_id

    out = sse_with_id("text", '{"token":"hi"}', 42)
    # 标准 SSE 协议：id / event / data 三行 + 空行结束
    assert out == 'id: 42\nevent: text\ndata: {"token":"hi"}\n\n'


def test_parse_last_event_id_valid():
    from services.sse_event_buffer import parse_last_event_id

    assert parse_last_event_id("42") == 42
    assert parse_last_event_id("  123  ") == 123
    assert parse_last_event_id("0") == 0


def test_parse_last_event_id_invalid_returns_none():
    from services.sse_event_buffer import parse_last_event_id

    assert parse_last_event_id(None) is None
    assert parse_last_event_id("") is None
    assert parse_last_event_id("abc") is None
    assert parse_last_event_id("12.5") is None
    assert parse_last_event_id("12abc") is None


# ── EventBuffer（mock redis） ──

class FakeRedis:
    """极简 redis mock：只实现 EventBuffer 用到的接口。"""

    def __init__(self):
        self.lists: dict[str, list[str]] = {}
        self.ttls: dict[str, int] = {}

    async def lpush(self, key: str, value: str):
        self.lists.setdefault(key, []).insert(0, value)

    async def ltrim(self, key: str, start: int, end: int):
        # 保留 [start..end] 闭区间
        if key in self.lists:
            self.lists[key] = self.lists[key][start : end + 1]

    async def expire(self, key: str, ttl: int):
        self.ttls[key] = ttl

    async def lrange(self, key: str, start: int, end: int):
        if key not in self.lists:
            return []
        return self.lists[key][start : end + 1]

    async def delete(self, key: str):
        self.lists.pop(key, None)
        self.ttls.pop(key, None)

    async def ping(self):
        return True


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    # patch EventBuffer._connect 直接返回 fake 客户端
    from services import sse_event_buffer

    async def fake_connect(self):
        self._client = fake
        return fake

    monkeypatch.setattr(sse_event_buffer.EventBuffer, "_connect", fake_connect)
    return fake


@pytest.mark.asyncio
async def test_append_returns_monotonic_ids(fake_redis):
    from services.sse_event_buffer import EventBuffer

    buf = EventBuffer("thread_001")
    id1 = await buf.append("text", '{"i":1}')
    id2 = await buf.append("text", '{"i":2}')
    id3 = await buf.append("done", '{"ok":true}')
    assert id1 == 1
    assert id2 == 2
    assert id3 == 3
    assert id1 < id2 < id3


@pytest.mark.asyncio
async def test_replay_from_none_returns_empty(fake_redis):
    from services.sse_event_buffer import EventBuffer

    buf = EventBuffer("thread_002")
    await buf.append("text", '{"i":1}')
    assert await buf.replay_from(None) == []


@pytest.mark.asyncio
async def test_replay_from_zero_returns_empty(fake_redis):
    from services.sse_event_buffer import EventBuffer

    buf = EventBuffer("thread_003")
    await buf.append("text", '{"i":1}')
    assert await buf.replay_from(0) == []


@pytest.mark.asyncio
async def test_replay_from_middle_returns_later_events(fake_redis):
    from services.sse_event_buffer import EventBuffer

    buf = EventBuffer("thread_004")
    await buf.append("text", '{"i":1}')
    id2 = await buf.append("text", '{"i":2}')
    await buf.append("text", '{"i":3}')
    id4 = await buf.append("done", '{"ok":true}')

    out = await buf.replay_from(id2)
    # id3 + id4（id > id2）
    assert len(out) == 2
    assert out[0].event_id == id2 + 1
    assert out[1].event_id == id4
    assert out[0].event == "text"
    assert out[1].event == "done"


@pytest.mark.asyncio
async def test_replay_from_after_all_returns_empty(fake_redis):
    from services.sse_event_buffer import EventBuffer

    buf = EventBuffer("thread_005")
    await buf.append("text", '{"i":1}')
    await buf.append("done", '{"ok":true}')
    out = await buf.replay_from(999)
    assert out == []


@pytest.mark.asyncio
async def test_max_size_circular_trim(fake_redis):
    from services.sse_event_buffer import EventBuffer

    buf = EventBuffer("thread_006", max_size=3)
    for i in range(5):
        await buf.append("text", json.dumps({"i": i + 1}))
    # Redis 列表应保留最近 3 条（id 3 / 4 / 5）
    raw_list = fake_redis.lists[buf.key]
    assert len(raw_list) == 3
    # replay_from(2) 应返回 id 3 / 4 / 5
    out = await buf.replay_from(2)
    assert len(out) == 3
    assert [e.event_id for e in out] == [3, 4, 5]


@pytest.mark.asyncio
async def test_ttl_set_on_append(fake_redis):
    from services.sse_event_buffer import EventBuffer

    buf = EventBuffer("thread_007")
    await buf.append("text", '{"i":1}')
    assert buf.key in fake_redis.ttls
    assert fake_redis.ttls[buf.key] == EventBuffer.BUFFER_TTL_SECONDS


@pytest.mark.asyncio
async def test_clear_removes_key(fake_redis):
    from services.sse_event_buffer import EventBuffer

    buf = EventBuffer("thread_008")
    await buf.append("text", '{"i":1}')
    assert buf.key in fake_redis.lists
    await buf.clear()
    assert buf.key not in fake_redis.lists


# ── INCR 跨实例单调性 ──

class FakeRedisWithIncr(FakeRedis):
    """支持 INCR 命令的 fake redis。"""

    def __init__(self):
        super().__init__()
        self.counters: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def expire(self, key: str, ttl: int):
        # INCR 路径也要更新 ttl（与 lpush 同 key 互不干扰）
        self.ttls[key] = ttl


@pytest.mark.asyncio
async def test_incr_assigns_monotonic_ids_across_instances(monkeypatch):
    """不同 EventBuffer 实例（同 thread_id）append 时 id 必须单调递增。"""
    from services import sse_event_buffer

    fake = FakeRedisWithIncr()

    async def fake_connect(self):
        self._client = fake
        return fake

    monkeypatch.setattr(sse_event_buffer.EventBuffer, "_connect", fake_connect)

    # 第一个实例：append 2 条
    buf1 = sse_event_buffer.EventBuffer("thread_incr_001")
    id1 = await buf1.append("text", '{"i":1}')
    id2 = await buf1.append("text", '{"i":2}')
    # 第二个实例（同 thread_id，模拟下一个 chat 请求）
    buf2 = sse_event_buffer.EventBuffer("thread_incr_001")
    id3 = await buf2.append("text", '{"i":3}')
    id4 = await buf2.append("text", '{"i":4}')

    assert id1 == 1
    assert id2 == 2
    assert id3 == 3
    assert id4 == 4
    # INCR key 应被记录
    assert fake.counters["sse:counter:thread_incr_001"] == 4
    # 缓存 list 应有 4 条
    assert len(fake.lists["sse:events:thread_incr_001"]) == 4


@pytest.mark.asyncio
async def test_replay_from_skips_ids_leq_last_event_id(monkeypatch):
    """replay_from(N) 只返回 id > N 的事件；id <= N 的不返回。"""
    from services import sse_event_buffer

    fake = FakeRedisWithIncr()

    async def fake_connect(self):
        self._client = fake
        return fake

    monkeypatch.setattr(sse_event_buffer.EventBuffer, "_connect", fake_connect)

    buf = sse_event_buffer.EventBuffer("thread_incr_002")
    for _ in range(5):
        await buf.append("text", "{}")
    # replay_from(2) 应只返回 id 3 / 4 / 5
    out = await buf.replay_from(2)
    assert [e.event_id for e in out] == [3, 4, 5]


# ── Redis 不可用降级 ──

@pytest.mark.asyncio
async def test_redis_unavailable_degrades_gracefully(monkeypatch):
    """Redis 不可用时：append 仍递增本地计数器并返回 id；replay 返回空。"""
    from services import sse_event_buffer

    async def broken_connect(self):
        self._client = None
        return None

    monkeypatch.setattr(sse_event_buffer.EventBuffer, "_connect", broken_connect)

    buf = sse_event_buffer.EventBuffer("thread_009")
    id1 = await buf.append("text", '{"i":1}')
    id2 = await buf.append("done", '{"ok":true}')
    assert id1 == 1
    assert id2 == 2
    # replay 返回空（无可用缓存）
    assert await buf.replay_from(0) == []
    assert await buf.replay_from(id1) == []


@pytest.mark.asyncio
async def test_redis_append_failure_keeps_counter(monkeypatch):
    """Redis append 抛错时：本地计数器继续递增，返回的 id 仍单调。"""
    from services import sse_event_buffer

    class BrokenRedis:
        async def lpush(self, *a, **kw):
            raise ConnectionError("redis down")

        async def ltrim(self, *a, **kw):
            pass

        async def expire(self, *a, **kw):
            pass

        async def lrange(self, *a, **kw):
            return []

        async def delete(self, *a, **kw):
            pass

        async def ping(self):
            return True

    async def broken_connect(self):
        self._client = BrokenRedis()
        return self._client

    monkeypatch.setattr(sse_event_buffer.EventBuffer, "_connect", broken_connect)

    buf = sse_event_buffer.EventBuffer("thread_010")
    id1 = await buf.append("text", '{"i":1}')
    id2 = await buf.append("text", '{"i":2}')
    id3 = await buf.append("done", '{"ok":true}')
    assert (id1, id2, id3) == (1, 2, 3)


# ── BufferedEvent 不可变 ──

def test_buffered_event_is_frozen():
    from services.sse_event_buffer import BufferedEvent

    ev = BufferedEvent(event_id=1, event="text", payload="{}")
    with pytest.raises(Exception):  # FrozenInstanceError 或 AttributeError
        ev.event_id = 999
