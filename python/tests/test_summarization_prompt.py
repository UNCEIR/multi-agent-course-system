# -*- coding: utf-8 -*-
"""summarization 五字段 prompt 注入与回退测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from agent.main.factory import _load_summarization_prompt

FIVE_FIELDS = ("GOAL", "PROGRESS", "KEY DECISIONS", "NEXT STEPS", "CRITICAL CONTEXT")


def test_prompt_file_exists():
    path = Path(__file__).resolve().parents[1] / "agent" / "main" / "prompts" / "summarization.txt"
    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    for field in FIVE_FIELDS:
        assert field in content, f"五字段缺失: {field}"
    assert "{messages}" in content, "必须保留 {messages} 占位符（deepagents 模板约定）"


def test_load_summarization_prompt_returns_content():
    prompt = _load_summarization_prompt()
    assert prompt is not None
    for field in FIVE_FIELDS:
        assert field in prompt


def test_load_summarization_prompt_fallback_on_missing_file():
    with patch(
        "agent.main.factory._SUMMARIZATION_PROMPT_PATH",
        Path(__file__).resolve().parent / "nonexistent_summarization.txt",
    ):
        assert _load_summarization_prompt() is None