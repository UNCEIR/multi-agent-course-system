# -*- coding: utf-8 -*-
"""图片产物下载端点 — image_generate 转存的内部图片（images/ 前缀 key）。

与 /api/v1/report/download 分离：report 端点承载 report 产物（HMAC 校验 + pdf/html +
attachment 下载语义）；图片是后端自产内部资源（images/<uuid>.<ext>，无隐私、key 随机），
无需鉴权、**永不过期**，一律 image/* + Content-Disposition: inline 供前端 <img>/Markdown 直接渲染。

安全：只放行 images/ 前缀 key（防任意 MinIO 对象下载），对象不存在返回 404。
"""

from __future__ import annotations

import json

import structlog
from fastapi import APIRouter, Query
from fastapi.responses import Response

logger = structlog.get_logger()
router = APIRouter()

_IMAGE_KEY_PREFIX = "images/"
_IMAGE_EXT_CONTENT_TYPE = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


@router.get("/api/v1/images/download")
async def download_image(file_key: str = Query(..., description="MinIO 对象 key（必须 images/ 前缀）")):
    """内部图片直链下载：无 token/无过期（文件在 MinIO/本地兜底则始终可读）。"""
    if not file_key.startswith(_IMAGE_KEY_PREFIX):
        return Response(
            status_code=403,
            content=json.dumps({"code": "invalid_key", "message": "仅允许 images/ 前缀的内部图片 key"}, ensure_ascii=False),
            media_type="application/json",
        )
    from agent import runtime

    data = runtime.minio_repo.download(file_key)
    if data is None:
        return Response(
            status_code=404,
            content=json.dumps({"code": "image_not_found", "message": "图片不存在或已被清理"}, ensure_ascii=False),
            media_type="application/json",
        )
    ext = "." + file_key.rsplit(".", 1)[-1].lower() if "." in file_key else ""
    content_type = _IMAGE_EXT_CONTENT_TYPE.get(ext, "application/octet-stream")
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": 'inline; filename="' + file_key.split("/")[-1] + '"'},
    )
