# -*- coding: utf-8 -*-
"""GET /api/v1/images/download：内部图片直链端点。

- images/ 前缀 key：无 token / 无过期（文件在则始终可读），image/* + inline 供 <img> 渲染
- 非 images/ 前缀 → 403 invalid_key（防任意 MinIO 对象下载）
- 对象不存在 → 404 image_not_found

注：本文件直接 await api.images.download_image（不 import agent.app，避免本地慢收集）；
路由注册由 agent/app.py 的 include_router 静态校验覆盖。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


async def _call(file_key: str, data: bytes | None = b"\x89PNG\r\n\x1a\n fake"):
    from agent import runtime

    from api.images import download_image

    with patch("agent.runtime.minio_repo") as minio:
        minio.download = MagicMock(return_value=data)
        return await download_image(file_key=file_key), minio


@pytest.mark.asyncio
async def test_download_image_ok():
    """images/ 内部图片 → 200 image/png + inline（无 token 参数）。"""
    resp, _ = await _call("images/abc123.png")
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("image/png")
    assert resp.headers.get("content-disposition", "").startswith("inline")
    assert resp.body.startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_download_image_rejects_non_images_prefix():
    """非 images/ 前缀 → 403（不能借图片端点下载 report 等任意对象）。"""
    resp, minio = await _call("b1/1.pdf")
    assert resp.status_code == 403
    assert "invalid_key" in resp.body.decode("utf-8")
    minio.download.assert_not_called()


@pytest.mark.asyncio
async def test_download_image_not_found():
    """对象不存在 → 404。"""
    resp, _ = await _call("images/missing.png", data=None)
    assert resp.status_code == 404
    assert "image_not_found" in resp.body.decode("utf-8")


def test_app_registers_images_router():
    """agent/app.py 静态校验：images 路由已 import + include。"""
    import io as _io
    import os

    p = os.path.join(os.path.dirname(__file__), "..", "agent", "app.py")
    src = _io.open(os.path.abspath(p), encoding="utf-8").read()
    assert "images" in src
    assert "app.include_router(images.router)" in src
