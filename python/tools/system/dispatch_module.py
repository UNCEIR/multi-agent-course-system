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
    "hint": "该模块的执行方式提示：report/evaluation 指向已挂载的子 agent（用 task 委派走 SKILL.md 流程），ppt/image_generate 指向独立页面",
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
    "report": (
        "目标模块 report：已挂载 report_agent 子 agent（skills=/skills/report-generation/）。"
        "用户已提供可访问的多科 Excel（一科一文件）时，调用 task(subagent_type='report_agent', description=...) "
        "委派子 agent 按 SKILL.md 流程 解析合并→选模板→逐学生填表→渲染 PDF/HTML，返回下载链接；"
        "未提供文件则引导到 /report 页面上传。"
    ),
    "evaluation": (
        "目标模块 evaluation：已挂载 evaluation_agent 子 agent（skills=/skills/evaluation-writing/，五层反幻觉流程）。"
        "调用 task(subagent_type='evaluation_agent', description=<目标学生 user_id + 评语类型>) "
        "委派子 agent 读取 SKILL.md 按 快照→维度→雷达→评语引用核验→落库 执行，返回评语与雷达画像；学生端不触发。"
    ),
    "ppt": "请引导用户到 /ppt 页面（在 PPT 独立页面有完整拖拽/预览交互，chat 内不生成 PPT；可先委派 ppt_agent 规划课件结构）。",
    "image_generate": (
        "目标模块 image_generate：主 agent 已在工具白名单持有 image_generate / image_generate_get，"
        "无需跳页——直接按 image-generation SKILL.md 两段式流程调用（提交 task → 轮询 get → done 返回持久化链接）。"
    ),
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

    调用后按 hint 继续：report/evaluation 模块用 task(subagent_type=...) 委派子 agent
    按各自 SKILL.md 流程真实执行；ppt/image_generate 引导用户到独立页面。
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
