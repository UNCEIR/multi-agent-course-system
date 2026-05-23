from __future__ import annotations

from typing import Any

from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility

from config import get_settings
from services.embedding_client import EmbeddingClient


class CourseVectorRepository:
    def __init__(self, embedding_client: EmbeddingClient):
        self.settings = get_settings()
        self.embedding_client = embedding_client
        self._collection: Collection | None = None

    def connect(self) -> None:
        if self._collection:
            return

        settings = self.settings
        if settings.milvus_uri.strip():
            connections.connect(alias="default", uri=settings.milvus_uri)
        else:
            connections.connect(
                alias="default",
                host=settings.milvus_host,
                port=str(settings.milvus_port),
                user=settings.milvus_user or None,
                password=settings.milvus_password or None,
            )

        collection_name = settings.course_milvus_collection
        if not utility.has_collection(collection_name):
            schema = CollectionSchema(
                fields=[
                    FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=128, is_primary=True),
                    FieldSchema(name="course_id", dtype=DataType.VARCHAR, max_length=64),
                    FieldSchema(name="chunk_type", dtype=DataType.VARCHAR, max_length=64),
                    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=settings.milvus_dimension),
                ],
                description="Public elective course chunk embeddings",
            )
            collection = Collection(collection_name, schema=schema, using="default")
            collection.create_index(
                field_name="embedding",
                index_params={
                    "metric_type": settings.milvus_metric_type,
                    "index_type": settings.milvus_index_type,
                    "params": {},
                },
            )
        self._collection = Collection(collection_name, using="default")
        self._collection.load()

    def upsert_chunks(self, chunks: list[dict[str, Any]]) -> int:
        if not chunks:
            return 0
        self.connect()
        assert self._collection is not None

        contents = [chunk["content"] for chunk in chunks]
        embeddings = self.embedding_client.embed_texts(contents)
        self._collection.upsert(
            [
                [chunk["chunk_id"] for chunk in chunks],
                [chunk["course_id"] for chunk in chunks],
                [chunk["chunk_type"] for chunk in chunks],
                embeddings,
            ]
        )
        self._collection.flush()
        return len(chunks)

    def ping(self) -> bool:
        try:
            self.connect()
            return True
        except Exception:
            self._collection = None
            return False

    def search(
        self, query: str, limit: int = 10, query_vector: list[float] | None = None
    ) -> list[dict[str, object]]:
        self.connect()
        assert self._collection is not None
        if query_vector is not None:
            vector = query_vector
        else:
            vector = self.embedding_client.embed_text(query)
        results = self._collection.search(
            data=[vector],
            anns_field="embedding",
            param={"metric_type": self.settings.milvus_metric_type, "params": {}},
            limit=limit,
            output_fields=["chunk_id", "course_id", "chunk_type"],
        )
        if not results:
            return []
        return [
            {
                "chunk_id": hit.id,
                "course_id": str(hit.entity.get("course_id", "")),
                "chunk_type": str(hit.entity.get("chunk_type", "")),
                "distance": float(hit.distance),
            }
            for hit in results[0]
        ]
