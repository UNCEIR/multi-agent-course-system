# -*- coding: utf-8 -*-
"""dispatch_module 路由工具单测：输入校验 / 返回 JSON 结构 / 4 个合法 intent。"""

from __future__ import annotations

import json

import pytest


def _invoke(intent: str, payload: dict | None = None) -> dict:
    from tools.system.dispatch_module import dispatch_module

    raw = dispatch_module.invoke({"intent": intent, "payload": payload or {}})
    return json.loads(raw)


@pytest.mark.unit
def test_dispatch_report_returns_module_and_hint():
    out = _invoke("report", {"semester": "上学期", "subject": "道法"})
    assert out["module"] == "report"
    assert "/api/v1/report" in out["hint"] or "/report" in out["hint"]
    assert out["payload"] == {"semester": "上学期", "subject": "道法"}


@pytest.mark.unit
def test_dispatch_evaluation_returns_module_and_hint():
    out = _invoke("evaluation", {"target_user_id": "张三", "comment_type": "semester_summary"})
    assert out["module"] == "evaluation"
    # 委派语义：hint 指向已挂载的 evaluation_agent（task 委派走 SKILL.md 流程）
    assert "evaluation_agent" in out["hint"]
    assert "task(" in out["hint"]
    assert out["payload"]["target_user_id"] == "张三"


@pytest.mark.unit
def test_dispatch_ppt_and_image_generate():
    # ppt 引导独立页面；image_generate 指向 chat 内两段式工具（无独立页面）
    out = _invoke("ppt")
    assert out["module"] == "ppt"
    assert "/ppt" in out["hint"]
    ig = _invoke("image_generate")
    assert ig["module"] == "image_generate"
    assert "image_generate" in ig["hint"]
    assert "image_generate_get" in ig["hint"]


@pytest.mark.unit
def test_dispatch_default_payload_is_empty_dict():
    out = _invoke("report")
    assert out["payload"] == {}


@pytest.mark.unit
def test_dispatch_rejects_unknown_intent():
    """Pydantic Literal 拦截非法 intent（防止 LLM 误传自定义模块名）。"""
    from langchain_core.tools import BaseTool

    tool_obj = None
    from tools.system.dispatch_module import dispatch_module

    tool_obj = dispatch_module
    assert isinstance(tool_obj, BaseTool)
    schema = tool_obj.args_schema
    assert schema is not None
    field = schema.model_fields["intent"]
    allowed = getattr(field.annotation, "__args__", ())
    assert set(allowed) == {"report", "evaluation", "ppt", "image_generate"}
