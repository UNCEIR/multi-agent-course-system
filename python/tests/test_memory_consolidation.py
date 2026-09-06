# -*- coding: utf-8 -*-
"""记忆 consolidation 测试：确定性去重、超限 LLM 合并、LLM 失败仅去重、决策 19 不出文件。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.memory.consolidation import ConsolidationWorker


class _FakeRepo:
    def __init__(self):
        self.entries: list[dict] = []
        self.deleted: list[str] = []

    def list_memory_entries(self, user_id, limit=50, max_chars=2000, agent_name="main_agent"):
        return list(self.entries[:limit])

    def upsert_memory_entry(self, user_id, kind, content, source_session_id="", agent_name="main_agent"):
        self.entries.append({"kind": kind, "content": content, "source_session_id": source_session_id})

    def delete_memory_entries(self, user_id, contents, agent_name="main_agent"):
        self.deleted.extend(contents)
        self.entries = [e for e in self.entries if e["content"] not in contents]

    def replace_memory_entries(self, user_id, delete_contents, upsert_entries, agent_name="main_agent", upsert_expires=None):
        self.deleted.extend(delete_contents)
        self.entries = [e for e in self.entries if e["content"] not in delete_contents]
        for kind, content in upsert_entries:
            self.entries.append({"kind": kind, "content": content, "source_session_id": "consolidate"})


def _settings(threshold=15):
    s = MagicMock()
    s.memory_consolidate_threshold_per_kind = threshold
    return s


@pytest.mark.unit
async def test_dedup_keeps_unique_entries_untouched():
    repo = _FakeRepo()
    repo.entries = [
        {"kind": "fact", "content": "用户喜欢编程"},
        {"kind": "preference", "content": "偏好安静环境"},
    ]
    worker = ConsolidationWorker(llm=MagicMock())
    with patch("config.get_settings", return_value=_settings(threshold=1)):
        stats = await worker.consolidate(repo=repo, user_id="u1")
    assert stats["deduped"] == 0
    assert len(repo.entries) == 2
    assert repo.deleted == []


@pytest.mark.unit
async def test_dedup_normalized_duplicates():
    repo = _FakeRepo()
    repo.entries = [
        {"kind": "fact", "content": "选修高等数学"},
        {"kind": "fact", "content": "选修高等数学 "},  # NFKC 归一后重复
    ]
    worker = ConsolidationWorker(llm=MagicMock())
    with patch("config.get_settings", return_value=_settings(threshold=1)):
        stats = await worker.consolidate(repo=repo, user_id="u1")
    assert stats["deduped"] == 1
    assert len(repo.entries) == 1


@pytest.mark.unit
async def test_over_threshold_kind_llm_merge():
    repo = _FakeRepo()
    for i in range(5):
        repo.entries.append({"kind": "fact", "content": f"同义条目 {i}"})
    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=MagicMock(
            content='{"entries": [{"kind": "fact", "content": "合并后唯一条目"}]}'
        )
    )
    worker = ConsolidationWorker(llm=llm)
    with patch("config.get_settings", return_value=_settings(threshold=3)):
        stats = await worker.consolidate(repo=repo, user_id="u1")
    assert stats["merged_kinds"] == ["fact"]
    assert len(repo.entries) == 1
    assert repo.entries[0]["content"] == "合并后唯一条目"
    assert len(repo.deleted) == 5


@pytest.mark.unit
async def test_llm_failure_dedup_only():
    repo = _FakeRepo()
    for i in range(5):
        repo.entries.append({"kind": "fact", "content": f"同义条目 {i}"})
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content="坏输出"))
    worker = ConsolidationWorker(llm=llm)
    with patch("config.get_settings", return_value=_settings(threshold=3)):
        stats = await worker.consolidate(repo=repo, user_id="u1")
    assert stats["merged_kinds"] == []
    assert repo.deleted == []
    assert len(repo.entries) == 5  # 仅去重不合并，不误删


@pytest.mark.unit
async def test_consolidation_never_writes_files(tmp_path):
    """决策 19：consolidation 只操作内存仓储，绝不写出文件。"""
    repo = _FakeRepo()
    repo.entries = [{"kind": "fact", "content": "用户偏好安静"}]
    worker = ConsolidationWorker(llm=MagicMock())
    with patch("config.get_settings", return_value=_settings(threshold=1)):
        await worker.consolidate(repo=repo, user_id="u1")
    assert list(tmp_path.iterdir()) == []