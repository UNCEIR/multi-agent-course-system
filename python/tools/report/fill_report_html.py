# -*- coding: utf-8 -*-
"""report 模板填充器 — LLM 填充为主 + 确定性校验 + Jinja2 降级。

- 锚点规范：`<span class="fill" data-slot="<学科>|<维度>|grade"></span>`
  班级/姓名 = class|name / student|name；学期 = semester；评语区 = comment
- LLM 填充：复用 llm_model（task_name=REPORT_HTML_FILL），模板不可删改约束
- 输出校验（代码）：结构校验（锚点全集存在性 + 标签闭合）+ 数值回填校验
  （逐 data-slot 文本 vs 源 JSON 逐字段比对）→ 不一致错误回灌重试 1 次
- 降级：LLM 失败/校验不过 → 确定性锚点替换（同一模板文件）

Phase: 2 (implemented)
"""

from __future__ import annotations

import re
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

from ai.llm_client import build_chat_openai
from ai.llm_task_name import LLMTaskName
from tools.report.contract import canonical_dimension, canonical_subject

TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates" / "report"

_FILL_SPAN = re.compile(r'<span class="fill" data-slot="([^"]+)">([^<]*)</span>')
_OPEN_TAGS = ("table", "tr", "td", "th", "span", "div", "p", "h2", "h3", "b", "i", "ul", "li", "style", "head", "body", "html")


def get_template(name: str) -> str:
    """读取锚点模板（模板文件 = 契约）。"""
    path = TEMPLATE_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"report 模板不存在: {path}")
    return path.read_text(encoding="utf-8")


def build_fill_llm() -> BaseChatModel:
    """填表 LLM：复用 llm_model，长输出 + 低温。"""
    return build_chat_openai(
        temperature=0.1,
        max_tokens=8192,
        task_name=LLMTaskName.REPORT_HTML_FILL,
    )


def fill_prompt() -> str:
    prompt_path = Path(__file__).resolve().parent / "prompts" / "fill_template.txt"
    return prompt_path.read_text(encoding="utf-8")


# ── 结构校验 ────────────────────────────────────────────────────────────
def validate_structure(html: str, template: str) -> list[str]:
    """结构校验：模板锚点全集都在输出中（一个不少）+ comment 槽存在 + 标签闭合。

    返回错误清单（空 = 通过）。
    """
    errors: list[str] = []
    template_slots = {m.group(1) for m in _FILL_SPAN.finditer(template)}
    output_slots = {m.group(1) for m in _FILL_SPAN.finditer(html)}
    missing = template_slots - output_slots
    if missing:
        errors.append(f"模板锚点缺失: {sorted(missing)[:10]}")
    # 评语区锚点可能在 <p>（非 span），按原始属性字符串检查
    if 'data-slot="comment"' not in html:
        errors.append("评语区锚点缺失")
    # 简单标签闭合校验（忽略自闭合/void 标签）
    stack: list[str] = []
    for m in re.finditer(r"</?([a-zA-Z][a-zA-Z0-9]*)(?:\s[^>]*?)?>", html):
        tag = m.group(1).lower()
        if tag in ("meta", "br", "input", "img", "hr", "link"):
            continue
        if m.group(0).startswith("</"):
            if stack and stack[-1] == tag:
                stack.pop()
        else:
            stack.append(tag)
    if stack:
        errors.append(f"标签未闭合: {stack[-5:]}")
    return errors


# ── 数值回填校验 ────────────────────────────────────────────────────────
def _expected_slots(student: dict) -> dict[str, str]:
    """从学生 JSON 计算期望槽值：{slot: value}（空值 = 留空）。

    解析器维度形如「综合答辩·等级」（父·子 复合），槽位名取规范化后的
    子维度（综合答辩）——与模板锚点名一致。
    """
    expected: dict[str, str] = {}
    expected["class|name"] = student.get("class", "")
    expected["student|name"] = student.get("name", "")
    expected["semester"] = student.get("semester", "")
    for subj in student.get("score", []):
        subject = canonical_subject(subj.get("subject", ""))
        for dim, grade in subj.items():
            if dim == "subject":
                continue
            base = dim.split("·")[0] if "·" in dim else dim
            expected[f"{subject}|{canonical_dimension(base)}|grade"] = str(grade)
    return expected


def validate_backfill(html: str, student: dict) -> list[str]:
    """数值回填校验：输出锚点文本 vs 期望槽值逐字段比对（防漏填/错填/编造）。"""
    errors: list[str] = []
    expected = _expected_slots(student)
    filled = {m.group(1): m.group(2).strip() for m in _FILL_SPAN.finditer(html)}
    for slot, want in expected.items():
        got = filled.get(slot, "")
        if want == "":
            continue  # 没给到就留空（允许空）
        if got != want:
            errors.append(f"槽 {slot}: 期望 '{want}' 实得 '{got}'")
    return errors


# ── 确定性降级填充（Jinja2 语义：同一模板 + 锚点替换）──────────────────
def fill_with_jinja2(template: str, student: dict) -> str:
    """确定性填充：锚点替换为期望值（与 LLM 共用同一模板文件）。"""
    expected = _expected_slots(student)
    html = template

    def _repl(m: re.Match) -> str:
        slot = m.group(1)
        value = expected.get(slot, "")
        return f'<span class="fill" data-slot="{slot}">{value}</span>'

    return _FILL_SPAN.sub(_repl, html)


# ── LLM 填充 ────────────────────────────────────────────────────────────
async def fill_one_llm(template: str, student: dict, llm: BaseChatModel | None = None, *, retries: int = 1) -> str:
    """LLM 填表：输入模板全文 + 学生 JSON → 输出完整 HTML。

    校验不过 → 差异明细回灌重试（retries 次）；仍不过 → 抛 FillValidationError。
    """
    import json

    llm = llm or build_fill_llm()
    prompt = fill_prompt()
    student_json = json.dumps(student, ensure_ascii=False, indent=2)

    content = f"{prompt}\n\n模板：\n```html\n{template}\n```\n\n学生数据：\n```json\n{student_json}\n```\n请输出填好的完整 HTML。"
    msg = HumanMessage(content=content)
    output = ""
    for attempt in range(retries + 1):
        resp = await llm.ainvoke([msg])
        output = str(resp.content or "")
        struct_errors = validate_structure(output, template)
        if not struct_errors:
            backfill_errors = validate_backfill(output, student)
            if not backfill_errors:
                return output
            errors = backfill_errors
        else:
            errors = struct_errors
        msg = HumanMessage(
            content=content + f"\n\n上一轮输出校验失败：{errors[:5]}\n请严格按模板与数据重新输出完整 HTML。"
        )
    raise FillValidationError(errors)


class FillValidationError(Exception):
    """LLM 填表校验失败（调用方转 Jinja2 降级）。"""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors[:5]))
