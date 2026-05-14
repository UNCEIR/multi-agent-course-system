"""Backfill missing chunk vectors into Milvus without re-processing already-inserted chunks."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import text

from repositories import CourseRepository, CourseVectorRepository
from services.embedding_client import build_embedding_client


MAX_RETRIES = 5


def embed_with_retry(client, contents: list[str]) -> list[list[float]]:
    for attempt in range(MAX_RETRIES):
        try:
            return client.embed_texts(contents)
        except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as exc:
            wait = 2 ** attempt
            print(f"  connection error (attempt {attempt+1}/{MAX_RETRIES}), waiting {wait}s: {exc}")
            time.sleep(wait)
    raise RuntimeError(f"Failed after {MAX_RETRIES} retries")


def main() -> None:
    course_repo = CourseRepository()
    course_repo.ensure_schema()

    client = build_embedding_client()
    vector_repo = CourseVectorRepository(client)
    vector_repo.connect()

    assert vector_repo._collection is not None

    # Read all chunk rows from MySQL
    assert course_repo._engine is not None
    with course_repo._engine.connect() as conn:
        rows = conn.execute(
            text("SELECT chunk_id, course_id, chunk_type, content FROM course_chunks ORDER BY chunk_index")
        ).mappings().all()

    chunks = [dict(row) for row in rows]
    print(f"MySQL has {len(chunks)} chunks total")
    print(f"Milvus currently has {vector_repo._collection.num_entities} vectors")

    batch = 32  # 32 chunks = 4 API calls per batch, gentler on SSL connections
    total = 0
    for start in range(0, len(chunks), batch):
        batch_chunks = chunks[start : start + batch]
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
        total += len(batch_chunks)
        if (start // batch) % 5 == 0:
            vector_repo._collection.flush()
        time.sleep(2.0)
        print(f"  upserted {total}/{len(chunks)} chunks")

    vector_repo._collection.flush()
    print(f"Done. Milvus now has {vector_repo._collection.num_entities} vectors.")


if __name__ == "__main__":
    main()
