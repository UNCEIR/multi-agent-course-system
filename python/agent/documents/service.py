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
import structlog

from tools.documents import chunk_document, parse_document


logger = structlog.get_logger()


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
        structured: dict = {"user_id": user_id}
        if user_id and user_id != "public" and student_name:
            from tools.documents.desensitizer import desensitize_transcript, extract_transcript_courses

            desensitized = desensitize_transcript(text, student_name=student_name)
            chunks = chunk_document.invoke(
                {"text": desensitized, "strategy": strategy}
            )
            # Phase 2（evaluation 数据基准）：成绩单结构化课程提取 → metadata_json
            courses = extract_transcript_courses(text)
            if courses:
                structured["courses"] = courses

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
                user_id=user_id,  # 2026-08-29 修复：之前漏传 → 默认值 "public"，个人成绩单误写到 public 分区
            )
            meta_chunks = [
                {
                    "chunk_id": f"{dataset_id}:{idx}",
                    "chunk_index": idx,
                    "chunk_type": chunk["strategy"],
                    "content": chunk["text"],
                    "page_number": 0,
                    "metadata": structured,
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

    async def ingest_many(
        self,
        files: list[UploadFile],
        dataset_name: str,
        chunk_strategy: str = "auto",
        user_id: str = "public",
        student_name: str | None = None,
        max_file_bytes: int = 10 * 1024 * 1024,
    ) -> list[dict[str, Any]]:
        """批量摄入（1~5 份）；每文件一份独立 dataset。

        - 任一文件抛错 → 该文件返回 {status: "error", filename, error}；其余继续。
        - 文件大小超 max_file_bytes → 跳过该文件，返回 {status: "error", error: "file_too_large", file_size}。
        - 文件名重复 → 自动加 -1/-2 后缀避免 dataset_dir 冲突。
        - 空列表 / dataset_name 空 → 抛 ValueError（前端应在调用前拦截）。
        """
        if not dataset_name.strip():
            raise ValueError("dataset_name 不能为空")
        if not files:
            return []

        results: list[dict[str, Any]] = []
        # 同名文件计数：用于自动 -1/-2 后缀
        seen_counts: dict[str, int] = {}
        for file in files:
            original_name = Path(file.filename or "document").name
            if not original_name:
                original_name = "document"
            # 文件大小校验（必须在落盘 / 解析前判断，避免传大文件把磁盘打爆）
            try:
                # 1.0.x 版本 fastapi starlette 的 UploadFile.size 不一定存在；
                # 通过 spool 临时文件 stat 兜底
                spool = getattr(file, "file", None)
                if spool is not None and hasattr(spool, "tell") and hasattr(spool, "seek"):
                    spool.seek(0, 2)  # SEEK_END
                    file_size = spool.tell()
                    spool.seek(0)
                else:
                    file_size = 0
            except Exception:  # noqa: BLE001
                file_size = 0

            if file_size > max_file_bytes:
                results.append(
                    {
                        "dataset_id": None,
                        "filename": original_name,
                        "file_size": file_size,
                        "chunks_count": 0,
                        "status": "error",
                        "error": "file_too_large",
                        "max_file_bytes": max_file_bytes,
                    }
                )
                continue

            # 文件名去重
            stem = Path(original_name).stem
            suffix = Path(original_name).suffix
            count = seen_counts.get(stem + suffix, 0)
            seen_counts[stem + suffix] = count + 1
            filename = original_name if count == 0 else f"{stem}-{count}{suffix}"

            try:
                result = await self.ingest(
                    file,
                    dataset_name=dataset_name,
                    chunk_strategy=chunk_strategy,
                    user_id=user_id,
                    student_name=student_name,
                )
                # 给每条结果补 filename 方便前端展示
                result["filename"] = filename
                results.append(result)
            except Exception as exc:  # noqa: BLE001
                # 坏文件不让整批回滚；记录后继续
                logger.warning(
                    "document.ingest_failed filename=%s error=%s",
                    filename,
                    exc,
                )
                results.append(
                    {
                        "dataset_id": None,
                        "filename": filename,
                        "file_size": file_size,
                        "chunks_count": 0,
                        "status": "error",
                        "error": type(exc).__name__,
                        "message": str(exc),
                    }
                )
        return results
