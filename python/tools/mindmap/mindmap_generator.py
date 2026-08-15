# -*- coding: utf-8 -*-
"""脑图生成 tool — LLM 大纲 DSL → Python 渲染 HTML/SVG（Docker 无 Node，纯 Python）。

流程：LLM 生成缩进大纲 → 解析为树 → 渲染 HTML（markmap 兼容结构 + 内联 SVG 或列表树）。
失败 → 结构化 error。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from ai.llm_client import build_chat_openai
from ai.llm_task_name import LLMTaskName

logger = logging.getLogger(__name__)


class MindmapGeneratorInput(BaseModel):
    """mindmap_generator 工具输入参数。"""
    topic: str = Field(..., description="脑图主题", min_length=1, max_length=200)
    detail: str = Field(default="", description="内容要点（可空，由 LLM 展开）")
    format: str = Field(default="html", description="输出格式（html/svg）")


def _generate_outline_llm():
    return build_chat_openai(temperature=0.4, max_tokens=2048, task_name=LLMTaskName.MAIN_AGENT_ROUTER)


def _parse_outline(text: str) -> list[tuple[int, str]]:
    """解析缩进大纲 → [(层级, 文本)]。"""
    items: list[tuple[int, str]] = []
    for line in text.splitlines():
        m = re.match(r"^(\s*)[-*•]?\s*(.+)$", line)
        if not m or not m.group(2).strip():
            continue
        indent = len(m.group(1).replace("\t", "  "))
        level = max(1, indent // 2 + 1)
        items.append((level, m.group(2).strip()))
    return items


def _render_svg(items: list[tuple[int, str]], topic: str) -> str:
    """纯 Python SVG 渲染：根节点 + 层级缩进分支（简版，避免引外部依赖）。"""
    width, height = 900, max(200, len(items) * 56 + 60)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<text x="450" y="30" font-size="18" text-anchor="middle" font-weight="bold">{topic}</text>',
    ]
    y = 70
    for level, text in items:
        x = 40 + (level - 1) * 40
        color = ["#333", "#666", "#999", "#bbb"][min(level - 1, 3)]
        parts.append(f'<circle cx="{x - 12}" cy="{y - 5}" r="4" fill="{color}"/>')
        parts.append(f'<text x="{x}" y="{y}" font-size="14" fill="{color}">{ET.fromstring(f"<t>{text}</t>").text}</text>')
        y += 52
    parts.append("</svg>")
    return "\n".join(parts)


def _render_html(items: list[tuple[int, str]], topic: str) -> str:
    """HTML 列表树渲染（markmap 风格结构，纯 HTML 无 JS 依赖）。"""
    def _tree_html(idx: int, level: int) -> tuple[str, int]:
        buf = ["<ul>"]
        while idx < len(items):
            lv, text = items[idx]
            if lv < level:
                break
            if lv == level:
                buf.append(f"<li>{text}")
                child, idx = _tree_html(idx + 1, level + 1)
                buf.append(child if child else "")
                buf.append("</li>")
            else:
                idx += 1
        buf.append("</ul>")
        return "".join(buf), idx

    body, _ = _tree_html(0, 1)
    return f"<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'><title>{topic}</title>"
    f"<style>ul{{list-style:none;border-left:1px solid #ccc;margin:6px 0;padding-left:18px}}"
    f"li{{margin:4px 0;font-size:15px}}</style></head><body><h2>{topic}</h2>{body}</body></html>"


@tool(args_schema=MindmapGeneratorInput)
async def mindmap_generator(topic: str, detail: str = "", format: str = "html") -> str:
    """生成思维导图（LLM 大纲 → Python 渲染 HTML/SVG），返回文件链接。"""
    llm = _generate_outline_llm()
    user = f"为「{topic}」生成层级大纲（每行一条，用缩进或 - 表示层级，根节点下第一层为主题分支）："
    if detail:
        user += f"\n内容要点：{detail}"
    try:
        resp = await llm.ainvoke([HumanMessage(content=user)])
    except Exception as exc:  # noqa: BLE001
        logger.warning("mindmap outline failed: %s", exc)
        return json.dumps({"isError": True, "code": "MINDMAP_FAILED", "message": str(exc)[:200]}, ensure_ascii=False)
    items = _parse_outline(str(resp.content or ""))
    if len(items) < 2:
        return json.dumps({"isError": True, "code": "MINDMAP_EMPTY", "message": "大纲生成失败"}, ensure_ascii=False)
    html = _render_html(items, topic) if format == "html" else _render_svg(items, topic)
    # 落盘产物目录
    out_dir = Path(__file__).resolve().parent.parent.parent / ".documents" / "mindmaps"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"mindmap_{uuid.uuid4().hex[:8]}.{'html' if format == 'html' else 'svg'}"
    path.write_text(html, encoding="utf-8")
    return json.dumps({"file": str(path), "format": format, "node_count": len(items)}, ensure_ascii=False)
