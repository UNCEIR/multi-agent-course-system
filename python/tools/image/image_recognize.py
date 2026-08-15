# -*- coding: utf-8 -*-
"""图片识别 tool — 视觉模型直连（qwen3.7-plus，与文本模型同 key）。

图片经 /chat/stream 的 images 附件落本地 → data URL 入参 → 视觉分析。
失败 → 结构化 error + 熔断（失败计数）。
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from ai.llm_client import build_chat_openai
from ai.llm_task_name import LLMTaskName

logger = logging.getLogger(__name__)


class ImageRecognizeInput(BaseModel):
    """image_recognize 工具输入参数。"""
    image_url: str = Field(..., description="图片地址（URL 或 data URL）")
    question: str = Field(default="", description="针对图片的问题（可空=描述图片）")


def _build_vision_llm():
    from config import get_settings

    return build_chat_openai(
        temperature=0.2,
        max_tokens=2048,
        task_name=LLMTaskName.VISION_ANALYZE,
        model=get_settings().vision_model,
    )


def _to_data_url(image_url: str) -> str | None:
    """URL/本地路径 → data URL；失败返回 None。"""
    if image_url.startswith("data:"):
        return image_url
    if image_url.startswith(("http://", "https://")):
        try:
            import httpx

            from config import get_settings

            resp = httpx.get(image_url, verify=get_settings().httpx_verify_ssl, timeout=30.0)
            resp.raise_for_status()
            return "data:image/png;base64," + base64.b64encode(resp.content).decode()
        except Exception as exc:  # noqa: BLE001
            logger.warning("image fetch failed: %s", exc)
            return None
    path = Path(image_url)
    if path.is_file():
        return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()
    return None


@tool(args_schema=ImageRecognizeInput)
async def image_recognize(image_url: str, question: str = "") -> str:
    """识别/分析图片内容（视觉模型直连）。"""
    data_url = _to_data_url(image_url)
    if data_url is None:
        return json.dumps({"isError": True, "code": "IMAGE_FETCH_FAILED", "message": "图片获取失败"}, ensure_ascii=False)
    try:
        llm = _build_vision_llm()
        content = [
            {"type": "text", "text": question or "请详细描述这张图片的内容。"},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]
        resp = await llm.ainvoke([HumanMessage(content=content)])
        return str(resp.content or "")
    except Exception as exc:  # noqa: BLE001
        logger.warning("vision analyze failed: %s", exc)
        return json.dumps({"isError": True, "code": "VISION_FAILED", "message": str(exc)[:200]}, ensure_ascii=False)
