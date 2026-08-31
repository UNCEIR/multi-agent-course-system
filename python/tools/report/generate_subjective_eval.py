# -*- coding: utf-8 -*-
"""报告单「学生综合评价」LLM 主观评语生成器。

- 输入：该生全科等级 JSON（确定性数据，来自中间形态）
- 约束：只基于给定等级、禁止编造科目/数字、30-80 字、语气规范
- 兜底：失败/超时 → 返回 ""（评语区留空，不阻塞交付），错误进 trace

Phase: 2 (implemented)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

from ai.llm_client import build_chat_openai
from ai.llm_task_name import LLMTaskName


def _prompt() -> str:
    path = Path(__file__).resolve().parent / "prompts" / "subjective_eval.txt"
    return path.read_text(encoding="utf-8")


def build_subjective_llm() -> BaseChatModel:
    return build_chat_openai(
        temperature=0.5,
        max_tokens=1024,
        task_name=LLMTaskName.REPORT_SUBJECTIVE_EVAL,
    )


async def generate_subjective_eval(
    student: dict,
    llm: BaseChatModel | None = None,
    *,
    timeout_seconds: float = 60.0,
    user_message: str = "",
) -> str:
    """生成综合评语；失败/超时 → ""（留空不阻塞）。

    user_message：前端「补充要求」，注入评语提示词（如语气/重点），让该字段真正影响产物。
    """
    llm = llm or build_subjective_llm()
    data = json.dumps(student, ensure_ascii=False, indent=2)
    content = f"{_prompt()}\n\n学生成绩数据：\n```json\n{data}\n```"
    um = (user_message or "").strip()
    if um:
        content += f"\n\n用户补充要求（评语需体现，不得与成绩数据冲突）：{um}"
    msg = HumanMessage(content=content)
    try:
        resp = await asyncio.wait_for(llm.ainvoke([msg]), timeout=timeout_seconds)
        text = str(resp.content or "").strip()
        return _sanitize(text)
    except Exception:  # noqa: BLE001
        return ""


def _sanitize(text: str) -> str:
    """去噪：截断过长/去围栏/去解释性前缀。"""
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            text = text.split("\n", 1)[1]
    text = text.strip()
    # 只保留中文、常见中文标点与等级字符（防御性清洗，去掉模型废话/代码痕迹）
    keep = lambda ch: (0x4E00 <= ord(ch) <= 0x9FFF) or ch in "，。！？、；：（）ABCDEF \n"
    text = "".join(ch for ch in text if keep(ch))
    return text[:200]
