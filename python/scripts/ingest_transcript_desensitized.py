# -*- coding: utf-8 -*-
"""摄入个人成绩单 PDF 到用户私有分区（脱敏后）。

用法（在 python/ 下执行）：
    python scripts/ingest_transcript_desensitized.py --user-id 3123003252 --name xxx
    python scripts/ingest_transcript_desensitized.py --user-id xxx --name xxx --embedding local

要点：
- 写入 Milvus document_chunks 的 user_id={user-id} 分区，检索时强过滤，仅本人可检。
- 摄入前经脱敏器：姓名→[姓名]、学号→掩码、班级→年级、日期→年份。
- 课程名/学分/成绩精确值保留（个人分区内用于回答"某科考了多少分"）。
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.milvus.document_vector_repo import DocumentVectorRepository  # noqa: E402


def _chunk_id(dataset_id: str, index: int) -> str:
    return f"{dataset_id}:{index}"


def ingest(
    pdf_path: str,
    *,
    user_id: str,
    student_name: str | None,
    embedding_provider: str,
) -> int:
    from ai.embedding_client import build_embedding_client
    from ai.llm_task_name import LLMTaskName
    from storage.mysql.document_repo import DocumentRepository
    from tools.documents import chunk_document, parse_document
    from tools.documents.desensitizer import (
        build_pii_report,
        desensitize_transcript,
        extract_transcript_courses,
    )

    if not user_id.strip():
        raise ValueError("user_id 不能为空（成绩单必须归属某用户）")

    # 解析 + NFKC
    raw = parse_document.invoke({"file_path": pdf_path, "file_type": "pdf", "normalize": True})
    if not raw.strip():
        raise RuntimeError(f"解析结果为空：{pdf_path}")

    # PII 审计 + 脱敏
    report = build_pii_report(raw)
    print(f"PII audit (raw): {report}")
    text = desensitize_transcript(raw, student_name=student_name)

    chunks = chunk_document.invoke({"text": text, "strategy": "recursive"})

    # Phase 2（evaluation 数据基准）：结构化课程提取 → metadata_json
    # （快照工具确定性直查；提取失败仅告警，不阻塞摄入）
    courses = extract_transcript_courses(raw)
    if not courses:
        print(f"[WARNING] 成绩单结构化提取为空（格式可能不兼容）：{pdf_path}")
    structured = {"user_id": user_id, "courses": courses}

    embedding_client = build_embedding_client(task_name=LLMTaskName.DOCUMENTS_UPLOAD)
    vector_repo = DocumentVectorRepository(embedding_client)
    doc_repo = DocumentRepository()

    dataset_id = "transcript_" + hashlib.sha256(
        f"{user_id}:{Path(pdf_path).name}".encode("utf-8")
    ).hexdigest()[:8]

    vector_repo.delete_by_dataset(dataset_id)

    source_name = Path(pdf_path).name
    vector_chunks = []
    meta_chunks = []
    for idx, chunk in enumerate(chunks):
        chunk_id = _chunk_id(dataset_id, idx)
        vector_chunks.append(
            {
                "chunk_id": chunk_id,
                "dataset_id": dataset_id,
                "source_doc_name": source_name,
                "chunk_type": "generic_fixed",
                "page_number": 0,
                "section": "",
                "user_id": user_id,
                "content": chunk["text"],
            }
        )
        meta_chunks.append(
            {
                "chunk_id": chunk_id,
                "chunk_index": idx,
                "chunk_type": "generic_fixed",
                "content": chunk["text"],
                "page_number": 0,
                "metadata": structured,
            }
        )
    written = vector_repo.upsert_chunks(vector_chunks)

    # 写 MySQL 元数据（query_knowledge 取回 content + 来源；含脱敏后文本）
    doc_repo.create_dataset(
        dataset_id=dataset_id,
        dataset_name=f"transcript_{user_id}",
        source_doc_name=source_name,
        storage_path=str(Path(pdf_path).resolve()),
        file_type="pdf",
        file_size=Path(pdf_path).stat().st_size,
        chunk_strategy="recursive",
        chunks_count=len(chunks),
        status="ok",
    )
    doc_repo.replace_chunks(dataset_id, meta_chunks)

    print(
        f"ingest_transcript done: dataset_id={dataset_id} user_id={user_id} "
        f"chunks={written} provider={embedding_provider}"
    )
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest transcript into user partition")
    parser.add_argument("--pdf", default=str(
        Path(__file__).resolve().parents[2] / "本科生中文成绩单(1860658).pdf"
    ))
    parser.add_argument("--user-id", required=True, help="成绩单归属的用户 id（学号或系统 uid）")
    parser.add_argument("--name", default=None, help="学生姓名（用于脱敏替换为 [姓名]）")
    parser.add_argument("--embedding", default="openai", choices=["openai", "local"], help="embedding provider")
    args = parser.parse_args()

    if args.embedding == "local":
        import os

        os.environ.setdefault("EMBEDDING_PROVIDER", "local")

    if not Path(args.pdf).is_file():
        raise FileNotFoundError(f"PDF 不存在：{args.pdf}")
    ingest(
        args.pdf,
        user_id=args.user_id,
        student_name=args.name,
        embedding_provider=args.embedding,
    )


if __name__ == "__main__":
    main()
