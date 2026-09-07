# -*- coding: utf-8 -*-
"""兜底演示链路单测（Phase 4 F3）：断裂 → 熔断 → 拦截 → 恢复。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "demo_tool_fallback.py"


@pytest.fixture(scope="module")
def demo_mod():
    spec = importlib.util.spec_from_file_location("demo_tool_fallback", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    sys.modules["demo_tool_fallback"] = m
    spec.loader.exec_module(m)
    return m


@pytest.mark.unit
def test_demo_run_returns_zero(demo_mod):
    assert demo_mod.main() == 0


@pytest.mark.unit
def test_demo_asserts_full_cycle(demo_mod):
    """链路必须有熔断拦截 + 恢复成功（main 内部断言兜底）。"""
    from unittest.mock import patch

    with patch("builtins.print"):  # 抑制演示输出
        assert demo_mod.main() == 0
