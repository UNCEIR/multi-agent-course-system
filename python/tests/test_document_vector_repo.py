# -*- coding: utf-8 -*-
"""document_vector_repo 仓储测试（mock Milvus）。

验证：user_id 分区 upsert/search 过滤、dataset 级删除、公开/个人分区隔离。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def settings():
    s = MagicMock()
    s.milvus_uri = ""
    s.milvus_host = "localhost"
    s.milvus_port = 19530
    s.milvus_user = ""
    s.milvus_password = ""
    s.document_milvus_collection = "document_chunks"
    s.milvus_dimension = 1024
    s.milvus_metric_type = "COSINE"
    s.milvus_index_type = "AUTOINDEX"
    with patch("storage.milvus.document_vector_repo.get_settings", return_value=s):
        yield s


class _FakeCollection:
    def __init__(self):
        self.upserted = None
        self.deleted = None
        self.search_expr = None
        self.search_result = []

    def upsert(self, rows):
        self.upserted = rows

    def flush(self):
        pass

    def delete(self, expr):
        self.deleted = expr

    def search(self, *, data, anns_field, param, limit, expr, output_fields):
        self.search_expr = expr
        return [self.search_result]

    def load(self):
        pass


def _build_repo(settings, fake_collection):
    from storage.milvus.document_vector_repo import DocumentVectorRepository

    embedding = MagicMock()
    embedding.embed_text.return_value = [0.0] * 8
    embedding.embed_texts.return_value = [[0.0] * 8] * 5
    repo = DocumentVectorRepository(embedding)
    repo._collection = fake_collection
    return repo


def test_upsert_chunks_writes_partition_key(settings):
    fake = _FakeCollection()
    repo = _build_repo(settings, fake)
    chunks = [
        {
            "chunk_id": f"c{i}",
            "dataset_id": "ds1",
            "source_doc_name": "手册.pdf",
            "chunk_type": "generic_fixed",
            "page_number": i + 1,
            "section": "第X章",
            "user_id": "public",
            "content": f"内容{i}",
        }
        for i in range(3)
    ]
    assert repo.upsert_chunks(chunks) == 3
    user_ids = fake.upserted[6]
    assert user_ids == ["public", "public", "public"]


class _FakeEntity:
    def __init__(self, **fields):
        self._fields = fields

    def get(self, key, default=None):
        return self._fields.get(key, default)


class _FakeHit:
    def __init__(self, hit_id, distance, entity):
        self.id = hit_id
        self.distance = distance
        self.entity = entity


def test_search_filters_public_and_user_partitions(settings):
    fake = _FakeCollection()
    fake.search_result = [
        _FakeHit(
            "c1",
            0.2,
            _FakeEntity(
                dataset_id="ds1",
                source_doc_name="手册.pdf",
                chunk_type="generic_fixed",
                page_number=3,
                section="第X章",
                user_id="u123",
            ),
        )
    ]
    repo = _build_repo(settings, fake)

    results = repo.search("转专业", top_k=5, user_ids=["public", "u123"])
    assert len(results) == 1
    assert fake.search_expr == 'user_id in ["public", "u123"]'
    assert results[0]["user_id"] == "u123"


def test_search_defaults_to_public_only(settings):
    fake = _FakeCollection()
    repo = _build_repo(settings, fake)
    repo.search("奖学金")
    assert fake.search_expr == 'user_id in ["public"]'


def test_delete_by_dataset(settings):
    fake = _FakeCollection()
    repo = _build_repo(settings, fake)
    repo.delete_by_dataset("handbook_2025_abc")
    assert fake.deleted == 'dataset_id == "handbook_2025_abc"'
