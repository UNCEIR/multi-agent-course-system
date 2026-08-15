# -*- coding: utf-8 -*-
"""图片生成 tool（两段式提交）— 即梦 4.0 经自建 MCP server（image/* namespace）。

- image_generate：提交生成任务 → {task_id, status, hint}（立即返回，不等待）
- image_generate_get：查询任务 → done 时转存 MinIO/本地（24h URL 失效兜底）→ 返回持久化链接

两段式链式调用（B1）：agent 提交后按 next_poll_after_seconds 轮询 get；
未 done 不得声称成功（no-fake）；task_id 火山侧 12h 有效可续查。
"""

from __future__ import annotations

import json
import logging
import uuid

from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ImageGenerateInput(BaseModel):
    """image_generate 工具输入参数（提交阶段）。"""
    prompt: str = Field(..., description="图片描述提示词（≤800 字符；组图场景请明确 1-3 张）", min_length=1, max_length=800)
    ratio: str = Field(default="1:1", description="宽高比（1:1 / 16:9 / 9:16 / 3:4 / 4:3；不传则由模型智能判断）")
    style: str = Field(default="", description="风格（写实/插画/动漫/水墨等，可空）")
    negative_prompt: str = Field(default="", description="负面提示词（可空）")
    scale: float = Field(default=0.7, description="文本影响程度 0-1（越大越遵从文本语义）", ge=0, le=1)
    force_single: bool = Field(default=False, description="是否强制单图（false=智能组图，建议 prompt 控制在 3 张内）")


class ImageGenerateGetInput(BaseModel):
    """image_generate_get 工具输入参数（查询阶段）。"""
    task_id: str = Field(..., description="提交任务返回的 task_id")
    attempt: int = Field(default=1, description="当前查询次数（从 1 起）", ge=1, le=20)


def _ratio_to_size(ratio: str) -> tuple[int, int] | None:
    """常用宽高比 → 2K 尺寸（不传则模型智能判断）。"""
    mapping = {
        "1:1": (2048, 2048),
        "16:9": (2560, 1440),
        "9:16": (1440, 2560),
        "3:4": (2304, 1728),
        "4:3": (1728, 2304),
    }
    return mapping.get(ratio)


async def _call_mcp(tool_name: str, args: dict) -> dict:
    """经 MCP 客户端调用自建即梦 server；返回 dict。

    工具为 async（与 agent/调用方同事件循环），直接 await——MCP stdio 连接
    在该循环内建立并常驻，避免跨循环调用异常。
    """
    from tools.mcp_client import get_mcp_client

    client = get_mcp_client()
    result = await client.call_tool("jimeng", tool_name, args)
    if isinstance(result, dict) and "text" in result and "isError" not in result:
        return result
    if isinstance(result, list):
        for item in result:
            text = (item or {}).get("text", "")
            if isinstance(text, str) and text.strip():
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    continue
    if isinstance(result, dict):
        return result
    return {"isError": True, "code": "MCP_RESPONSE_INVALID", "message": "MCP 返回格式异常"}


@tool(args_schema=ImageGenerateInput)
async def image_generate(
    prompt: str,
    ratio: str = "1:1",
    style: str = "",
    negative_prompt: str = "",
    scale: float = 0.7,
    force_single: bool = False,
) -> str:
    """提交即梦 4.0 图片生成任务（两段式：提交后需调用 image_generate_get 轮询拿图）。"""
    full_prompt = prompt
    if style:
        full_prompt = f"{full_prompt}，风格：{style}"
    if negative_prompt:
        full_prompt = f"{full_prompt}，避免：{negative_prompt}"
    if not force_single:
        full_prompt = f"{full_prompt}，请生成 1-3 张内容关联的组图"

    size = _ratio_to_size(ratio)
    args = {
        "prompt": full_prompt,
        "scale": scale,
        "force_single": force_single,
    }
    if size:
        args["size"] = size[0] * size[1]
    # 可重试错误码（限流 50429/50430、后审核 50511/50519）退避重试 2 次
    result = await _call_mcp("generate_image_submit", args)
    if result.get("isError") and result.get("retryable"):
        for backoff in (3.0, 6.0):
            import asyncio

            logger.info("jimeng submit retryable (%s), backoff %ss", result.get("code"), backoff)
            await asyncio.sleep(backoff)
            result = await _call_mcp("generate_image_submit", args)
            if not (result.get("isError") and result.get("retryable")):
                break
    if result.get("isError"):
        return json.dumps(result, ensure_ascii=False)
    task_id = result.get("task_id", "")
    return json.dumps(
        {
            "task_id": task_id,
            "status": result.get("status", "in_queue"),
            "hint": "任务已提交，请调用 image_generate_get 查询结果（未完成前不要声称已生成）",
        },
        ensure_ascii=False,
    )


@tool(args_schema=ImageGenerateGetInput)
async def image_generate_get(task_id: str, attempt: int = 1) -> str:
    """查询即梦生成任务；done 时下载转存 MinIO/本地（24h 链接失效兜底）并返回持久化链接。"""
    result = await _call_mcp("generate_image_get", {"task_id": task_id, "attempt": attempt})
    if result.get("isError"):
        return json.dumps(result, ensure_ascii=False)
    status = result.get("status", "")
    if status != "done":
        return json.dumps(
            {
                "task_id": task_id,
                "status": status,
                "next_poll_after_seconds": result.get("next_poll_after_seconds", 3),
                "attempts_left": result.get("attempts_left", 0),
                "hint": "任务尚未完成，请按 next_poll_after_seconds 等待后再次查询",
            },
            ensure_ascii=False,
        )
    # done：转存（24h URL → MinIO/本地）
    urls = result.get("image_urls", [])
    if not urls:
        return json.dumps({"isError": True, "code": "NO_IMAGE", "message": "任务完成但未返回图片 URL"}, ensure_ascii=False)
    stored = [_store_image(u) for u in urls]
    return json.dumps({"task_id": task_id, "status": "done", "image_urls": stored, "count": len(stored)}, ensure_ascii=False)


def _store_image(url: str) -> str:
    """下载图片到 MinIO/本地；失败原样返回 24h URL（标注时效）。"""
    import httpx

    from config import get_settings

    try:
        resp = httpx.get(url, verify=get_settings().httpx_verify_ssl, timeout=60.0)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("image download failed: %s", exc)
        return url  # 原样返回外部 URL（24h 有效，尽力而为）
    key = f"images/{uuid.uuid4().hex[:12]}.png"
    try:
        from agent import runtime

        runtime.minio_repo.upload(key, resp.content, content_type="image/png")
        return f"/api/v1/report/download?file_key={key}&token=__IMG__"
    except Exception:  # noqa: BLE001
        return url
