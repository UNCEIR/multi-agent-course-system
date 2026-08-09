# -*- coding: utf-8 -*-
"""本地文档分块 tool。

提供段落优先、固定字符窗口、递归（中文感知分隔符 + 标题优先）三种确定性策略。
递归策略用于知识库（学生手册/成绩单）摄入。
"""

from __future__ import annotations

import re

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class ChunkDocumentInput(BaseModel):
    """chunk_document 工具输入参数。"""
    text: str = Field(..., description="文档文本内容", min_length=1)
    chunk_size: int = Field(default=800, description="每块目标大小（字符数），范围 50-2000", ge=50, le=2000)
    chunk_overlap: int = Field(default=120, description="块间重叠大小", ge=0, le=500)
    strategy: str = Field(default="recursive", description="分块策略（paragraph、fixed、recursive）")


@tool(args_schema=ChunkDocumentInput)
def chunk_document(
    text: str,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
    strategy: str = "recursive",
) -> list[dict]:
    """将文档文本分块。

    Args:
        text: 文档文本内容
        chunk_size: 每块目标大小（字符数）
        chunk_overlap: 块间重叠大小
        strategy: 分块策略（paragraph、fixed、recursive）

    Returns:
        分块列表，每块包含 chunk_index、text、strategy、char_count
    """
    if strategy not in {"paragraph", "fixed", "recursive"}:
        raise ValueError(f"不支持的分块策略：{strategy}")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap 必须小于 chunk_size")

    if strategy == "paragraph":
        pieces = _paragraph_chunks(text, chunk_size)
    elif strategy == "recursive":
        pieces = _recursive_chunks(text, chunk_size, chunk_overlap)
    else:
        pieces = _fixed_chunks(text, chunk_size, chunk_overlap)

    return [
        {
            "chunk_index": index,
            "text": piece,
            "strategy": strategy,
            "char_count": len(piece),
        }
        for index, piece in enumerate(pieces)
        if piece
    ]


# 中文章节标题模式：只匹配真实标题行（第X章/节/条/款/部分、编号标题）
_HEADING_RE = re.compile(
    r"^\s*(第[一二三四五六七八九十百千0-9]+[章节条款部分]"
    r"|[一二三四五六七八九十]{1,3}[、．.]\S)"
)
# 目录行特征：连续点号引导符（.......  1）
_TOC_RE = re.compile(r"\.{3,}")
# 递归分隔符（中文感知）
_RECURSIVE_SEPARATORS = ["\n\n", "\n", "。", "；", "，", ""]


def _is_toc_line(line: str) -> bool:
    """目录/引导行：含 3 个以上连续点号，或整行是短页码/罗马页码。"""
    if _TOC_RE.search(line):
        return True
    return bool(re.fullmatch(r"\s*[ivxlcdmIVXLCDM0-9]{1,4}\s*", line))


