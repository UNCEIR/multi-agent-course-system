# -*- coding: utf-8 -*-
"""模块路由工具 — dispatch_module。

主 agent 在识别到独立模块（报告/评价/PPT/图片生成）入口意图时调用，
返回目标模块名 + 前端跳转/端点拉起提示。设计动机：Phase 2 实装 report /
evaluation 直接管线，但 main agent 之前没有路由工具，导致教师端
"成绩单/期末报告/评语/寄语"类意图无法被正确路由（要么 0 工具调用停住，
要么退回到 query_knowledge 知识库问答）。

返回 JSON 字符串，结构：
  {
    "module": "report" | "evaluation" | "ppt" | "image_generate",
    "hint": "前端跳转 /report 或后端拉起 /api/v1/report SSE 的提示文本",
    "payload": {<传给模块的原始参数透传，如学期/学科/学生名单>}
  }

SSE 协议扩展：tool 事件附带 args 字段，runner 据此把 module 名映射进
tool_chain 元素（"report" / "evaluation" / ...），与 eval 期望对齐。
"""

from __future__ import annotations

import json
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field


_MODULE_HINTS: dict[str, str] = {
    "report": "请引导用户到 /report 页面或后端拉起 POST /api/v1/report SSE 上传多科 Excel → 批量生成逐学生报告。",
    "evaluation": "请引导用户到 /evaluation 页面或后端拉起 POST /api/v1/evaluation SSE 生成学期/评语/鼓励类寄语。",
    "ppt": "请引导用户到 /ppt 页面（在 PPT 独立页面有完整拖拽/预览交互，chat 内不生成 PPT）。",
    "image_generate": "请引导用户到 /image-generate 页面（在图片生成独立页面有模型选择/参考图/批量上传等交互）。",
}


class DispatchModuleInput(BaseModel):
    """dispatch_module 工具输入参数。"""

    intent: Literal["report", "evaluation", "ppt", "image_generate"] = Field(
        ...,
        description=(
            "目标模块名。report=成绩单/期末报告；evaluation=评语/寄语/学期总结；"
            "ppt=PPT 生成；image_generate=图片生成。"
        ),
    )
    payload: dict = Field(
        default_factory=dict,
        description="透传给目标模块的原始参数（学期/学科/学生名单等），仅做记录不强制使用。",
    )


@tool(args_schema=DispatchModuleInput)
def dispatch_module(intent: str, payload: dict | None = None) -> str:
    """把当前请求路由到指定独立模块（前端跳转或后端 SSE 端点）。

    使用场景：
    - 教师端提到"成绩单/期末报告/班级报告/道法成绩/汇总表"→ report
    - 教师端提到"评语/寄语/鼓励/学期总结/学生张三"→ evaluation
    - 学生提到"做 PPT / 制作课件"→ ppt
    - 学生提到"生成图片/画一张"→ image_generate

    调用后请用一段自然语言告诉用户：目标模块是哪个 + 让用户在对应页面继续操作。
    """
    payload = payload or {}
    return json.dumps(
        {
            "module": intent,
            "hint": _MODULE_HINTS.get(intent, "请引导用户到对应独立页面继续操作。"),
            "payload": payload,
        },
        ensure_ascii=False,
    )
