# -*- coding: utf-8 -*-
"""图片生成 tool（两段式提交）— 即梦 4.0 经自建 MCP server（image/* namespace）。

- image_generate：提交生成任务 → {task_id, status, hint}（立即返回，不等待）
- image_generate_get：查询任务 → done 时转存 MinIO/本地（24h URL 失效兜底）→ 返回持久化链接

两段式链式调用（B1）：agent 提交后按 next_poll_after_seconds 轮询 get；
未 done 不得声称成功（no-fake）；task_id 火山侧 12h 有效可续查。
"""

from __future__ import annotations

import base64
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


def _extract_text(result) -> str | None:
    """从 langchain-mcp-adapters 的不同返回形态里提取第一条 text。

    兼容形态：裸 dict{"text": ...} / {"output": [{"id":..., "text": "...", "type": "text"}]}
    / list / 带 .content 的对象（AIMessage/ToolMessage）。
    """
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        text = result.get("text")
        if isinstance(text, str) and text:
            return text
        output = result.get("output")
        if isinstance(output, list):
            for item in output:
                t = _extract_text(item)
                if t:
                    return t
        return _extract_text(result.get("content"))
    if isinstance(result, list):
        for item in result:
            t = _extract_text(item)
            if t:
                return t
    content = getattr(result, "content", None)
    if content is not None:
        return _extract_text(content)
    return None


async def _call_mcp(tool_name: str, args: dict) -> dict:
    """经 MCP 客户端调用自建即梦 server；返回业务 dict。

    解析兜底（2026-09-03）：不同 langchain-mcp-adapters 版本对 MCP 返回的包装不同
    （裸 dict / {"output":[{"text": json}]} / AIMessage），统一先递归取 text 再
    json.loads；解析失败再透传原始 dict，最后兜底结构化错误。
    """
    from tools.mcp_client import get_mcp_client

    client = get_mcp_client()
    result = await client.call_tool("jimeng", tool_name, args)
    text = _extract_text(result)
    if text:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
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
    """查询即梦生成任务；done 时图片字节直存 MinIO/本地，返回永不过期的内部链接（/api/v1/images/download）。"""
    result = await _call_mcp("generate_image_get", {"task_id": task_id, "attempt": attempt, "need_base64": True})
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
    # 转存（24h URL → MinIO/本地）：改为优先用 MCP 返回的图片字节（base64 直存，无外部
    # 24h URL 依赖），为空时回退 image_urls httpx 下载转存；不再复用 report 下载接口。
    stored = await _store_done_images(result)
    if stored is None:
        return json.dumps(
            {"isError": True, "code": "NO_STORAGE", "message": "图片转存失败，请稍后重试（未伪造链接）"},
            ensure_ascii=False,
        )
    return json.dumps({"task_id": task_id, "status": "done", "image_urls": stored, "count": len(stored)}, ensure_ascii=False)


_IMAGE_EXT_CONTENT_TYPE = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _image_ext(data: bytes, ext: str = "png") -> str:
    """按魔数嗅探真实格式（兜底下载可能丢扩展名）；未知则保持传入 ext。"""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return ext if ext in ("png", "jpg", "jpeg", "gif", "webp") else "png"


async def _store_done_images(result: dict) -> list[str] | None:
    """把即梦 done 结果的图片字节转存 MinIO/本地，返回持久化内部链接列表；任一失败返回 None。

    优先级：
    1. images_base64（MCP get 以 need_base64=true 请求，base64 直存，不依赖外部 24h URL）；
    2. image_urls（24h 签名 URL 兜底：httpx 下载后转存）。
    """
    b64s = result.get("images_base64") or []
    formats = result.get("image_formats") or []
    if b64s:
        stored: list[str] = []
        for i, raw in enumerate(b64s):
            try:
                data = base64.b64decode(str(raw))
            except Exception:  # noqa: BLE001
                logger.warning("image base64 decode failed idx=%s err=%s", i, exc)
                return None
            ext = _image_ext(data, str(formats[i]).lower() if i < len(formats) and formats[i] else "png")
            link = _store_image_bytes(data, ext)
            if link is None:
                return None
            stored.append(link)
        return stored
    urls = result.get("image_urls") or []
    if urls:
        stored = []
        for u in urls:
            link = await _store_image_from_url(str(u))
            if link is None:
                return None
            stored.append(link)
        return stored
    logger.warning("image done but no images_base64/image_urls")
    return None


def _store_image_bytes(data: bytes, ext: str = "png") -> str | None:
    """图片字节直存 MinIO/本地（本地兜底），返回永不过期的内部下载链接；失败返回 None。

    不再复用 /api/v1/report/download（report 产物专用、HMAC + pdf/html）；图片走
    /api/v1/images/download（image/* + inline、无 token、无过期）。
    """
    if not data:
        return None
    ext = _image_ext(data, ext)
    key = f"images/{uuid.uuid4().hex[:12]}.{ext}"
    try:
        from agent import runtime

        content_type = _IMAGE_EXT_CONTENT_TYPE.get("." + ext, "application/octet-stream")
        runtime.minio_repo.upload(key, data, content_type=content_type)
    except Exception as exc:  # noqa: BLE001
        logger.warning("image store failed key=%s err=%s", key, exc)
        return None
    return f"/api/v1/images/download?file_key={key}"


async def _store_image_from_url(url: str) -> str | None:
    """24h 签名 URL 兜底：httpx 下载字节后转存；失败返回 None（不静默返回死链）。"""
    import httpx

    from config import get_settings

    try:
        resp = httpx.get(url, verify=get_settings().httpx_verify_ssl, timeout=60.0)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("image download failed: %s", exc)
        return None
    return _store_image_bytes(resp.content, "png")
