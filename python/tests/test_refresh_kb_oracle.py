# -*- coding: utf-8 -*-
"""refresh_kb_retrieval_oracle 收敛逻辑单测（Phase 4 B4）：expected ≤ k + 语义筛选。"""

from __future__ import annotations

import pytest

SCRIPT = r"E:\Agent\mult-agent-university-system\python\scripts\refresh_kb_retrieval_oracle.py"


@pytest.fixture(scope="module")
def mod():
    import importlib.util

    spec = importlib.util.spec_from_file_location("refresh_kb_oracle", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_CASE = {
    "case_id": "kb_01",
    "scenario": "奖学金",
    "reference": {"contexts": ["奖学金评审办法：国家奖学金、学校奖学金申请条件与评审流程"]},
}


def _chunks(n: int, prefix="handbook_2025_abc:"):
    return [(f"{prefix}{i}", f"内容{i}") for i in range(n)]


@pytest.mark.unit
def test_converge_within_k(mod):
    matched = _chunks(3)
    out = mod._converge(matched, _CASE, k=5)
    assert len(out) == 3


@pytest.mark.unit
def test_converge_truncates_to_k(mod):
    matched = _chunks(10)
    out = mod._converge(matched, _CASE, k=5)
    assert len(out) == 5
    # 按 chunk 序号取前 k：取最接近目标章节的（序号最小的 5 个）
    assert out == [f"handbook_2025_abc:{i}" for i in range(5)]


@pytest.mark.unit
def test_converge_anchor_filter(mod):
    anchor = "奖学金评审办法：国家奖学金、学校奖学金申请条件与评审流程"
    matched = [
        ("handbook_2025_abc:1", "普通内容"),
        ("handbook_2025_abc:2", anchor),
        ("handbook_2025_abc:3", "普通内容"),
        ("handbook_2025_abc:4", anchor),
        ("handbook_2025_abc:5", "普通内容"),
    ]
    out = mod._converge(matched, _CASE, k=3)
    # 锚短语优先：2 个命中奖学金章节的 chunk 保留（≤k），普通内容被剔除
    assert out == ["handbook_2025_abc:2", "handbook_2025_abc:4"]


@pytest.mark.unit
def test_chunk_seq(mod):
    assert mod._chunk_seq("handbook_2025_abc:42") == 42
    assert mod._chunk_seq("bad-id") == 0
