# -*- coding: utf-8 -*-
"""脱敏器与解析/分块知识库能力测试。"""

from __future__ import annotations


def test_nfkc_normalizes_kangxi_variants():
    from tools.documents.desensitizer import normalize_nfkc

    # ⼴⼯⼤⾦ 是 Kangxi 部首（U+2F00 段），NFKC 可映射；⻩ 是 U+2EE9，不映射
    text = "⼴东⼯业⼤学 普通 姓名"
    assert normalize_nfkc(text) == "广东工业大学 普通 姓名"


def test_mask_student_id():
    from tools.documents.desensitizer import mask_student_id

    assert mask_student_id("3123003252") == "3123****52"


def test_mask_id_card_and_mobile():
    from tools.documents.desensitizer import mask_id_card, mask_mobile

    assert mask_id_card("440106199801011234") == "440106********1234"
    assert mask_mobile("13800138000") == "138****8000"


def test_generalize_class():
    from tools.documents.desensitizer import generalize_class

    assert "2023级" in generalize_class("信息管理与信息系统23(3)")


def test_desensitize_transcript_keeps_grades_masks_identifiers():
    from tools.documents.desensitizer import desensitize_transcript

    raw = (
        "姓名：黄信烨 学号：3123003252 班级：信息管理与信息系统23(3)\n"
        "2023秋季 高等数学 成绩 92\n"
        "打印日期：2026-07-28"
    )
    result = desensitize_transcript(raw, student_name="黄信烨")
    assert "[姓名]" in result
    assert "3123****52" in result
    assert "2023级" in result
    assert "2026年" in result
    assert "92" in result  # 成绩保留（个人分区内回答"某科考了多少分"）
    assert "黄信烨" not in result


def test_desensitize_transcript_handles_kangxi_supplement_name():
    from tools.documents.desensitizer import desensitize_transcript

    raw = "姓名：⻩信烨 学号：3123003252 班级：信息管理与信息系统23(3)"
    result = desensitize_transcript(raw, student_name="黄信烨")
    assert "[姓名]" in result
    assert "⻩信烨" not in result
    assert "3123****52" in result


def test_build_pii_report():
    from tools.documents.desensitizer import build_pii_report

    report = build_pii_report("学号 3123003252 手机 13800138000")
    assert report["student_id"] == 1
    assert report["mobile"] == 1


def test_recursive_chunking_is_heading_aware():
    from tools.documents.chunker import chunk_document

    text = (
        "第一章 学籍管理\n"
        "学生应按时注册，逾期未注册按退学处理。\n"
        "第二章 奖学金评定\n"
        "综合测评成绩为奖学金评定的主要依据，包括学业成绩、社会实践与综合素质三个部分。"
    )
    chunks = chunk_document.invoke({"text": text, "chunk_size": 800, "chunk_overlap": 50, "strategy": "recursive"})
    assert chunks, "recursive 分块不应为空"
    joined = "".join(c["text"] for c in chunks)
    assert "学籍管理" in joined
    assert "奖学金评定" in joined


def test_recursive_chunking_splits_long_text_on_sentence_boundary():
    from tools.documents.chunker import chunk_document

    sentence = "第一条 学生应当遵守学校各项规章制度，认真完成学业任务，积极参加各类集体活动。"
    text = "\n".join([sentence] * 30)
    chunks = chunk_document.invoke({"text": text, "chunk_size": 100, "chunk_overlap": 20, "strategy": "recursive"})
    assert len(chunks) > 1
    assert all(c["char_count"] > 0 for c in chunks)
