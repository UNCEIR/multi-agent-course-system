# -*- coding: utf-8 -*-
"""image_generate_get 重构单测（2026-09-03 图片交付链路修复）。

- _call_mcp 解析兜底：langchain-mcp-adapters 不同包装形态（{"output": [{"text": json}]} / 裸 dict）
- done 后图片字节 base64 直存 MinIO → 返回永不过期的 /api/v1/images/download 内部链接（不再复用 report）
- done 但无图 → isError（不伪造）
"""

from __future__ import annotations

import importlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# @tool 会覆盖 tools.image 包属性为 StructuredTool，这里用 importlib 拿真实模块
iig = importlib.import_module("tools.image.image_generate")
ig = iig


@pytest.mark.unit
def test_extract_text_handles_mcp_wrappers():
    """递归提取 text：裸 dict / output 包装 / list / 对象 .content。"""
    assert ig._extract_text({"text": "hello"}) == "hello"
    assert ig._extract_text({"output": [{"id": "x", "text": "{\"a\":1}", "type": "text"}]}) == "{\"a\":1}"
    assert ig._extract_text([{"type": "text", "text": "hi"}]) == "hi"
    assert ig._extract_text(MagicMock(content="obj-text")) == "obj-text"
    assert ig._extract_text(None) is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_call_mcp_parses_output_wrapped_json():
    """_call_mcp 兜底：MCP 返回 {"output": [{"text": "<json>"}]} 时解析出业务 dict。"""
    payload = {"status": "done", "images_base64": ["aGk="], "image_formats": ["png"]}
    client = AsyncMock()
    client.call_tool = AsyncMock(
        return_value={"output": [{"id": "lc_1", "text": json.dumps(payload, ensure_ascii=False), "type": "text"}]}
    )
    with patch("tools.mcp_client.get_mcp_client", return_value=client):
        result = await ig._call_mcp("generate_image_get", {"task_id": "t1"})
    assert result == payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_done_stores_base64_to_minio_and_returns_images_link():
    """done + images_base64 → base64 解码直存 MinIO，返回永不过期内部链接（无 token/report 复用）。"""
    uploads: list[tuple[str, bytes, str | None]] = []

    class _FakeMinio:
        def upload(self, key, data, content_type=None):
            uploads.append((key, data, content_type))
            return key

    done = {
        "status": "done",
        "images_base64": [__import__("base64").b64encode(b"\x89PNG\r\n\x1a\n real").decode()],
        "image_formats": ["png"],
    }
    with (
        patch("tools.image.image_generate._call_mcp", new=AsyncMock(return_value=done)),
        patch("agent.runtime.minio_repo", _FakeMinio()),
    ):
        out = json.loads(await ig.image_generate_get.coroutine(task_id="t1", attempt=1))
    assert out["status"] == "done"
    assert out["count"] == 1
    assert len(uploads) == 1
    assert uploads[0][0].startswith("images/")
    assert uploads[0][0].endswith(".png")
    assert uploads[0][1].startswith(b"\x89PNG")
    assert uploads[0][2] == "image/png"
    url = out["image_urls"][0]
    assert url.startswith("/api/v1/images/download?file_key=images/")
    assert "token" not in url and "report/download" not in url


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_done_without_image_returns_iserror():
    """done 但既无 base64 也无 URL → NO_STORAGE isError（不伪造链接）。"""
    done = {"status": "done"}
    with patch("tools.image.image_generate._call_mcp", new=AsyncMock(return_value=done)):
        out = json.loads(await ig.image_generate_get.coroutine(task_id="t1", attempt=1))
    assert out.get("isError") is True
    assert out["code"] == "NO_STORAGE"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_done_url_fallback_stores_downloaded_bytes():
    """兜底路径：无 base64 但有 image_urls（24h 签名 URL）→ httpx 下载字节转存。"""
    uploads: list[tuple[str, bytes, str | None]] = []

    class _FakeMinio:
        def upload(self, key, data, content_type=None):
            uploads.append((key, data, content_type))
            return key

    resp = MagicMock()
    resp.content = b"\xff\xd8\xff real-jpeg"
    resp.raise_for_status = MagicMock()
    done = {"status": "done", "image_urls": ["https://example.com/img?x=1"]}
    with (
        patch("tools.image.image_generate._call_mcp", new=AsyncMock(return_value=done)),
        patch("agent.runtime.minio_repo", _FakeMinio()),
        patch("httpx.get", return_value=resp),
    ):
        out = json.loads(await ig.image_generate_get.coroutine(task_id="t1", attempt=1))
    assert out["status"] == "done"
    assert out["count"] == 1
    assert uploads[0][0].endswith(".jpg")  # 魔数嗅探出 jpeg
    assert out["image_urls"][0].startswith("/api/v1/images/download?file_key=images/")
