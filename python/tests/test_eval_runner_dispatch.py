# -*- coding: utf-8 -*-
"""eval runner _parse_chat_stream_events 单测：dispatch_module → 模块名映射。"""

from __future__ import annotations

import json

import pytest

from eval.runner import _parse_chat_stream_events


def _sse_lines(events: list[tuple[str, dict]]) -> list[str]:
    """构造 SSE 行序列：`[("",{}), ("event: tool", {...}), ("data: {...}", {})]`。"""
    out: list[str] = []
    for name, payload in events:
        if name:
            out.append(f"event: {name}")
        if payload or payload == {}:
            out.append(f"data: {json.dumps(payload, ensure_ascii=False)}")
        out.append("")
    return out


@pytest.mark.unit
def test_dispatch_module_report_maps_to_module_name():
    """intent_04 修复后预期：dispatch_module(intent='report') → tool_chain=['report']"""
    lines = _sse_lines([
        ("tool", {"tool": "list_available_skills", "status": "start", "args": {}}),
        ("tool", {"tool": "dispatch_module", "status": "start", "args": {"intent": "report", "payload": {}}}),
        ("tool", {"tool": "dispatch_module", "status": "end"}),
        ("text", {"token": "请到 /report 页面上传 Excel 生成报告"}),
        ("done", {"reply": "请到 /report 页面上传 Excel 生成报告", "usage": {}, "latency_ms": 1234, "ttft_ms": 100}),
    ])
    out = _parse_chat_stream_events(lines)
    assert out["tool_chain"] == ["report"]
    assert "report" in out["reply"]


@pytest.mark.unit
def test_dispatch_module_evaluation_maps_to_module_name():
    """intent_06/07 修复后预期：dispatch_module(intent='evaluation') → ['evaluation']"""
    lines = _sse_lines([
        ("tool", {"tool": "dispatch_module", "status": "start", "args": {"intent": "evaluation"}}),
        ("done", {"reply": "请到 /evaluation 页生成评语", "usage": {}, "latency_ms": 800}),
    ])
    out = _parse_chat_stream_events(lines)
    assert out["tool_chain"] == ["evaluation"]


@pytest.mark.unit
def test_dispatch_module_ppt_and_image_generate():
    """ppt / image_generate 同样走 dispatch_module 映射。"""
    for intent in ("ppt", "image_generate"):
        lines = _sse_lines([
            ("tool", {"tool": "dispatch_module", "status": "start", "args": {"intent": intent}}),
            ("done", {"reply": "请到独立页", "usage": {}, "latency_ms": 500}),
        ])
        out = _parse_chat_stream_events(lines)
        assert out["tool_chain"] == [intent], intent


@pytest.mark.unit
def test_dispatch_module_without_intent_filtered_out():
    """args 缺失 intent 时 dispatch_module 不进 tool_chain（防御：避免裸名污染断言）。"""
    lines = _sse_lines([
        ("tool", {"tool": "dispatch_module", "status": "start", "args": {}}),
        ("done", {"reply": "", "usage": {}, "latency_ms": 100}),
    ])
    out = _parse_chat_stream_events(lines)
    assert "dispatch_module" not in out["tool_chain"]
    assert out["tool_chain"] == []


@pytest.mark.unit
def test_other_tools_passthrough():
    """非 dispatch_module 工具透传 tool_name。"""
    lines = _sse_lines([
        ("tool", {"tool": "query_knowledge", "status": "start", "args": {"query": "x"}}),
        ("tool", {"tool": "recommend_courses", "status": "start", "args": {"limit": 5}}),
        ("done", {"reply": "ok", "usage": {}, "latency_ms": 200}),
    ])
    out = _parse_chat_stream_events(lines)
    assert out["tool_chain"] == ["query_knowledge", "recommend_courses"]


@pytest.mark.unit
def test_noise_tools_filtered():
    """噪音工具（系统工具 + MCP 子事件）从 tool_chain 过滤掉。"""
    lines = _sse_lines([
        ("tool", {"tool": "read_file", "status": "start", "args": {"path": "/skills/x/SKILL.md"}}),
        ("tool", {"tool": "list_available_skills", "status": "start"}),
        ("tool", {"tool": "tavily_search", "status": "start"}),
        ("tool", {"tool": "execute_code", "status": "start"}),
        ("tool", {"tool": "query_knowledge", "status": "start"}),
        ("done", {"reply": "ok", "usage": {}, "latency_ms": 50}),
    ])
    out = _parse_chat_stream_events(lines)
    assert out["tool_chain"] == ["query_knowledge"]


@pytest.mark.unit
def test_text_and_done_accumulate_reply_and_usage():
    """text 事件累计 token；done 事件解析 usage / latency / ttft。"""
    lines = _sse_lines([
        ("text", {"token": "你"}),
        ("text", {"token": "好"}),
        ("done", {
            "reply": "你好",
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "latency_ms": 321.5,
            "ttft_ms": 42.1,
        }),
    ])
    out = _parse_chat_stream_events(lines)
    assert out["reply"] == "你好"
    assert out["usage"] == {"input_tokens": 100, "output_tokens": 50}
    assert out["latency_ms"] == 321.5
    assert out["ttft_ms"] == 42.1


@pytest.mark.unit
def test_malformed_data_line_does_not_crash():
    """data 行 JSON 解析失败不应让整个解析抛错（runner 容错）。"""
    lines = [
        "event: tool",
        "data: {not json",
        "",
        "event: done",
        'data: {"reply":"x","usage":{},"latency_ms":1}',
        "",
    ]
    out = _parse_chat_stream_events(lines)
    assert out["tool_chain"] == []  # 坏 JSON → data={} → tool_name 空 → 过滤
    assert out["latency_ms"] == 1
