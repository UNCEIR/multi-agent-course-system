# -*- coding: utf-8 -*-
"""图片工具 — 识别（image_recognize，视觉直连）+ 生成（即梦 4.0 两段式）。

Phase 4（E1）实装：
- image_recognize：URL/data URL/本地路径 → qwen3-vl-plus 结构化识别（chart/series/trend + source_image 可溯源）
- image_generate / image_generate_get：即梦 4.0 两段式（提交 → 轮询 → 转存 MinIO/本地）
"""

from __future__ import annotations

from .image_generate import image_generate, image_generate_get
from .image_recognize import image_recognize

__all__ = [
    "image_generate",
    "image_generate_get",
    "image_recognize",
]
