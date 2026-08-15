# -*- coding: utf-8 -*-
"""evaluation 数据基准测试：结构化提取 + 派生统计手算断言 + 无数据兜底。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tools.documents.desensitizer import extract_transcript_courses
from tools.evaluation.get_academic_snapshot import build_snapshot, compute_derived

TRANSCRIPT_TEXT = """广东工业大学本科生中文成绩单
姓名 黄信烨 学号 3123****52
2023-2024学年第一学期
高等数学（上） 5.0 92
大学英语（一） 3.5 88
程序设计基础 3.0 85
2023-2024学年第二学期
线性代数 2.5 78
大学物理（上） 4.0 及格
打印日期 2026年
"""


@pytest.mark.unit
def test_extract_courses_ok():
    courses = extract_transcript_courses(TRANSCRIPT_TEXT)
    assert len(courses) == 5
    assert courses[0]["name"] == "高等数学（上）"
    assert courses[0]["credits"] == 5.0
    assert courses[0]["numeric_score"] == 92.0
    # 非数值成绩保留字符串
    physics = [c for c in courses if "大学物理" in c["name"]][0]
    assert physics["numeric_score"] is None
    assert physics["score"] == "及格"


@pytest.mark.unit
def test_extract_courses_skips_headers_and_dates():
    """表头行/日期行/姓名行不误配。"""
    courses = extract_transcript_courses("课程名称 学分 成绩\n2023-2024学年第一学期\n" + TRANSCRIPT_TEXT)
    assert all("课程名称" != c["name"] for c in courses)
    assert all("学年" not in c["name"] for c in courses)


@pytest.mark.unit
def test_extract_courses_incompatible_returns_empty():
    """格式不兼容（提取不足 2 条）→ 空（调用方 warning，不阻塞摄入）。"""
    assert extract_transcript_courses("纯文本成绩单\n没有任何结构化行") == []


@pytest.mark.unit
def test_compute_derived_hand_computed():
    """派生统计与手算一致（防幻觉的确定性基准）。"""
    courses = extract_transcript_courses(TRANSCRIPT_TEXT)
    derived = compute_derived(courses)
    # 数值成绩：92, 88, 85, 78 → avg = 85.75
    assert derived["course_count"] == 5
    assert derived["total_credits"] == 18.0
    assert derived["avg"] == 85.75
    # 加权均分 = (92*5+88*3.5+85*3+78*2.5)/14 = (460+308+255+195)/14 = 1218/14 = 87.0
    assert derived["weighted_avg"] == 87.0
    assert derived["top_subject"]["name"] == "高等数学（上）"
    assert derived["weak_subject"]["name"] == "线性代数"
    # 及格：92/88/85/78 + 及格 → 5/5
    assert derived["pass_rate"] == 1.0


@pytest.mark.unit
def test_snapshot_no_user():
    with patch("agent.main.context.get_current_user_id", return_value=""):
        result = build_snapshot()
    assert result["code"] == "no_user"


@pytest.mark.unit
def test_snapshot_no_transcript_data():
    repo = MagicMock()
    repo.get_chunks_by_user = MagicMock(return_value=[])
    with patch("agent.main.context.get_current_user_id", return_value="3123003252"), patch(
        "agent.runtime.document_repo", repo
    ):
        result = build_snapshot()
    assert result["code"] == "no_transcript_data"


@pytest.mark.unit
def test_snapshot_ok():
    chunks = [
        {
            "chunk_id": "c1",
            "metadata": {"user_id": "u1", "courses": [{"name": "高数", "credits": 5.0, "score": "92", "numeric_score": 92.0}]},
        },
        {
            "chunk_id": "c2",
            "metadata": {"user_id": "u1", "courses": [{"name": "英语", "credits": 3.0, "score": "88", "numeric_score": 88.0}]},
        },
    ]
    repo = MagicMock()
    repo.get_chunks_by_user = MagicMock(return_value=chunks)
    with patch("agent.main.context.get_current_user_id", return_value="u1"), patch(
        "agent.runtime.document_repo", repo
    ):
        result = build_snapshot()
    assert "code" not in result
    assert len(result["courses"]) == 2
    assert result["derived"]["weighted_avg"] == round((92 * 5 + 88 * 3) / 8, 2)
    assert result["sources"] == ["c1", "c2"]
