# -*- coding: utf-8 -*-
"""Token 估算与压缩阈值决策（Phase 4 P0-A）。

- estimate_context_tokens：provider usage 优先（A0 落库的 usage_json.total_tokens），
  缺失时字符估算：中文按 chars/2、英文按 chars/4（经验系数）。
- should_compact：单点决策（window - reserve 触发），消除「消息数 / token 双路径打架」。
"""

from __future__ import annotations

import re
from typing import Any

_ZH_RE = re.compile(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")


def _chars_to_tokens(text: str) -> int:
    """字符估算：中文字符按 /2，其余按 /4（经验系数，避免 /4 低估中文）。"""
    zh = len(_ZH_RE.findall(text))
    other = len(text) - zh
    return int(zh / 2 + other / 4) + 1


def _message_text(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("content", "") or "")
    return str(getattr(msg, "content", "") or "")


def estimate_context_tokens(messages: list[Any], usage_json: dict | str | None = None) -> int:
    """估算消息列表 token 数。

    usage_json 优先（A0 落库的 total_tokens，来自 provider 真实计数）；
    缺失时按字符估算逐条累加。
    """
    if usage_json:
        if isinstance(usage_json, str):
            import json

            try:
                usage_json = json.loads(usage_json)
            except (ValueError, TypeError):
                usage_json = {}
        total = usage_json.get("total_tokens") or usage_json.get("input_tokens")
        if isinstance(total, (int, float)) and total > 0:
            return int(total)
    if not messages:
        return 0
    return sum(_chars_to_tokens(_message_text(m)) for m in messages)


def should_compact(tokens: int, window: int, reserve: int) -> bool:
    """tokens 达到 window - reserve 即触发压缩。"""
    return tokens >= max(0, int(window) - int(reserve))
