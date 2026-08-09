# -*- coding: utf-8 -*-
"""文档工具包 — Python 本地文档解析、确定性分块与个人数据脱敏。"""

from __future__ import annotations

from .chunker import chunk_document
from .desensitizer import (
    build_pii_report,
    desensitize_transcript,
    generalize_class,
    mask_id_card,
    mask_mobile,
    mask_student_id,
    normalize_nfkc,
    replace_name,
)
from .parser import parse_document

__all__ = [
    "chunk_document",
    "parse_document",
    "normalize_nfkc",
    "desensitize_transcript",
    "build_pii_report",
    "mask_student_id",
    "mask_id_card",
    "mask_mobile",
    "generalize_class",
    "replace_name",
]
