# -*- coding: utf-8 -*-
"""写作助手 tool — LLM 驱动多体裁/多风格写作（chat 内对话式创作）。"""

from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from ai.llm_client import build_chat_openai
from ai.llm_task_name import LLMTaskName

logger = logging.getLogger(__name__)

GENRES = ("学术论文", "读书报告", "实习报告", "课程设计", "演讲稿", "新闻稿", "散文", "其他")


class WritingAssistantInput(BaseModel):
    """writing_assistant 工具输入参数。"""
    topic: str = Field(..., description="写作主题", min_length=1, max_length=500)
    genre: str = Field(default="其他", description=f"体裁：{'/'.join(GENRES)}")
    outline: str = Field(default="", description="大纲（可选，分点）")
    word_count: int = Field(default=800, description="目标字数", ge=100, le=8000)


_SYSTEM = (
    "你是一名专业中文写作助手。根据用户提供的主题、体裁与大纲撰写文章："
    "结构完整（引言-主体-结论）、语言规范、符合体裁特征；"
    "只输出正文，不要解释写作过程；不得编造引用来源与数据。"
)


@tool(args_schema=WritingAssistantInput)
async def writing_assistant(topic: str, genre: str = "其他", outline: str = "", word_count: int = 800) -> str:
    """根据主题/体裁/大纲生成文章（对话式写作，一次性成稿）。"""
    llm = build_chat_openai(
        temperature=0.6,
        max_tokens=min(word_count * 2 + 512, 8192),
        task_name=LLMTaskName.MAIN_AGENT_ROUTER,
    )
    user = f"主题：{topic}\n体裁：{genre}\n目标字数：{word_count}"
    if outline:
        user += f"\n大纲：\n{outline}"
    try:
        resp = await llm.ainvoke(
            [
                HumanMessage(content=_SYSTEM),
                HumanMessage(content=user),
            ]
        )
        return str(resp.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("writing_assistant failed: %s", exc)
        return json.dumps({"isError": True, "code": "WRITING_FAILED", "message": str(exc)[:200]}, ensure_ascii=False)
