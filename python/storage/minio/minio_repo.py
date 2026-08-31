# -*- coding: utf-8 -*-
"""MinIO 对象存储访问层 — report artifact 存储，带本地磁盘兜底。

- 主存储：MinIO bucket（`minio_report_bucket`，默认 report-artifacts）
- 兜底：MinIO 不可用（连接超时/异常）时降级本地 `python/.documents/reports/`
- 寻址统一：`locate` 先 MinIO 后本地，上层无感

Phase: 2 (implemented)
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class MinioRepository:
    """MinIO 客户端封装 + 本地兜底（双后端统一寻址）。"""

    def __init__(
        self,
        *,
        endpoint: str = "localhost",
        port: int = 9002,
        access_key: str = "minioadmin",
        secret_key: str = "123456",
        secure: bool = False,
        bucket: str = "report-artifacts",
        connect_timeout: float = 3.0,
        local_root: Path | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._port = port
        self._access_key = access_key
        self._secret_key = secret_key
        self._secure = secure
        self._bucket = bucket
        self._connect_timeout = connect_timeout
        self._local_root = local_root or (Path(__file__).resolve().parent.parent.parent / ".documents" / "reports")
        self._client = None
        # 2026-08-31：本地兜底改为「30s 冷却」而非永久锁定——MinIO 恢复后自愈，
        # 避免进程启动时 MinIO 未就绪导致整进程永久降级本地（生成 OK 但文件进不了 MinIO）。
        self._local_until: float = 0.0

    # ── 懒加载客户端 ────────────────────────────────────────────────
    def _get_client(self):
        """首次使用时创建 minio 客户端并探测可用性；失败 → 进入 30s 本地冷却（可自愈）。"""
        import time as _time

        if _time.time() < self._local_until:
            return None
        if self._client is None:
            try:
                from minio import Minio

                self._client = Minio(
                    f"{self._endpoint}:{self._port}",
                    access_key=self._access_key,
                    secret_key=self._secret_key,
                    secure=self._secure,
                )
                # 探测：bucket 不存在则创建（幂等）；异常 → 本地冷却
                if not self._client.bucket_exists(self._bucket):
                    self._client.make_bucket(self._bucket)
                logger.info(f"minio_repo ready bucket={self._bucket} endpoint={self._endpoint}")
            except Exception as exc:  # noqa: BLE001
                logger.warning("minio_repo fallback to local storage: %s", exc)
                self._client = None
                self._local_until = _time.time() + 30.0
        return self._client

    # ── 核心操作（统一寻址：先 MinIO 后本地）─────────────────────────
    def upload(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        """上传数据到 artifact 存储，返回统一对象键（原样 key）。

        注意：minio SDK put_object 的 data 必须是类文件对象（有 read()），
        bytes 直接传入会报 'bytes' object has no attribute 'read'。
        """
        client = self._get_client()
        if client is not None:
            try:
                from io import BytesIO

                client.put_object(
                    self._bucket,
                    key,
                    BytesIO(data),
                    length=len(data),
                    content_type=content_type,
                )
                return key
            except Exception as exc:  # noqa: BLE001
                logger.warning("minio_repo upload failed (%s), falling back to local: %s", key, exc)
                self._local_until = time.time() + 30.0
        local_path = self._local_root / key
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)
        return key

    def download(self, key: str) -> bytes | None:
        """按 key 读取数据：先 MinIO 后本地；都不存在 → None。"""
        client = self._get_client()
        if client is not None:
            try:
                resp = client.get_object(self._bucket, key)
                try:
                    return resp.read()
                finally:
                    resp.close()
                    resp.release_conn()
            except Exception:  # noqa: BLE001
                logger.debug("minio_repo download miss, trying local: %s", key)
        local_path = self._local_root / key
        if local_path.is_file():
            return local_path.read_bytes()
        return None

    def exists(self, key: str) -> bool:
        """文件是否存在（双后端）。"""
        if self.download(key) is not None:
            return True
        return False

    def delete(self, key: str) -> None:
        """删除对象（双后端尽力删除）。"""
        client = self._get_client()
        if client is not None:
            try:
                client.remove_object(self._bucket, key)
            except Exception:  # noqa: BLE001
                pass
        local_path = self._local_root / key
        if local_path.is_file():
            local_path.unlink(missing_ok=True)

    def local_path_for(self, key: str) -> Path:
        """本地兜底路径（测试/诊断用）。"""
        return self._local_root / key

    # ── 状态 ────────────────────────────────────────────────────────
    @property
    def is_local_only(self) -> bool:
        """当前是否处于本地兜底冷却期（冷却内不访问 MinIO，冷却后自动重试）。"""
        import time as _time

        return _time.time() < self._local_until
