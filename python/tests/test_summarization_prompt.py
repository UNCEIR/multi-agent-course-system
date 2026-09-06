# -*- coding: utf-8 -*-
"""summarization 六节 prompt 注入与回退测试（Phase 4 A5：读取路径改向 summarize.txt）。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from agent.main.factory import _load_summarization_prompt

SIX_FIELDS = ("GOAL", "CONSTRAINTS & PREFERENCES", "PROGRESS", "KEY DECISIONS", "NEXT STEPS", "CRITICAL CONTEXT")


def test_prompt_file_exists():
    path = Path(__file__).resolve().parents[1] / "agent" / "main" / "prompts" / "summarize.txt"
    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    for field in SIX_FIELDS:
        assert field in content, f"五字段缺失: {field}"
    assert "{messages}" in content, "必须保留 {messages} 占位符（deepagents 模板约定）"
    assert "## CONSTRAINTS & PREFERENCES" in content, "六节缺 Constraints"


def test_load_summarization_prompt_returns_content():
    prompt = _load_summarization_prompt()
    assert prompt is not None
    for field in SIX_FIELDS:
        assert field in prompt


def test_load_summarization_prompt_fallback_on_missing_file():
    with patch(
        "agent.main.factory._SUMMARIZE_PROMPT_PATH",
        Path(__file__).resolve().parent / "nonexistent_summarize.txt",
    ):
        assert _load_summarization_prompt() is None