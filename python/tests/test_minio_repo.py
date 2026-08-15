# -*- coding: utf-8 -*-
"""MinioRepository 单测：MinIO 不可用 → 本地兜底；可用 → 走 MinIO；统一寻址。

构造时注入 tmp 本地根目录，避免污染仓库。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from storage.minio.minio_repo import MinioRepository


def _repo(tmp_path, **kwargs):
    return MinioRepository(
        endpoint="localhost",
        port=9000,
        access_key="minioadmin",
        secret_key="123456",
        bucket="report-artifacts",
        local_root=tmp_path / "reports",
        **kwargs,
    )


class _FakeMinioClient:
    """最小可用 MinIO 客户端替身（put/get/exists/remove）。"""

    def __init__(self):
        self.buckets = set()
        self.objects: dict[str, bytes] = {}

    def bucket_exists(self, bucket):
        return bucket in self.buckets

    def make_bucket(self, bucket):
        self.buckets.add(bucket)

    def put_object(self, bucket, key, data, length=None, content_type=None):
        self.objects[key] = data if isinstance(data, bytes) else data.read()

    def get_object(self, bucket, key):
        if key not in self.objects:
            raise Exception("NoSuchKey")
        resp = MagicMock()
        resp.read.return_value = self.objects[key]
        resp.close.return_value = None
        resp.release_conn.return_value = None
        return resp

    def remove_object(self, bucket, key):
        self.objects.pop(key, None)


@pytest.mark.unit
def test_minio_unavailable_falls_back_to_local(tmp_path):
    """MinIO 连接失败 → 本地兜底模式，上传/下载/寻址仍可用。"""
    with patch("minio.Minio", side_effect=Exception("connection refused")):
        repo = _repo(tmp_path)

        key = repo.upload("b1/s1.pdf", b"pdf-bytes", content_type="application/pdf")

        assert repo.is_local_only is True
        assert key == "b1/s1.pdf"
        assert repo.download("b1/s1.pdf") == b"pdf-bytes"
        assert repo.exists("b1/s1.pdf") is True
        assert (tmp_path / "reports" / "b1" / "s1.pdf").is_file()


@pytest.mark.unit
def test_minio_available_uses_minio(tmp_path):
    """MinIO 可用 → 走 MinIO，不写本地。"""
    fake = _FakeMinioClient()
    with patch("minio.Minio", return_value=fake):
        repo = _repo(tmp_path)

        key = repo.upload("b1/s1.pdf", b"pdf-bytes")

        assert repo.is_local_only is False
        assert key == "b1/s1.pdf"
        assert fake.objects["b1/s1.pdf"] == b"pdf-bytes"
        assert repo.download("b1/s1.pdf") == b"pdf-bytes"
        assert repo.exists("b1/s1.pdf") is True
        assert repo.local_path_for("b1/s1.pdf").exists() is False  # 未落本地


@pytest.mark.unit
def test_minio_upload_failure_falls_back_per_object(tmp_path):
    """MinIO 可用但单次上传失败 → 该对象降级本地，后续统一寻址。"""
    fake = _FakeMinioClient()
    with patch("minio.Minio", return_value=fake):
        repo = _repo(tmp_path)
        repo._get_client()  # 触发探测

        repo._client.put_object = MagicMock(side_effect=Exception("disk full"))
        key = repo.upload("b1/s2.pdf", b"local-bytes")

        assert key == "b1/s2.pdf"
        assert repo.download("b1/s2.pdf") == b"local-bytes"
        assert repo.is_local_only is True


@pytest.mark.unit
def test_download_missing_returns_none(tmp_path):
    """双后端都不存在 → None（下载端点 404 依据）。"""
    with patch("minio.Minio", side_effect=Exception("connection refused")):
        repo = _repo(tmp_path)
        assert repo.download("b1/missing.pdf") is None
        assert repo.exists("b1/missing.pdf") is False


@pytest.mark.unit
def test_delete(tmp_path):
    """删除双后端尽力执行。"""
    fake = _FakeMinioClient()
    with patch("minio.Minio", return_value=fake):
        repo = _repo(tmp_path)
        repo.upload("b1/s1.pdf", b"x")
        repo.delete("b1/s1.pdf")
        assert fake.objects.get("b1/s1.pdf") is None

    with patch("minio.Minio", side_effect=Exception("connection refused")):
        repo = _repo(tmp_path)
        repo.upload("b1/s2.pdf", b"y")
        repo.delete("b1/s2.pdf")
        assert repo.exists("b1/s2.pdf") is False
