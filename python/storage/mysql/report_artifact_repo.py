"""report 产物元数据仓储 — MySQL report_artifacts 表 CRUD。

表结构由 sql/init-db.sql 定义，本仓储只做 CRUD，不建表。
"""

from __future__ import annotations

import structlog
from sqlalchemy import text

from .base import MySQLRepository

logger = structlog.get_logger()


class ReportArtifactRepository(MySQLRepository):
    """report_artifacts CRUD（一学生一行，支持失败重试/下载寻址/审计）。"""

    def create_artifact(
        self,
        *,
        batch_id: str,
        student_id: str,
        student_name: str = "",
        format: str = "pdf",
        status: str = "ok",
        file_key: str = "",
        token_expires_at=None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        if not self.ping():
            raise RuntimeError("MySQL is not available")
        assert self._engine is not None
        sql = text(
            """
            INSERT INTO report_artifacts (
                batch_id, student_id, student_name, format, status, file_key,
                token_expires_at, error_code, error_message
            ) VALUES (
                :batch_id, :student_id, :student_name, :format, :status, :file_key,
                :token_expires_at, :error_code, :error_message
            )
            """
        )
        with self._engine.begin() as conn:
            conn.execute(
                sql,
                {
                    "batch_id": batch_id,
                    "student_id": student_id,
                    "student_name": student_name,
                    "format": format,
                    "status": status,
                    "file_key": file_key,
                    "token_expires_at": token_expires_at,
                    "error_code": error_code,
                    "error_message": error_message,
                },
            )

    def list_by_batch(self, batch_id: str) -> list[dict]:
        if not self.ping():
            return []
        assert self._engine is not None
        sql = text(
            """
            SELECT id, batch_id, student_id, student_name, format, status, file_key,
                   token_expires_at, error_code, error_message, created_at
            FROM report_artifacts WHERE batch_id = :batch_id ORDER BY id
            """
        )
        with self._engine.connect() as conn:
            rows = conn.execute(sql, {"batch_id": batch_id}).mappings().all()
        return [dict(r) for r in rows]

    def get_by_batch_student(self, batch_id: str, student_id: str) -> dict | None:
        if not self.ping():
            return None
        assert self._engine is not None
        sql = text(
            """
            SELECT id, batch_id, student_id, student_name, format, status, file_key,
                   token_expires_at, error_code, error_message, created_at
            FROM report_artifacts
            WHERE batch_id = :batch_id AND student_id = :student_id
            ORDER BY id DESC LIMIT 1
            """
        )
        with self._engine.connect() as conn:
            row = conn.execute(sql, {"batch_id": batch_id, "student_id": student_id}).mappings().first()
        return dict(row) if row else None

    def list_latest_by_student(self, student_id: str, limit: int = 10) -> list[dict]:
        if not self.ping():
            return []
        assert self._engine is not None
        sql = text(
            """
            SELECT id, batch_id, student_id, student_name, format, status, file_key,
                   token_expires_at, error_code, error_message, created_at
            FROM report_artifacts WHERE student_id = :student_id AND status = 'ok'
            ORDER BY id DESC LIMIT :limit
            """
        )
        with self._engine.connect() as conn:
            rows = conn.execute(sql, {"student_id": student_id, "limit": limit}).mappings().all()
        return [dict(r) for r in rows]
