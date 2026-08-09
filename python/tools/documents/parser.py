# -*- coding: utf-8 -*-
"""本地文档解析 tool。

Phase 1 只负责可验证的 Python 解析能力，不依赖 FastGPT。
PDF 主解析 pypdf，失败/表格版式复杂时用 pymupdf 兜底；支持 NFKC 归一化。
"""

from __future__ import annotations

import csv
import unicodedata
from pathlib import Path

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class ParseDocumentInput(BaseModel):
    """parse_document 工具输入参数。"""
    file_path: str = Field(..., description="文件路径", min_length=1, max_length=1024)
    file_type: str = Field(default="auto", description="文件类型（auto、pdf、docx、csv），auto 自动检测")
    normalize: bool = Field(default=True, description="是否 NFKC 归一化抽取文本（PDF 变体字修正）")


@tool(args_schema=ParseDocumentInput)
def parse_document(file_path: str, file_type: str = "auto", normalize: bool = True) -> str:
    """解析文档文件内容。

    Args:
        file_path: 文件路径
        file_type: 文件类型（auto、pdf、docx、csv），auto 自动检测
        normalize: 是否 NFKC 归一化（修复 PDF 抽取的 Kangxi 变体字）

    Returns:
        提取的文本内容
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"文档不存在：{file_path}")

    resolved_type = file_type.lower().strip()
    if resolved_type == "auto":
        resolved_type = path.suffix.lower().lstrip(".")
    if resolved_type in {"doc", "docx"}:
        return _parse_docx(path)
    if resolved_type == "pdf":
        return _parse_pdf(path, normalize=normalize)
    if resolved_type == "csv":
        return _parse_csv(path)
    if resolved_type in {"txt", "md"}:
        text = path.read_text(encoding="utf-8")
        return _normalize(text, normalize)
    raise ValueError(f"不支持的文档类型：{resolved_type}")


def _normalize(text: str, enabled: bool) -> str:
    return unicodedata.normalize("NFKC", text) if enabled else text


def _parse_csv(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.reader(handle)
        return "\n".join(" | ".join(cell.strip() for cell in row) for row in rows)


def _parse_pdf(path: Path, normalize: bool = True) -> str:
    text = _parse_pdf_pypdf(path)
    if not text.strip():
        text = _parse_pdf_pymupdf(path)
    return _normalize(text, normalize)


def _parse_pdf_pypdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()


def _parse_pdf_pymupdf(path: Path) -> str:
    """pymupdf 兜底：表格与复杂版式抽取更好。"""
    import fitz  # pymupdf

    pages: list[str] = []
    with fitz.open(str(path)) as doc:
        for page in doc:
            text = page.get_text("text") or ""
            tables = ""
            for table in page.find_tables():
                if table.extract():
                    rows = [" | ".join(cell or "" for cell in row) for row in table.extract()]
                    tables += "\n" + "\n".join(rows)
            pages.append((text + "\n" + tables).strip())
    return "\n".join(pages).strip()


def _parse_docx(path: Path) -> str:
    from docx import Document

    document = Document(str(path))
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs]
    return "\n".join(text for text in paragraphs if text)
