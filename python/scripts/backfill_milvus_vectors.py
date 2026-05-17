"""Backfill missing chunk vectors into Milvus without re-processing existing chunks."""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import text

from repositories import CourseRepository, CourseVectorRepository
from services.embedding_client import build_embedding_client


MAX_RETRIES = 5
BATCH_SIZE = 32  # 32 chunks = 4 API calls per batch, gentler on SSL connections
INTERVAL_SECONDS = 2.0


def embed_with_retry(client: Any, contents: list[str]) -> list[list[float]]:
    for attempt in range(MAX_RETRIES):
        try:
            return client.embed_texts(contents)
        except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as exc:
            wait = 2**attempt
            print(f"  connection error (attempt {attempt + 1}/{MAX_RETRIES}), waiting {wait}s: {exc}")
            time.sleep(wait)
    raise RuntimeError(f"Failed after {MAX_RETRIES} retries")


def load_mysql_chunks(course_repo: CourseRepository) -> list[dict[str, Any]]:
    assert course_repo._engine is not None
    with course_repo._engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT chunk_id, course_id, chunk_type, content
                FROM course_chunks
                ORDER BY chunk_index
                """
            )
        ).mappings().all()
    return [dict(row) for row in rows]


def load_milvus_chunk_ids(vector_repo: CourseVectorRepository) -> set[str]:
    assert vector_repo._collection is not None
    collection = vector_repo._collection
    collection.load()
    chunk_ids: set[str] = set()
    try:
        iterator = collection.query_iterator(
            expr='chunk_id != ""',
            output_fields=["chunk_id"],
            batch_size=512,
        )
        while True:
            rows = iterator.next()
            if not rows:
                break
            for row in rows:
                value = str(row.get("chunk_id", "")).strip()
                if value:
                    chunk_ids.add(value)
        iterator.close()
    except Exception:
        rows = collection.query(
            expr='chunk_id != ""',
            output_fields=["chunk_id"],
            limit=16384,
        )
        for row in rows:
            value = str(row.get("chunk_id", "")).strip()
            if value:
                chunk_ids.add(value)
    return chunk_ids


def main() -> None:
    course_repo = CourseRepository()
    course_repo.ensure_schema()

    client = build_embedding_client()
    vector_repo = CourseVectorRepository(client)
    vector_repo.connect()

    mysql_chunks = load_mysql_chunks(course_repo)
    mysql_chunk_count = len(mysql_chunks)
    milvus_chunk_ids = load_milvus_chunk_ids(vector_repo)
    milvus_chunk_count = len(milvus_chunk_ids)

    missing_chunks = [chunk for chunk in mysql_chunks if chunk["chunk_id"] not in milvus_chunk_ids]
    missing_count = len(missing_chunks)

    print(f"MySQL has {mysql_chunk_count} chunks total")
    print(f"Milvus currently has {milvus_chunk_count} unique chunk_ids")
    print(f"Missing chunks to backfill: {missing_count}")

    if missing_count == 0:
        print("No missing chunks found, skip embedding and upsert.")
        return

    assert vector_repo._collection is not None
    total_upserted = 0
    for start in range(0, missing_count, BATCH_SIZE):
        batch_chunks = missing_chunks[start : start + BATCH_SIZE]
        contents = [chunk["content"] for chunk in batch_chunks]
        embeddings = embed_with_retry(client, contents)
        vector_repo._collection.upsert(
            [
                [chunk["chunk_id"] for chunk in batch_chunks],
                [chunk["course_id"] for chunk in batch_chunks],
                [chunk["chunk_type"] for chunk in batch_chunks],
                embeddings,
            ]
        )
        total_upserted += len(batch_chunks)
        if (start // BATCH_SIZE) % 5 == 0:
            vector_repo._collection.flush()
        print(f"  upserted missing chunks {total_upserted}/{missing_count}")
        time.sleep(INTERVAL_SECONDS)

    vector_repo._collection.flush()
    print(f"Done. Backfilled {total_upserted} missing chunks.")


if __name__ == "__main__":
    main()
