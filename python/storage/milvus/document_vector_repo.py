"""文档向量仓储 — 通用知识库（学生手册/个人成绩单）。

- collection: document_chunks
- 分区策略: 用 user_id 作为 partition_key 字段，public 表示公开手册分区，
  其余为个人成绩单分区；检索时按 user_id 过滤，实现个人数据隔离。
"""

from __future__ import annotations

from typing import Any

from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility

from config import get_settings
from ai.embedding_client import EmbeddingClient

PUBLIC_USER = "public"


class DocumentVectorRepository:
    """通用文档向量仓储，支持按 user_id 分区隔离检索。"""

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

        collection_name = settings.document_milvus_collection
        if not utility.has_collection(collection_name):
            schema = CollectionSchema(
                fields=[
                    FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=128, is_primary=True),
                    FieldSchema(name="dataset_id", dtype=DataType.VARCHAR, max_length=64),
                    FieldSchema(name="source_doc_name", dtype=DataType.VARCHAR, max_length=512),
                    FieldSchema(name="chunk_type", dtype=DataType.VARCHAR, max_length=64),
                    FieldSchema(name="page_number", dtype=DataType.INT64),
                    FieldSchema(name="section", dtype=DataType.VARCHAR, max_length=256),
                    FieldSchema(name="user_id", dtype=DataType.VARCHAR, max_length=128, is_partition_key=True),
                    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=settings.milvus_dimension),
                ],
                description="Generic knowledge base document chunks (handbook / transcripts)",
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
        """批量写入 chunk（含向量）。

        chunk 必须包含: chunk_id, dataset_id, source_doc_name, chunk_type,
        page_number, section, user_id, content。
        """
        if not chunks:
            return 0
        self.connect()
        assert self._collection is not None

        contents = [chunk["content"] for chunk in chunks]
        embeddings = self.embedding_client.embed_texts(contents)
        self._collection.upsert(
            [
                [chunk["chunk_id"] for chunk in chunks],
                [chunk["dataset_id"] for chunk in chunks],
                [chunk["source_doc_name"] for chunk in chunks],
                [chunk["chunk_type"] for chunk in chunks],
                [int(chunk.get("page_number", 0)) for chunk in chunks],
                [chunk.get("section", "") for chunk in chunks],
                [chunk.get("user_id", PUBLIC_USER) for chunk in chunks],
                embeddings,
            ]
        )
        self._collection.flush()
        return len(chunks)

    def delete_by_dataset(self, dataset_id: str) -> None:
        """删除某 dataset 的所有 chunk（用于增量更新时旧版本清理）。"""
        self.connect()
        assert self._collection is not None
        self._collection.delete(f'dataset_id == "{dataset_id}"')

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        user_ids: list[str] | None = None,
        query_vector: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        """语义检索，按 user_ids 过滤分区（含公开分区）。

        Args:
            query: 查询文本
            top_k: 返回条数
            user_ids: 允许检索的用户分区；None 表示仅公开分区。
                调用方通常传 ["public", user_id]。
            query_vector: 预计算的 query 向量（复用避免重复 embed）

        Returns:
            [{chunk_id, dataset_id, source_doc_name, chunk_type, page_number,
              section, user_id, distance}]
        """
        self.connect()
        assert self._collection is not None
        if query_vector is None:
            query_vector = self.embedding_client.embed_text(query)

        expr = ""
        allowed = user_ids or [PUBLIC_USER]
        if allowed:
            quoted = ", ".join(f'"{uid}"' for uid in allowed)
            expr = f"user_id in [{quoted}]"

        results = self._collection.search(
            data=[query_vector],
            anns_field="embedding",
            param={"metric_type": self.settings.milvus_metric_type, "params": {}},
            limit=top_k,
            expr=expr or None,
            output_fields=[
                "chunk_id",
                "dataset_id",
                "source_doc_name",
                "chunk_type",
                "page_number",
                "section",
                "user_id",
            ],
        )
        if not results:
            return []
        return [
            {
                "chunk_id": hit.id,
                "dataset_id": str(hit.entity.get("dataset_id", "")),
                "source_doc_name": str(hit.entity.get("source_doc_name", "")),
                "chunk_type": str(hit.entity.get("chunk_type", "")),
                "page_number": int(hit.entity.get("page_number", 0) or 0),
                "section": str(hit.entity.get("section", "")),
                "user_id": str(hit.entity.get("user_id", "")),
                "distance": float(hit.distance),
            }
            for hit in results[0]
        ]

    def ping(self) -> bool:
        try:
            self.connect()
            return True
        except Exception:
            self._collection = None
            return False
