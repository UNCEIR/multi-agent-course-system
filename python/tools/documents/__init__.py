# -*- coding: utf-8 -*-
"""文档工具包 — 文档解析 + 分块。

Phase 1 实装完整功能，当前为 stub 骨架。
"""

from __future__ import annotations

from .chunker import chunk_document
from .parser import parse_document

__all__ = [
    "chunk_document",
    "parse_document",
]