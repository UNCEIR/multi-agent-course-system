from __future__ import annotations

import json
import time
from typing import Any

import structlog
from sqlalchemy import text

from models.schemas import Course

from .base import MySQLRepository

logger = structlog.get_logger()


class CourseRepository(MySQLRepository):
    def upsert_course(self, row: dict[str, Any]) -> None:
        if not self.ping():
            raise RuntimeError("MySQL is not available")
        assert self._engine is not None

        sql = text(
            """
            INSERT INTO course_records (
                course_id, course_name, teacher, credits, course_type, course_category,
                domain, campus, time_slot, capacity, current_enrolled, popularity_level,
                has_exam, group_work_required, tags, raw_json
            ) VALUES (
                :course_id, :course_name, :teacher, :credits, :course_type, :course_category,
                :domain, :campus, :time_slot, :capacity, :current_enrolled, :popularity_level,
                :has_exam, :group_work_required, :tags, :raw_json
            )
            ON DUPLICATE KEY UPDATE
                course_name = VALUES(course_name),
                teacher = VALUES(teacher),
                credits = VALUES(credits),
                course_type = VALUES(course_type),
                course_category = VALUES(course_category),
                domain = VALUES(domain),
                campus = VALUES(campus),
                time_slot = VALUES(time_slot),
                capacity = VALUES(capacity),
                current_enrolled = VALUES(current_enrolled),
                popularity_level = VALUES(popularity_level),
                has_exam = VALUES(has_exam),
                group_work_required = VALUES(group_work_required),
                tags = VALUES(tags),
                raw_json = VALUES(raw_json)
            """
        )
        with self._engine.begin() as conn:
            conn.execute(sql, self._course_params(row))

    def replace_course_chunks(self, course_id: str, chunks: list[dict[str, Any]]) -> None:
        if not self.ping():
            raise RuntimeError("MySQL is not available")
        assert self._engine is not None

        delete_sql = text("DELETE FROM course_chunks WHERE course_id = :course_id")
        insert_sql = text(
            """
            INSERT INTO course_chunks (
                chunk_id, course_id, chunk_index, chunk_type, content, metadata_json
            ) VALUES (
                :chunk_id, :course_id, :chunk_index, :chunk_type, :content, :metadata_json
            )
            """
        )
        with self._engine.begin() as conn:
            conn.execute(delete_sql, {"course_id": course_id})
            if chunks:
                conn.execute(insert_sql, chunks)

    def fetch_courses(
        self,
        limit: int,
        domains: list[str] | None = None,
        categories: list[str] | None = None,
        campus: list[str] | None = None,
        query_text: str = "",
    ) -> list[Course]:
        start = time.perf_counter()
        if not self.ping():
            logger.warning(
                "course_repository.fetch_courses.skip",
                reason="mysql_unavailable",
                limit=limit,
                domains_count=len(domains or []),
                categories_count=len(categories or []),
                campus_count=len(campus or []),
                query_len=len(query_text.strip()),
            )
            return []
        assert self._engine is not None

        conditions = ["1 = 1"]
        params: dict[str, Any] = {"limit": limit}
        if domains:
            placeholders = ", ".join(f":domain_{idx}" for idx, _ in enumerate(domains))
            conditions.append(f"domain IN ({placeholders})")
            params.update({f"domain_{idx}": value for idx, value in enumerate(domains)})
        if categories:
            placeholders = ", ".join(f":cat_{idx}" for idx, _ in enumerate(categories))
            conditions.append(f"course_category IN ({placeholders})")
            params.update({f"cat_{idx}": value for idx, value in enumerate(categories)})
        if campus:
            placeholders = ", ".join(f":campus_{idx}" for idx, _ in enumerate(campus))
            conditions.append(f"campus IN ({placeholders})")
            params.update({f"campus_{idx}": value for idx, value in enumerate(campus)})
        if query_text.strip():
            kw = query_text.strip()
            if len(kw) <= 2:
                conditions.append(
                    """
                    (
                        course_name LIKE :query_text OR teacher LIKE :query_text
                        OR course_category LIKE :query_text OR domain LIKE :query_text
                        OR campus LIKE :query_text OR time_slot LIKE :query_text
                        OR tags LIKE :query_text
                    )
                    """
                )
                params["query_text"] = f"%{kw}%"
            else:
                conditions.append(
                    "MATCH(search_text) AGAINST(:query_text IN NATURAL LANGUAGE MODE)"
                )
                params["query_text"] = kw

        sql = f"""
            SELECT course_id, course_name, teacher, credits, course_type, course_category,
                   domain, campus, time_slot, capacity, current_enrolled,
                   popularity_level, has_exam, group_work_required, tags, raw_json
            FROM course_records
            WHERE {" AND ".join(conditions)}
            ORDER BY
                popularity_level DESC,
                current_enrolled DESC,
                course_id ASC
            LIMIT :limit
        """
        with self._engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "course_repository.fetch_courses.done",
            limit=limit,
            domains_count=len(domains or []),
            categories_count=len(categories or []),
            campus_count=len(campus or []),
            query_len=len(query_text.strip()),
            row_count=len(rows),
            latency_ms=round(elapsed_ms, 1),
        )
        return [self._row_to_course(dict(row)) for row in rows]

    def fetch_courses_by_ids(self, course_ids: list[str]) -> list[Course]:
        if not course_ids:
            logger.info("course_repository.fetch_courses_by_ids.skip", reason="empty_ids")
            return []
        start = time.perf_counter()
        if not self.ping():
            logger.warning(
                "course_repository.fetch_courses_by_ids.skip",
                reason="mysql_unavailable",
                id_count=len(course_ids),
            )
            return []
        assert self._engine is not None
        seen_order = list(dict.fromkeys(course_ids))
        placeholders = ", ".join(f":course_{idx}" for idx, _ in enumerate(seen_order))
        params = {f"course_{idx}": value for idx, value in enumerate(seen_order)}
        sql = text(
            f"""
            SELECT course_id, course_name, teacher, credits, course_type, course_category,
                   domain, campus, time_slot, capacity, current_enrolled,
                   popularity_level, has_exam, group_work_required, tags, raw_json
            FROM course_records
            WHERE course_id IN ({placeholders})
            """
        )
        with self._engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "course_repository.fetch_courses_by_ids.done",
            requested_count=len(course_ids),
            unique_id_count=len(seen_order),
            row_count=len(rows),
            latency_ms=round(elapsed_ms, 1),
        )
        id_to_course = {row["course_id"]: self._row_to_course(dict(row)) for row in rows}
        return [id_to_course[course_id] for course_id in seen_order if course_id in id_to_course]

    @staticmethod
    def _course_params(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "course_id": row.get("course_id", ""),
            "course_name": row.get("course_name", ""),
            "teacher": row.get("teacher", ""),
            "credits": float(row.get("credits") or 0),
            "course_type": row.get("course_type", ""),
            "course_category": row.get("course_category", ""),
            "domain": row.get("domain", ""),
            "campus": row.get("campus", ""),
            "time_slot": row.get("time_slot", ""),
            "capacity": int(float(row.get("capacity") or 0)),
            "current_enrolled": int(float(row.get("current_enrolled") or 0)),
            "popularity_level": int(float(row.get("popularity_level") or 0)),
            "has_exam": CourseRepository._parse_binary_flag(row.get("has_exam")),
            "group_work_required": CourseRepository._parse_binary_flag(row.get("group_work_required")),
            "tags": row.get("tags", ""),
            "raw_json": json.dumps(row, ensure_ascii=False),
        }

    @staticmethod
    def _row_to_course(row: dict[str, Any]) -> Course:
        raw = row.get("raw_json") or {}
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {}

        merged = {**raw, **{key: value for key, value in row.items() if value is not None}}
        tags_raw = merged.get("tags", "")
        if isinstance(tags_raw, list):
            tags = [str(tag).strip() for tag in tags_raw if str(tag).strip()]
        else:
            tags = [tag.strip() for tag in str(tags_raw).replace(",", ";").split(";") if tag.strip()]

        capacity = int(float(merged.get("capacity") or 0))
        current_enrolled = int(float(merged.get("current_enrolled") or 0))
        ratio_raw = merged.get("current_enrollment_ratio")
        if ratio_raw in (None, "") and capacity > 0:
            ratio = current_enrolled / capacity
        else:
            ratio = float(ratio_raw or 0.0)

        return Course(
            course_id=str(merged.get("course_id", "")),
            course_name=str(merged.get("course_name", "")),
            teacher=str(merged.get("teacher", "")),
            credits=float(merged.get("credits") or 0.0),
            course_type=str(merged.get("course_type", "公共选修课")),
            course_category=str(merged.get("course_category", "")),
            domain=str(merged.get("domain", "")),
            campus=str(merged.get("campus", "")),
            time_slot=str(merged.get("time_slot", "")),
            location=str(merged.get("location", "")),
            capacity=capacity,
            current_enrolled=current_enrolled,
            current_enrollment_ratio=ratio,
            popularity_level=int(float(merged.get("popularity_level") or 0)),
            rush_advice=str(merged.get("rush_advice", "")),
            description=str(merged.get("description", "")),
            assessment=str(merged.get("assessment", "")),
            difficulty=str(merged.get("difficulty", "")),
            workload=str(merged.get("workload", "")),
            grade_friendly=str(merged.get("grade_friendly", "")),
            has_exam=CourseRepository._parse_binary_flag(merged.get("has_exam")),
            group_work_required=CourseRepository._parse_binary_flag(merged.get("group_work_required")),
            suitable_for=str(merged.get("suitable_for", "")),
            tags=tags,
        )

    @staticmethod
    def _parse_binary_flag(value: Any) -> int:
        if isinstance(value, bool):
            return 1 if value else 0
        text = str(value).strip()
        if text in {"1", "是", "有", "true", "True"}:
            return 1
        return 0
