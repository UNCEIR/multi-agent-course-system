# -*- coding: utf-8 -*-
"""评价寄语工具 — evaluation 反幻觉分层的确定性数据侧。

Phase: 2 (implemented)
"""

from __future__ import annotations

from .get_academic_snapshot import build_snapshot, get_academic_snapshot
from .tool_wrappers import compute_radar_values, design_dimensions, generate_comment

__all__ = [
    "get_academic_snapshot",
    "build_snapshot",
    "design_dimensions",
    "compute_radar_values",
    "generate_comment",
]
