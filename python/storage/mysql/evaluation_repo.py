"""evaluation 评价档案仓储 — MySQL evaluation_records 表 CRUD。

表结构由 sql/init-db.sql 定义，本仓储只做 CRUD，不建表。
"""

from __future__ import annotations

import json

import structlog
from sqlalchemy import text

from .base import MySQLRepository

logger = structlog.get_logger()


class EvaluationRepository(MySQLRepository):
    """evaluation_records CRUD（教师端生成 → 学生端读取，append 历史）。"""

    def insert(
        self,
        *,
        target_user_id: str,
        comment_type: str,
        radar: dict,
        comment: str,
        status: str = "generated",
        generated_by: str = "",
    ) -> int:
        if not self.ping():
            raise RuntimeError("MySQL is not available")
        assert self._engine is not None
        sql = text(
            """
            INSERT INTO evaluation_records (
                target_user_id, comment_type, radar_json, comment, status, generated_by
            ) VALUES (
                :target_user_id, :comment_type, :radar_json, :comment, :status, :generated_by
            )
            """
        )
        with self._engine.begin() as conn:
            result = conn.execute(
                sql,
                {
                    "target_user_id": target_user_id,
                    "comment_type": comment_type,
                    "radar_json": json.dumps(radar, ensure_ascii=False),
                    "comment": comment,
                    "status": status,
                    "generated_by": generated_by,
                },
            )
        return int(result.lastrowid)

    def list_by_user(self, target_user_id: str, limit: int = 20) -> list[dict]:
        if not self.ping():
            return []
        assert self._engine is not None
        sql = text(
            """
            SELECT id, target_user_id, comment_type, radar_json, comment, status,
                   generated_by, created_at
            FROM evaluation_records
            WHERE target_user_id = :target_user_id
            ORDER BY id DESC LIMIT :limit
            """
        )
        with self._engine.connect() as conn:
            rows = conn.execute(sql, {"target_user_id": target_user_id, "limit": limit}).mappings().all()
        out = []
        for row in rows:
            radar = row["radar_json"]
            if isinstance(radar, str) and radar:
                try:
                    radar = json.loads(radar)
                except (json.JSONDecodeError, TypeError):
                    radar = {}
            out.append(
                {
                    "id": int(row["id"]),
                    "target_user_id": str(row["target_user_id"]),
                    "comment_type": str(row["comment_type"]),
                    "radar": radar or {},
                    "comment": str(row["comment"] or ""),
                    "status": str(row["status"]),
                    "generated_by": str(row["generated_by"] or ""),
                    "created_at": str(row["created_at"]),
                }
            )
        return out
