# -*- coding: utf-8 -*-
"""报告工具 — 成绩解析、合并、统计、报告生成等。

Phase: 2 (implemented)
"""

from __future__ import annotations

from .compute_weighted_grade import compute_weighted_grade
from .inspect_score_excels import inspect_score_excels
from .merge_students import assert_integrity, journal_load, journal_save, merge_files
from .parse_score_excels import ExcelParseError, parse_score_excels, parse_workbook
from .render_report_batch import render_report_batch

__all__ = [
    "compute_weighted_grade",
    "parse_workbook",
    "parse_score_excels",
    "ExcelParseError",
    "merge_files",
    "assert_integrity",
    "journal_save",
    "journal_load",
    "inspect_score_excels",
    "render_report_batch",
]
