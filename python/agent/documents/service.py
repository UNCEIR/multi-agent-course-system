# -*- coding: utf-8 -*-
"""文档摄入编排。

串联 解析 → 脱敏（可选）→ 分块 → 向量化 → 写 Milvus/MySQL。
支持 user_id 分区：手册走 public，个人文档走 user 分区。
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from tools.documents import chunk_document, parse_document


class DocumentIngestionService:
    """协调源文件保存、解析、脱敏、分块和入库。"""

    def __init__(
        self,
        storage_dir: str | Path | None = None,
        vector_repo: Any | None = None,
        document_repo: Any | None = None,
        embedding_client: Any | None = None,
    ):
        if storage_dir is None:
            repo_root = Path(__file__).resolve().parents[3]
            storage_dir = repo_root / "python" / ".documents"
        self.storage_dir = Path(storage_dir)
        self.vector_repo = vector_repo
        self.document_repo = document_repo
        self.embedding_client = embedding_client

    def set_repos(
        self,
        vector_repo: Any,
        document_repo: Any,
        embedding_client: Any,
    ) -> None:
        self.vector_repo = vector_repo
        self.document_repo = document_repo
        self.embedding_client = embedding_client

    async def ingest(
        self,
        file: UploadFile,
        dataset_name: str,
        chunk_strategy: str = "auto",
        user_id: str = "public",
        student_name: str | None = None,
    ) -> dict[str, Any]:
        if not dataset_name.strip():
            raise ValueError("dataset_name 不能为空")
        filename = Path(file.filename or "document").name
        if not filename:
            raise ValueError("文件名不能为空")

        dataset_id = uuid.uuid4().hex
        dataset_dir = self.storage_dir / dataset_id
        dataset_dir.mkdir(parents=True, exist_ok=False)
        source_path = dataset_dir / filename
        source_path.write_bytes(await file.read())

        file_type = source_path.suffix.lower().lstrip(".") or "txt"
        text = parse_document.invoke(
            {"file_path": str(source_path), "file_type": file_type, "normalize": True}
        )
        strategy = chunk_strategy if chunk_strategy in {"recursive", "paragraph", "fixed"} else "recursive"
        chunks = chunk_document.invoke(
            {"text": text, "strategy": strategy}
        )

        # 个人文档（非 public 分区）先脱敏：姓名/学号/班级/日期
        if user_id and user_id != "public" and student_name:
            from tools.documents.desensitizer import desensitize_transcript

            desensitized = desensitize_transcript(text, student_name=student_name)
            chunks = chunk_document.invoke(
                {"text": desensitized, "strategy": strategy}
            )

        # 写 Milvus + MySQL（若仓储已注入）
        if self.vector_repo is not None and self.embedding_client is not None:
            vector_chunks = [
                {
                    "chunk_id": f"{dataset_id}:{idx}",
                    "dataset_id": dataset_id,
                    "source_doc_name": filename,
                    "chunk_type": chunk["strategy"],
                    "page_number": 0,
                    "section": "",
                    "user_id": user_id,
                    "content": chunk["text"],
                }
                for idx, chunk in enumerate(chunks)
            ]
            self.vector_repo.upsert_chunks(vector_chunks)

        if self.document_repo is not None:
            await asyncio.to_thread(
                self.document_repo.create_dataset,
                dataset_id=dataset_id,
                dataset_name=dataset_name,
                source_doc_name=filename,
                storage_path=str(source_path),
                file_type=file_type,
                file_size=source_path.stat().st_size,
                chunk_strategy=strategy,
                chunks_count=len(chunks),
                status="ok",
            )
            meta_chunks = [
                {
                    "chunk_id": f"{dataset_id}:{idx}",
                    "chunk_index": idx,
                    "chunk_type": chunk["strategy"],
                    "content": chunk["text"],
                    "page_number": 0,
                    "metadata": {"user_id": user_id},
                }
                for idx, chunk in enumerate(chunks)
            ]
            await asyncio.to_thread(self.document_repo.replace_chunks, dataset_id, meta_chunks)

        return {
            "dataset_id": dataset_id,
            "dataset_name": dataset_name,
            "source_path": str(source_path),
            "chunks": chunks,
            "chunks_count": len(chunks),
            "status": "ok",
            "user_id": user_id,
        }