def _recursive_chunks(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """标题优先 + 递归切分。

    1. 按标题行切出"章节块"（标题 + 其下内容）。
    2. 相邻小块合并到接近 chunk_size，保留标题前缀，避免碎片化。
    3. 超长块再用中文感知分隔符递归切到 chunk_size 内。
    """
    blocks = _split_by_headings(text)
    merged = _merge_small_blocks(blocks, chunk_size)
    chunks: list[str] = []
    for heading, body in merged:
        unit = f"{heading}\n{body}" if heading else body
        unit = unit.strip()
        if not unit:
            continue
        if len(unit) <= chunk_size:
            chunks.append(unit)
            continue
        pieces = _recursive_cut(unit, chunk_size, chunk_overlap)
        chunks.extend(pieces)
    return chunks


def _merge_small_blocks(
    blocks: list[tuple[str, str]], chunk_size: int
) -> list[tuple[str, str]]:
    """把相邻的小块（同标题或紧随其后的正文）合并到接近 chunk_size。

    只合并 body 很短且没有独立标题语义的块；超长块单独保留。
    """
    merged: list[tuple[str, str]] = []
    pending_heading = ""
    pending_body: list[str] = []
    pending_size = 0

    def _flush() -> None:
        nonlocal pending_heading, pending_body, pending_size
        if pending_body:
            merged.append((pending_heading, "\n".join(pending_body)))
        pending_heading = ""
        pending_body = []
        pending_size = 0

    for heading, body in blocks:
        body = (body or "").strip()
        if not heading:
            # 无标题正文块：并入当前 pending（若可）或开新块
            if pending_size and pending_size + len(body) <= chunk_size:
                pending_body.append(body)
                pending_size += len(body)
            else:
                _flush()
                pending_heading = ""
                pending_body = [body]
                pending_size = len(body)
            continue
        if not body:
            # 纯标题：作为下一块的前缀（替换 pending 标题）
            pending_heading = heading
            continue
        if len(body) > chunk_size:
            # 超长独立块，直接 flush 前一个
            _flush()
            merged.append((heading, body))
            continue
        if pending_size and pending_size + len(body) <= chunk_size:
            pending_body.append(body)
            pending_size += len(body)
        else:
            _flush()
            pending_heading = heading
            pending_body = [body]
            pending_size = len(body)
    _flush()
    return merged


def _split_by_headings(text: str) -> list[tuple[str, str]]:
    lines = [line.strip() for line in text.splitlines()]
    blocks: list[tuple[str, str]] = []
    current_heading = ""
    current_lines: list[str] = []
    for line in lines:
        if not line:
            continue
        # 跳过目录行（点号引导 / 纯页码），并入正文处理
        if _is_toc_line(line):
            current_lines.append(line)
            continue
        match = _HEADING_RE.match(line)
        if match and len(match.group(0)) < len(line):
            # 标题 + 同行正文（如 第一条 学生应当...）
            if current_lines:
                blocks.append((current_heading, "\n".join(current_lines)))
            current_heading = match.group(0)
            current_lines = [line[match.end():].strip()]
        elif match and len(line) <= 60:
            # 纯标题行（无正文），看下一行是否紧跟正文
            if current_lines:
                blocks.append((current_heading, "\n".join(current_lines)))
            current_heading = line
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        blocks.append((current_heading, "\n".join(current_lines)))
    return blocks


def _recursive_cut(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """用中文感知分隔符递归切分，保证块尾尽量在句子边界。"""
    best_sep = ""
    for sep in _RECURSIVE_SEPARATORS:
        if sep and sep in text:
            best_sep = sep
            break
    if not best_sep:
        return _fixed_chunks(text, chunk_size, chunk_overlap)
    parts = [part.strip() for part in text.split(best_sep) if part.strip()]
    if len(parts) <= 1:
        return _fixed_chunks(text, chunk_size, chunk_overlap)
    groups: list[str] = []
    current = ""
    for part in parts:
        candidate = f"{current}{best_sep}{part}".strip() if current else part
        if current and len(candidate) > chunk_size:
            groups.append(current)
            current = part
        else:
            current = candidate
    if current:
        groups.append(current)
    # 超长组再递归
    result: list[str] = []
    for group in groups:
        if len(group) > chunk_size * 1.5:
            result.extend(_recursive_cut(group, chunk_size, chunk_overlap))
        else:
            result.append(group)
    # 相邻块补 overlap（仅当不足时，避免信息跨边界丢失）
    final: list[str] = []
    for i, group in enumerate(result):
        if i == 0:
            final.append(group)
        else:
            tail = result[i - 1][-chunk_overlap:] if chunk_overlap else ""
            merged = f"{tail}\n{group}".strip() if tail else group
            final.append(merged)
    return final


def _paragraph_chunks(text: str, chunk_size: int) -> list[str]:
    paragraphs = [part.strip() for part in text.splitlines() if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_fixed_chunks(paragraph, chunk_size, 0))
            continue
        candidate = f"{current}\n{paragraph}".strip() if current else paragraph
        if current and len(candidate) > chunk_size:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _fixed_chunks(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    step = chunk_size - chunk_overlap
    return [text[start : start + chunk_size] for start in range(0, len(text), step)]
