# -*- coding: utf-8 -*-
"""chat 记忆机制测试：写纪律/匿名跳过、提取触发与幂等、注入仅首轮。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.memory.extractor import MemoryExtractWorker, maybe_extract
from agent.memory.injector import inject_memory_entries
from agent.memory.persistence import persist_turn


class _FakeRepo:
    """内存版仓储替身（模拟 DB 行为）。"""

    def __init__(self):
        self.sessions: dict[str, dict] = {}
        self.messages: dict[str, list] = {}
        self.entries: list[dict] = []
        self.extract_calls = 0
        self.extract_should_fail = False
        self.last_extracted = 0

    def session_lock(self, sid):
        return _NoopLock()

    def get_or_create_session(self, sid, uid):
        key = (sid, uid)
        if key not in self.sessions:
            self.sessions[key] = {"message_count": 0}
        return {"message_count": self.sessions[key]["message_count"]}

    def append_message(self, sid, uid, role, content, tool_calls_json=None, usage_json=None):
        self.sessions.setdefault((sid, uid), {"message_count": 0})
        self.messages.setdefault(sid, []).append({"role": role, "content": content, "seq": len(self.messages.get(sid, [])) + 1})
        self.sessions[(sid, uid)]["message_count"] = len(self.messages[sid])
        return len(self.messages[sid])

    def list_messages(self, sid, after_seq=0, limit=500):
        return [m for m in self.messages.get(sid, []) if m["seq"] > after_seq][:limit]

    def count_unextracted(self, sid):
        return max(0, len(self.messages.get(sid, [])) - self.last_extracted)

    def get_extract_state(self, sid):
        return {"last_extracted_seq": self.last_extracted, "last_failure_at": 0}

    def update_extracted_seq(self, sid, seq):
        self.last_extracted = max(self.last_extracted, seq)

    def mark_extract_failure(self, sid):
        pass

    def upsert_memory_entry(self, uid, kind, content, src="", agent_name="main_agent", expires_at=None):
        self.entries.append({"kind": kind, "content": content})

    def replace_memory_entries(self, uid, delete_contents, upsert_entries, agent_name="main_agent", upsert_expires=None):
        drop = set(delete_contents or [])
        self.entries = [e for e in self.entries if e["content"] not in drop]
        for kind, content in upsert_entries or []:
            self.entries.append({"kind": kind, "content": content})

    def list_memory_entries(self, uid, limit=50, max_chars=2000, agent_name="main_agent"):
        return list(self.entries[:limit])


class _NoopLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _settings(**kw):
    s = MagicMock()
    s.memory_extract_threshold_messages = 20
    s.memory_extract_max_messages = 200
    s.memory_extract_retry_after_seconds = 600
    s.memory_entries_per_user_limit = 50
    s.memory_extract_min_interval_seconds = 0
    s.memory_extract_disclosure_signal_enabled = False
    for k, v in kw.items():
        setattr(s, k, v)
    return s


@pytest.mark.unit
async def test_persist_turn_anonymous_skipped():
    repo = _FakeRepo()
    await persist_turn(repo, session_id="s1", user_id="", user_msg="hi", assistant_msgs=[])
    assert repo.messages == {}


@pytest.mark.unit
async def test_persist_turn_writes_user_and_assistant():
    repo = _FakeRepo()
    await persist_turn(repo, session_id="s1", user_id="u1", user_msg="你好", assistant_msgs=[{"content": "你好！", "role": "assistant"}])
    assert len(repo.messages["s1"]) == 2
    assert repo.messages["s1"][0] == {"role": "user", "content": "你好", "seq": 1}


@pytest.mark.unit
async def test_extract_threshold_and_idempotency():
    """达阈值触发提取；提取后水位推进 → 不再重复提取（幂等）。"""
    repo = _FakeRepo()
    for i in range(20):
        repo.append_message("s1", "u1", "user" if i % 2 == 0 else "assistant", f"msg{i}")

    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=MagicMock(content='{"entries": [{"kind": "fact", "content": "用户喜欢编程"}]}')
    )
    with patch("agent.memory.extractor.build_extract_llm", return_value=llm), patch(
        "config.get_settings", return_value=_settings()
    ):
        ran = await maybe_extract(repo, session_id="s1", user_id="u1")
        assert ran is True
        assert len(repo.entries) == 1
        assert repo.last_extracted == 20
        # 幂等：水位已到 → 不再提取
        ran2 = await maybe_extract(repo, session_id="s1", user_id="u1")
        assert ran2 is False
        assert len(repo.entries) == 1


@pytest.mark.unit
async def test_extract_below_threshold_skips():
    repo = _FakeRepo()
    for i in range(5):
        repo.append_message("s1", "u1", "user", f"m{i}")
    with patch("config.get_settings", return_value=_settings()):
        assert await maybe_extract(repo, session_id="s1", user_id="u1") is False


@pytest.mark.unit
async def test_extract_bad_output_marks_failure():
    """LLM 输出非法 → 不推进水位（下轮重试），不阻塞。"""
    repo = _FakeRepo()
    for i in range(20):
        repo.append_message("s1", "u1", "user", f"m{i}")
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content="不是 JSON"))
    with patch("agent.memory.extractor.build_extract_llm", return_value=llm), patch(
        "config.get_settings", return_value=_settings()
    ):
        assert await maybe_extract(repo, session_id="s1", user_id="u1") is False
    assert repo.last_extracted == 0  # 水位未动


@pytest.mark.unit
async def test_worker_isolated_from_main_agent():
    """MemoryExtractWorker 独立可用：不依赖主 agent/checkpointer，直接调用可完成提取。"""
    repo = _FakeRepo()
    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=MagicMock(content='{"entries": [{"kind": "decision", "content": "选课优先校区"}]}')
    )
    worker = MemoryExtractWorker(llm=llm)
    ok = await worker.extract(
        repo=repo,
        session_id="s9",
        user_id="u9",
        messages=[{"role": "user", "content": "帮我选课", "seq": 3}],
        previous_entries=[],
    )
    assert ok is True
    assert repo.entries == [{"kind": "decision", "content": "选课优先校区"}]
    assert repo.last_extracted == 3


@pytest.mark.unit
async def test_worker_failure_marks_failure_and_no_watermark():
    """worker 失败：标记失败、水位不动（下轮可重试），不抛异常（forked 隔离）。"""
    repo = _FakeRepo()
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content="坏输出"))
    worker = MemoryExtractWorker(llm=llm)
    ok = await worker.extract(
        repo=repo,
        session_id="s9",
        user_id="u9",
        messages=[{"role": "user", "content": "x", "seq": 5}],
        previous_entries=[],
    )
    assert ok is False
    assert repo.last_extracted == 0


@pytest.mark.unit
async def test_inject_only_first_turn_and_own_memory():
    """注入仅首轮；续轮不注入；无记忆不注入。"""
    repo = _FakeRepo()
    with patch("config.get_settings", return_value=_settings()):
        # 无记忆 → None
        assert await inject_memory_entries(repo, session_id="s1", user_id="u1") is None
        # 有记忆且首轮 → 注入
        repo.entries.append({"kind": "fact", "content": "用户偏好安静环境"})
        prefix = await inject_memory_entries(repo, session_id="s1", user_id="u1")
        assert prefix is not None and "用户偏好安静环境" in prefix
        # 续轮（已有消息）→ 不注入
        repo.append_message("s1", "u1", "user", "x")
        assert await inject_memory_entries(repo, session_id="s1", user_id="u1") is None
        # 匿名 → 不注入
        assert await inject_memory_entries(repo, session_id="s2", user_id="") is None


# ── B：信号即时提取（未达攒批阈值但命中改口信号 → 立即提取）────────
@pytest.mark.unit
async def test_signal_immediate_extract_below_threshold():
    repo = _FakeRepo()
    for i in range(6):  # 3 轮 = 6 条 < 20 阈值
        repo.append_message("s1", "u1", "user" if i % 2 == 0 else "assistant", f"m{i}")
    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=MagicMock(content='{"entries": [{"kind": "decision", "content": "用户决定不再运动"}]}')
    )
    with patch("agent.memory.extractor.build_extract_llm", return_value=llm), patch(
        "config.get_settings", return_value=_settings()
    ):
        ran = await maybe_extract(repo, session_id="s1", user_id="u1", user_text="我不再喜欢运动了")
    assert ran is True
    assert repo.last_extracted == 6
    assert repo.entries == [{"kind": "decision", "content": "用户决定不再运动"}]


@pytest.mark.unit
async def test_signal_without_new_messages_skips():
    repo = _FakeRepo()
    for i in range(6):
        repo.append_message("s1", "u1", "user", f"m{i}")
    repo.last_extracted = 6  # 水位已到：没有未提取消息
    llm = MagicMock()
    with patch("agent.memory.extractor.build_extract_llm", return_value=llm), patch(
        "config.get_settings", return_value=_settings()
    ):
        ran = await maybe_extract(repo, session_id="s1", user_id="u1", user_text="我不再喜欢运动了")
    assert ran is False
    llm.ainvoke.assert_not_called()


@pytest.mark.unit
async def test_signal_rate_limited():
    from agent.memory import extractor as _ext

    _ext._user_last_extract_at.clear()  # 清理模块级限频表（防跨测试污染）
    repo = _FakeRepo()
    for i in range(6):
        repo.append_message("s1", "u1", "user" if i % 2 == 0 else "assistant", f"m{i}")
    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=MagicMock(content='{"entries": [{"kind": "decision", "content": "用户决定不再运动"}]}')
    )
    with patch("agent.memory.extractor.build_extract_llm", return_value=llm), patch(
        "config.get_settings", return_value=_settings(memory_extract_min_interval_seconds=10000)
    ):
        ran1 = await maybe_extract(repo, session_id="s1", user_id="u1", user_text="我不再喜欢运动了")
        # 又聊一轮（2 条新消息），同 user 仍在限频窗口内
        repo.append_message("s1", "u1", "user", "我以后也不游泳了")
        repo.append_message("s1", "u1", "assistant", "好的")
        ran2 = await maybe_extract(repo, session_id="s1", user_id="u1", user_text="我以后也不游泳了")
    assert ran1 is True
    assert ran2 is False  # 限频拦截（水位已到 6，第二次也只会有 2 条新消息，不足攒批阈值）
    assert repo.last_extracted == 6


# ── C1：supersede 只允许删"模型确实看到且精确命中"的旧条目 ──────────
@pytest.mark.unit
async def test_supersede_only_deletes_whitelisted_previous():
    repo = _FakeRepo()
    old = "用户喜欢运动，尤其爱打篮球"
    repo.entries.append({"kind": "preference", "content": old})
    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=MagicMock(
            content='{"entries": [{"kind": "decision", "content": "用户决定不再运动"}], '
            '"supersede": ["用户喜欢运动，尤其爱打篮球", "库里根本不存在的幻影条目"]}'
        )
    )
    worker = MemoryExtractWorker(llm=llm)
    ok = await worker.extract(
        repo=repo,
        session_id="s9",
        user_id="u9",
        messages=[{"role": "user", "content": "我不再喜欢运动了", "seq": 1}],
        previous_entries=[{"kind": "preference", "content": old}],
    )
    assert ok is True
    # 幻影条目不在 previous-memory 中 → 被白名单过滤；旧偏好被删，新更正写入
    assert repo.entries == [{"kind": "decision", "content": "用户决定不再运动"}]


# ── TTL 过期策略：fact 永不过期；preference/decision 设 TTL；ttl<=0 不过期 ──
@pytest.mark.unit
def test_memory_expires_at_policy():
    from datetime import datetime

    from agent.memory.extractor import memory_expires_at

    assert memory_expires_at("fact", 30) is None
    assert memory_expires_at("preference", 0) is None
    assert memory_expires_at("decision", None) is None
    exp = memory_expires_at("preference", 30)
    assert exp is not None
    assert isinstance(exp, datetime)
    # 约 30 天（允许 ±1 天误差）
    delta_days = (exp - datetime.utcnow()).days
    assert 29 <= delta_days <= 30

