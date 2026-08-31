# -*- coding: utf-8 -*-
"""report 上传批次元数据仓储 — MySQL report_uploads 表 CRUD。

表结构由 sql/init-db.sql 定义，本仓储只做 CRUD，不建表。
与 document_records（知识库）按业务分表不混存；与 report_artifacts（逐学生产物）
粒度不同——本表是「输入侧」上传批次记录（来源 Excel 清单 + 归属 user_id + 状态机）。

设计（可扩展）：
- 一次批量上传 = 一行，file_names 存 JSON 清单；未来需要 per-file 粒度可再拆子表。
- 状态机：processing（已落盘，管线运行中）→ done | error；students_ok/failed 在
  done 时回填，供前端列表展示与后续审计。
"""

from __future__ import annotations

import json

import structlog
from sqlalchemy import text

from .base import MySQLRepository

logger = structlog.get_logger()


class ReportUploadRepository(MySQLRepository):
    """report_uploads CRUD（batch 级：创建 / 状态推进 / 按 user 列表）。"""

    def create_upload(
        self,
        *,
        batch_id: str,
        user_id: str = "",
        semester: str = "",
        user_message: str = "",
        file_names: list[str] | None = None,
        status: str = "processing",
        merged_batch_id: str = "",
    ) -> None:
        if not self.ping():
            raise RuntimeError("MySQL is not available")
        assert self._engine is not None
        file_names = file_names or []
        sql = text(
            """
            INSERT INTO report_uploads (
                batch_id, merged_batch_id, user_id, semester, user_message, file_count,
                file_names, status
            ) VALUES (
                :batch_id, :merged_batch_id, :user_id, :semester, :user_message, :file_count,
                :file_names, :status
            )
            """
        )
        with self._engine.begin() as conn:
            conn.execute(
                sql,
                {
                    "batch_id": batch_id,
                    "merged_batch_id": merged_batch_id,
                    "user_id": user_id,
                    "semester": semester,
                    "user_message": user_message,
                    "file_count": len(file_names),
                    "file_names": json.dumps(file_names, ensure_ascii=False),
                    "status": status,
                },
            )

    def update_status(
        self,
        batch_id: str,
        status: str,
        *,
        error_message: str = "",
        students_ok: int = 0,
        students_failed: int = 0,
        merged_batch_id: str = "",
    ) -> None:
        if not self.ping():
            return
        assert self._engine is not None
        sql = text(
            """
            UPDATE report_uploads
            SET status = :status,
                error_message = :error_message,
                students_ok = :students_ok,
                students_failed = :students_failed,
                merged_batch_id = COALESCE(NULLIF(:merged_batch_id, ''), merged_batch_id)
            WHERE batch_id = :batch_id
            """
        )
        with self._engine.begin() as conn:
            conn.execute(
                sql,
                {
                    "batch_id": batch_id,
                    "status": status,
                    "error_message": error_message,
                    "students_ok": students_ok,
                    "students_failed": students_failed,
                    "merged_batch_id": merged_batch_id,
                },
            )

    def get_by_batch(self, batch_id: str) -> dict | None:
        if not self.ping():
            return None
        assert self._engine is not None
        sql = text(
            """
            SELECT id, batch_id, merged_batch_id, user_id, semester, user_message, file_count,
                   file_names, status, error_message, students_ok, students_failed,
                   created_at, updated_at
            FROM report_uploads WHERE batch_id = :batch_id
            """
        )
        with self._engine.connect() as conn:
            row = conn.execute(sql, {"batch_id": batch_id}).mappings().first()
        return self._row_to_dict(row) if row else None

    def list_by_user(self, user_id: str, limit: int = 50) -> list[dict]:
        if not self.ping():
            return []
        assert self._engine is not None
        sql = text(
            """
            SELECT id, batch_id, merged_batch_id, user_id, semester, user_message, file_count,
                   file_names, status, error_message, students_ok, students_failed,
                   created_at, updated_at
            FROM report_uploads
            WHERE user_id = :user_id
            ORDER BY id DESC
            LIMIT :limit
            """
        )
        with self._engine.connect() as conn:
            rows = conn.execute(sql, {"user_id": user_id, "limit": limit}).mappings().all()
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row) -> dict:
        d = dict(row)
        try:
            d["file_names"] = json.loads(d.get("file_names") or "[]")
        except (TypeError, ValueError):
            d["file_names"] = []
        return d
