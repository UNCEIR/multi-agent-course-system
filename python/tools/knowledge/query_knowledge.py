# -*- coding: utf-8 -*-
"""知识检索工具 — query_knowledge。

主 agent 回答学校制度/个人学业问题时调用。检索 Milvus document_chunks，
自动合并公开分区（public）+ 当前用户分区（user_id），返回带来源的片段。

user_id 由系统统一注入（agent.main.context），不依赖 LLM 从对话猜测。
"""

from __future__ import annotations

import asyncio
import json

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from agent.main.context import get_current_user_id
from storage.milvus.document_vector_repo import PUBLIC_USER, DocumentVectorRepository


class QueryKnowledgeInput(BaseModel):
    """query_knowledge 工具输入参数。"""
    query: str = Field(..., description="查询问题，如：转专业流程、奖学金条件、我修过哪些课", min_length=1, max_length=500)
    top_k: int = Field(default=5, description="返回相关片段数量", ge=1, le=10)


@tool(args_schema=QueryKnowledgeInput)
async def query_knowledge(query: str, top_k: int = 5) -> str:
    """检索学校知识库（学生手册/个人成绩单）。

    公开问题检索学生手册；个人问题（学业/成绩）检索当前登录用户私有分区
    （user_id 由系统自动注入）。
    返回片段带来源（source_doc_name / page_number），回答时必须引用来源，无源不编造。
    """
    from agent import runtime

    user_id = get_current_user_id()
    repo: DocumentVectorRepository | None = runtime.document_vector_repo
    if repo is None:
        return json.dumps(
            {"error": "知识库未初始化（document_vector_repo 不可用）"},
            ensure_ascii=False,
        )

    allowed = [PUBLIC_USER]
    if user_id and user_id != PUBLIC_USER:
        allowed.append(user_id)

    # 复用已有 embedding 客户端：先试 repo.embedding_client，避免重复创建
    query_vector = None
    try:
        query_vector = repo.embedding_client.embed_text(query)
    except Exception as exc:
        return json.dumps(
            {"error": f"查询向量化失败：{exc}", "query": query},
            ensure_ascii=False,
        )

    try:
        hits = repo.search(
            query,
            top_k=top_k,
            user_ids=allowed,
            query_vector=query_vector,
        )
    except Exception as exc:
        return json.dumps(
            {"error": f"检索失败：{exc}"},
            ensure_ascii=False,
        )

    if not hits:
        return json.dumps({"matches": [], "message": "未检索到相关内容"}, ensure_ascii=False)

    # 取回片段正文（供 agent 组织答案）
    contents: dict[str, dict] = {}
    document_repo = getattr(runtime, "document_repo", None)
    if document_repo is not None:
        chunk_ids = [hit["chunk_id"] for hit in hits]
        contents = await asyncio.to_thread(document_repo.get_chunk_contents, chunk_ids)

    matches = []
    for idx, hit in enumerate(hits):
        chunk_id = hit["chunk_id"]
        content = contents.get(chunk_id, {}).get("content", "")
        matches.append(
            {
                "rank": idx + 1,
                "chunk_id": chunk_id,
                "source_doc_name": hit["source_doc_name"],
                "page_number": hit["page_number"],
                "section": hit["section"],
                "user_scope": "public" if hit["user_id"] == PUBLIC_USER else "personal",
                "score": round(float(1.0 - hit["distance"]), 4),
                "content": content[:800],
            }
        )
    return json.dumps(
        {"query": query, "top_k": top_k, "matches": matches, "user_id": user_id},
        ensure_ascii=False,
    )
