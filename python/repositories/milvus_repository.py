from __future__ import annotations

from typing import Any

from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility

from config import get_settings
from services.embedding_client import EmbeddingClient


class MilvusRepository:
    def __init__(self, embedding_client: EmbeddingClient):
        self.settings = get_settings()
        self.embedding_client = embedding_client
        self._collection: Collection | None = None

    @property
    def is_available(self) -> bool:
        return self._collection is not None

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

        collection_name = settings.milvus_collection
        if not utility.has_collection(collection_name):
            schema = CollectionSchema(
                fields=[
                    FieldSchema(name="product_id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
                    FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=64),
                    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=settings.milvus_dimension),
                ],
                description="E-commerce product embeddings",
            )
            collection = Collection(collection_name, schema=schema, using="default")
            index_params = {
                "metric_type": settings.milvus_metric_type,
                "index_type": settings.milvus_index_type,
                "params": {},
            }
            collection.create_index(field_name="embedding", index_params=index_params)
        self._collection = Collection(collection_name, using="default")
        self._collection.load()

    def ping(self) -> bool:
        try:
            self.connect()
            return True
        except Exception:
            self._collection = None
            return False

    def upsert_products(self, products: list[dict[str, Any]]) -> int:
        if not products or not self.ping():
            return 0
        assert self._collection is not None

        product_ids = [p["product_id"] for p in products]
        categories = [p.get("category", "") for p in products]
        embeddings = [
            self.embedding_client.embed_text(
                " ".join(
                    [
                        p.get("name", ""),
                        p.get("category", ""),
                        " ".join(p.get("tags", [])),
                    ]
                )
            )
            for p in products
        ]

        self._collection.upsert([product_ids, categories, embeddings])
        self._collection.flush()
        return len(product_ids)

    def search(self, query: str, limit: int = 20) -> list[str]:
        if not query.strip() or not self.ping():
            return []
        assert self._collection is not None
        vector = self.embedding_client.embed_text(query)
        results = self._collection.search(
            data=[vector],
            anns_field="embedding",
            param={"metric_type": self.settings.milvus_metric_type, "params": {}},
            limit=limit,
            output_fields=["product_id"],
        )
        if not results:
            return []
        return [hit.id for hit in results[0]]
