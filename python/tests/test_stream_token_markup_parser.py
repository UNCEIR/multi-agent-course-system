from __future__ import annotations

from typing import AsyncGenerator

import pytest

from app.recommend.stream_token_markup_parser import StreamTokenMarkupParser


async def _token_stream(*chunks: str) -> AsyncGenerator[str, None]:
    for chunk in chunks:
        yield chunk


async def _collect(parser: StreamTokenMarkupParser, *chunks: str) -> list[dict]:
    return [event async for event in parser.parse(_token_stream(*chunks))]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_stream_no_events():
    parser = StreamTokenMarkupParser()
    events = await _collect(parser)
    assert events == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pure_text_no_markers():
    parser = StreamTokenMarkupParser()
    events = await _collect(parser, "推荐以下课程供参考：\n")
    assert len(events) == 1
    assert events[0]["type"] == "text"
    assert events[0]["course_id"] is None
    assert events[0]["token"] == "推荐以下课程供参考：\n"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_single_complete_marker():
    parser = StreamTokenMarkupParser()
    events = await _collect(
        parser,
        "总起语：",
        "[COURSE:GXK001:电影艺术赏析]",
        "该课程很好。",
    )
    types = [e["type"] for e in events]
    assert types == ["text", "course_start", "text", "course_end"]
    assert events[0]["course_id"] is None
    assert events[1]["course_id"] == "GXK001"
    assert events[1]["course_name"] == "电影艺术赏析"
    assert events[1]["index"] == 0
    assert events[2]["course_id"] == "GXK001"
    assert events[2]["token"] == "该课程很好。"
    assert events[3]["type"] == "course_end"
    assert events[3]["course_id"] == "GXK001"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_marker_split_across_chunks():
    parser = StreamTokenMarkupParser()
    events = await _collect(
        parser,
        "前面文本",
        "[COURSE:GXK",
        "002:Python程序设计]",
        "很好。",
    )
    types = [e["type"] for e in events]
    assert types == ["text", "course_start", "text", "course_end"]
    assert events[1]["type"] == "course_start"
    assert events[1]["course_id"] == "GXK002"
    assert events[1]["course_name"] == "Python程序设计"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_multiple_courses():
    parser = StreamTokenMarkupParser()
    events = await _collect(
        parser,
        "总起",
        "[COURSE:GXK001:电影鉴赏]",
        "课程A很好。",
        "[COURSE:GXK002:程序设计]",
        "课程B很好。",
    )
    types = [e["type"] for e in events]
    assert types == [
        "text",
        "course_start",
        "text",
        "course_end",
        "course_start",
        "text",
        "course_end",
    ]
    assert events[1]["course_id"] == "GXK001"
    assert events[3]["type"] == "course_end"
    assert events[3]["course_id"] == "GXK001"
    assert events[4]["course_id"] == "GXK002"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_final_course_end_on_exhaustion():
    parser = StreamTokenMarkupParser()
    events = await _collect(
        parser,
        "[COURSE:GXK001:电影鉴赏]",
        "内容。",
    )
    types = [e["type"] for e in events]
    assert types == ["course_start", "text", "course_end"]
    assert events[2]["type"] == "course_end"
    assert events[2]["course_id"] == "GXK001"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invalid_marker_flushes_as_text():
    parser = StreamTokenMarkupParser()
    events = await _collect(
        parser,
        "前缀",
        "[NOT_A_MARKER:stuff]",
        "后缀",
    )
    types = [e["type"] for e in events]
    assert types == ["text", "text", "text"]
    assert "[NOT_A_MARKER:stuff]" in events[1]["token"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_buffer_overflow_flushes():
    parser = StreamTokenMarkupParser()
    long_prefix = "X" * 250 + "[COURSE"
    events = await _collect(parser, long_prefix)
    types = [e["type"] for e in events]
    assert types == ["text", "text"]
    assert "[COURSE" in events[1]["token"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_nested_bracket_resets_buffer():
    parser = StreamTokenMarkupParser()
    events = await _collect(
        parser,
        "先有文本",
        "[COURSE:GXK001:[嵌套]电影鉴赏]",
        "后续文本",
    )
    types = [e["type"] for e in events]
    assert types == ["text", "text", "text", "text"]
    assert "[" in events[1]["token"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_single_char_chunks():
    parser = StreamTokenMarkupParser()
    chars = list("[COURSE:GXK001:电影]文本")
    events = []
    async for chunk in parser.parse(_token_stream(*chars)):
        events.append(chunk)
    assert events[0]["type"] == "course_start"
    assert events[0]["course_id"] == "GXK001"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_chunk_skipped():
    parser = StreamTokenMarkupParser()
    events = await _collect(parser, "", "hello", "", " world")
    assert len(events) == 2
    assert events[0]["token"] == "hello"
    assert events[1]["token"] == " world"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_course_name_with_special_chars():
    parser = StreamTokenMarkupParser()
    events = await _collect(
        parser,
        "[COURSE:GXK001:大学英语(四)-高级]",
        "内容。",
    )
    assert events[0]["type"] == "course_start"
    assert events[0]["course_name"] == "大学英语(四)-高级"
