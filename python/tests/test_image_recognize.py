# -*- coding: utf-8 -*-
"""image_recognize 单测：URL/data URL/本地路径 → 结构化 JSON（可溯源）+ 容错。"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _llm_responding(text: str):
    llm = MagicMock()
    resp = MagicMock()
    resp.content = text
    llm.ainvoke = AsyncMock(return_value=resp)
    return llm


@pytest.mark.unit
async def test_recognize_structured_chart_returns_json_with_source(tmp_path):
    """图表关键词 → 结构化 JSON（chart_type/series/trend/source_image 可溯源）。"""
    from tools.image.image_recognize import image_recognize

    img = tmp_path / "chart.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n fake image bytes")
    llm = _llm_responding(
        '{"chart_type": "line", "series": [{"name": "成绩", "points": [{"x": "上学期", "y": 85}]}], '
        '"trend": "上升", "confidence": 0.9, "summary": "成绩呈上升趋势"}'
    )
    with patch("tools.image.image_recognize._build_vision_llm", return_value=llm):
        raw = await image_recognize.ainvoke({"image_url": str(img), "question": "分析成绩趋势图"})

    data = json.loads(raw)
    assert data["chart_type"] == "line"
    assert data["trend"] == "上升"
    assert data["source_image"] == str(img)  # 可溯源


@pytest.mark.unit
async def test_recognize_unstructured_rejected(tmp_path):
    """图表场景但 LLM 返回非 JSON → VISION_UNSTRUCTURED 拒绝引用。"""
    from tools.image.image_recognize import image_recognize

    img = tmp_path / "chart.png"
    img.write_bytes(b"fake")
    llm = _llm_responding("这段成绩还不错，整体平稳。")  # 非 JSON
    with patch("tools.image.image_recognize._build_vision_llm", return_value=llm):
        raw = await image_recognize.ainvoke({"image_url": str(img), "question": "成绩趋势如何"})

    data = json.loads(raw)
    assert data.get("isError") is True
    assert data["code"] == "VISION_UNSTRUCTURED"
    assert data["source_image"] == str(img)


@pytest.mark.unit
async def test_recognize_fetch_failed_returns_error():
    """图片获取失败（路径不存在）→ IMAGE_FETCH_FAILED，不空跑 LLM。"""
    from tools.image.image_recognize import image_recognize

    raw = await image_recognize.ainvoke({"image_url": "Z:/definitely/not/exist.png", "question": ""})
    data = json.loads(raw)
    assert data.get("isError") is True
    assert data["code"] == "IMAGE_FETCH_FAILED"


@pytest.mark.unit
async def test_recognize_plain_description_when_no_chart_keyword(tmp_path):
    """无图表关键词 → 普通描述路径（直接返回文本，不强求 JSON）。"""
    from tools.image.image_recognize import image_recognize

    img = tmp_path / "photo.png"
    img.write_bytes(b"fake")
    llm = _llm_responding("这是一张校园照片。")
    with patch("tools.image.image_recognize._build_vision_llm", return_value=llm):
        # question 不含图表关键词（"图/成绩/趋势"等）→ 走普通描述路径
        raw = await image_recognize.ainvoke({"image_url": str(img), "question": ""})

    assert raw == "这是一张校园照片。"


@pytest.mark.unit
async def test_to_data_url_passthrough_and_local_file(tmp_path):
    """data URL 原样透传；本地文件转 data URL。"""
    from tools.image.image_recognize import _to_data_url

    assert _to_data_url("data:image/png;base64,AAAA") == "data:image/png;base64,AAAA"
    img = tmp_path / "a.png"
    img.write_bytes(b"abc")
    url = _to_data_url(str(img))
    assert url.startswith("data:image/png;base64,")
    assert _to_data_url(str(tmp_path / "missing.png")) is None
