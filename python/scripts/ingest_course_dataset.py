from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from storage import CourseRepository, CourseVectorRepository
from ai import LLMTaskName, build_embedding_client


DEFAULT_CSV = Path(__file__).resolve().parents[2] / "course_dataset_tools" / "output" / "public_elective_courses.csv"


# region agent log
def _agent_debug_log(hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
    payload = {
        "sessionId": "e14d6c",
        "runId": "mysql-ingest-pre-fix",
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    Path("debug-e14d6c.log").open("a", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False) + "\n")
# endregion


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest public elective CSV chunks into MySQL and Milvus.")
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="CSV file path")
    parser.add_argument("--limit", type=int, default=0, help="Optional max rows to ingest")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    # region agent log
    _agent_debug_log(
        "H2-H5",
        "python/scripts/ingest_course_dataset.py:main",
        "ingest script started",
        {"csv_path": str(csv_path), "limit": args.limit, "cwd": str(Path.cwd())},
    )
    # endregion
    rows = _read_rows(csv_path)
    if args.limit > 0:
        rows = rows[: args.limit]
    # region agent log
    _agent_debug_log(
        "H5",
        "python/scripts/ingest_course_dataset.py:main",
        "csv rows loaded",
        {"row_count": len(rows), "csv_exists": csv_path.exists()},
    )
    # endregion

    course_repo = CourseRepository()
    course_repo.ensure_schema()
    vector_repo = CourseVectorRepository(build_embedding_client(task_name=LLMTaskName.BACKFILL))

    total_chunks = 0
    for row in rows:
        course_repo.upsert_course(row)
        chunks = _build_chunks(row)
        course_repo.replace_course_chunks(row["course_id"], chunks)
        total_chunks += vector_repo.upsert_chunks(chunks)

    print(
        json.dumps(
            {
                "csv": str(csv_path),
                "courses": len(rows),
                "chunks": total_chunks,
                "status": "ok",
            },
            ensure_ascii=False,
        )
    )


def _read_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        return [dict(row) for row in csv.DictReader(file)]


def _build_chunks(row: dict[str, Any]) -> list[dict[str, Any]]:
    chunk_specs = [
        (
            "basic",
            [
                "course_name",
                "teacher",
                "credits",
                "course_type",
                "course_category",
                "domain",
            ],
        ),
        (
            "schedule_capacity",
            [
                "campus",
                "time_slot",
                "location",
                "capacity",
                "current_enrolled",
                "current_enrollment_ratio",
                "popularity_level",
                "rush_advice",
            ],
        ),
        (
            "learning_profile",
            [
                "description",
                "assessment",
                "difficulty",
                "workload",
                "grade_friendly",
                "has_exam",
                "group_work_required",
            ],
        ),
        (
            "audience_tags",
            [
                "suitable_for",
                "tags",
                "avg_history_enrollment_ratio",
            ],
        ),
    ]

    chunks: list[dict[str, Any]] = []
    for index, (chunk_type, fields) in enumerate(chunk_specs):
        content = _render_chunk(row, fields)
        chunk_id = f"{row['course_id']}:{index}:{chunk_type}"
        chunks.append(
            {
                "chunk_id": chunk_id,
                "course_id": row["course_id"],
                "chunk_index": index,
                "chunk_type": chunk_type,
                "content": content,
                "metadata_json": json.dumps(
                    {
                        "course_name": row.get("course_name", ""),
                        "teacher": row.get("teacher", ""),
                        "domain": row.get("domain", ""),
                        "course_category": row.get("course_category", ""),
                        "tags": row.get("tags", ""),
                    },
                    ensure_ascii=False,
                ),
            }
        )
    return chunks


def _render_chunk(row: dict[str, Any], fields: list[str]) -> str:
    labels = {
        "course_name": "课程名称",
        "teacher": "教师",
        "credits": "学分",
        "course_type": "课程类型",
        "course_category": "课程分类",
        "domain": "方向",
        "campus": "校区",
        "time_slot": "上课时间",
        "location": "地点",
        "capacity": "限选人数",
        "current_enrolled": "已选人数",
        "current_enrollment_ratio": "当前选课比例",
        "popularity_level": "热度",
        "rush_advice": "抢课建议",
        "description": "课程简介",
        "assessment": "考核方式",
        "difficulty": "难度",
        "workload": "作业量",
        "grade_friendly": "给分友好度",
        "has_exam": "是否考试",
        "group_work_required": "是否小组作业",
        "suitable_for": "适合人群",
        "tags": "标签",
        "avg_history_enrollment_ratio": "历年平均选课比例",
    }
    lines = [
        f"{labels.get(field, field)}：{_display_value(field, value)}"
        for field in fields
        if (value := row.get(field, "")) is not None and str(value) != ""
    ]
    return "\n".join(lines)


def _display_value(field: str, value: Any) -> Any:
    if field in {"has_exam", "group_work_required"}:
        return "有" if str(value).strip() in {"1", "是", "有", "true", "True"} else "无"
    return value


if __name__ == "__main__":
    main()
