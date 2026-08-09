# -*- coding: utf-8 -*-
"""摄入学生手册 PDF 到知识库公开分区。

用法（在 python/ 下执行）：
    python scripts/ingest_student_handbook.py                 # 全量
    python scripts/ingest_student_handbook.py --limit 30      # 仅前 30 页验证
    python scripts/ingest_student_handbook.py --embedding local   # 本地确定性向量冒烟

输出：写入 Milvus document_chunks（user_id=public）与 MySQL document_records。
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.milvus.document_vector_repo import PUBLIC_USER, DocumentVectorRepository  # noqa: E402

# 手册正文开始标记（目录之后的第一份规章）
_TOC_END_MARKERS = ["高等学校学生行为准则", "第一章  总", "第一章 总", "总  则"]


def _strip_toc(text: str) -> str:
    """去掉手册目录（前 8 页点号引导行），从正文开始保留。

    目录里也含"高等学校学生行为准则"字样但后跟点号引导，正文里的标记后跟规章正文；
    因此跳过带连续点号（....）的命中位置。
    """
    markers = ["高等学校学生行为准则", "第一章  总", "第一章 总", "总  则"]
    start = 0
    while True:
        best = None
        for marker in markers:
            idx = text.find(marker, start)
            if idx >= 0 and (best is None or idx < best):
                best = idx
        if best is None:
            return text
        # 命中位置后 20 字符内若出现连续 3+ 点号 → 是目录行，继续往后找
        if "..." in text[best:best + 20]:
            start = best + len("高等学校学生行为准则")
            continue
        return text[best:]


def _chunk_id(dataset_id: str, index: int) -> str:
    return f"{dataset_id}:{index}"


def ingest(pdf_path: str, *, limit: int | None, embedding_provider: str, dataset_name: str) -> int:
    from ai.embedding_client import build_embedding_client
    from ai.llm_task_name import LLMTaskName
    from storage.mysql.document_repo import DocumentRepository
    from tools.documents import chunk_document, parse_document

    # 解析 + NFKC 归一化 + 去目录
    text = parse_document.invoke({"file_path": pdf_path, "file_type": "pdf", "normalize": True})
    text = _strip_toc(text)
    if not text.strip():
        raise RuntimeError(f"解析结果为空：{pdf_path}")

    # 分块（recursive，标题优先 + 中文感知分隔符）
    chunks = chunk_document.invoke({"text": text, "strategy": "recursive"})

    embedding_client = build_embedding_client(task_name=LLMTaskName.DOCUMENTS_UPLOAD)
    vector_repo = DocumentVectorRepository(embedding_client)
    doc_repo = DocumentRepository()

    dataset_id = "handbook_2025_" + hashlib.sha256(pdf_path.encode("utf-8")).hexdigest()[:8]

    # 先清理旧版本（增量更新：同 dataset 去旧）
    vector_repo.delete_by_dataset(dataset_id)

    source_name = Path(pdf_path).name
    selected = chunks[:limit] if limit else chunks
    vector_chunks = []
    meta_chunks = []
    for idx, chunk in enumerate(selected):
        chunk_id = _chunk_id(dataset_id, idx)
        vector_chunks.append(
            {
                "chunk_id": chunk_id,
                "dataset_id": dataset_id,
                "source_doc_name": source_name,
                "chunk_type": "generic_fixed",
                "page_number": 0,
                "section": "",
                "user_id": PUBLIC_USER,
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
                "metadata": {"user_id": PUBLIC_USER},
            }
        )
    written = vector_repo.upsert_chunks(vector_chunks)

    # 写 MySQL 元数据（query_knowledge 需要取回 content + 来源）
    doc_repo.create_dataset(
        dataset_id=dataset_id,
        dataset_name=dataset_name,
        source_doc_name=source_name,
        storage_path=str(Path(pdf_path).resolve()),
        file_type="pdf",
        file_size=Path(pdf_path).stat().st_size,
        chunk_strategy="recursive",
        chunks_count=len(selected),
        status="ok",
    )
    doc_repo.replace_chunks(dataset_id, meta_chunks)

    print(
        f"ingest_student_handbook done: dataset_id={dataset_id} "
        f"chunks={written} total_parsed={len(chunks)} provider={embedding_provider}"
    )
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest student handbook into knowledge base")
    parser.add_argument("--pdf", default=str(
        Path(__file__).resolve().parents[2] / "广东工业大学2025年学生手册.pdf"
    ))
    parser.add_argument("--limit", type=int, default=None, help="仅摄入前 N 个 chunk（验证用）")
    parser.add_argument("--embedding", default="openai", choices=["openai", "local"], help="embedding provider")
    parser.add_argument("--dataset-name", default="student_handbook_2025")
    args = parser.parse_args()

    # local provider 冒烟：不耗真实额度
    if args.embedding == "local":
        import os

        os.environ.setdefault("EMBEDDING_PROVIDER", "local")

    if not Path(args.pdf).is_file():
        raise FileNotFoundError(f"PDF 不存在：{args.pdf}")
    ingest(
        args.pdf,
        limit=args.limit,
        embedding_provider=args.embedding,
        dataset_name=args.dataset_name,
    )


if __name__ == "__main__":
    main()
