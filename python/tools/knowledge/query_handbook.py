# -*- coding: utf-8 -*-
"""学生手册检索工具 — query_handbook。

只查 user_id=public 的手册分区（学校规章 / 政策 / 流程 / 学分要求 / 毕业条件）。
与 query_transcript 完全分离：候选集 100% 命中公开手册 top_k=5，
不再混入个人成绩单 chunk。匿名/登录状态均可调用。

user_id 仍由系统统一注入（agent.main.context），这里不依赖它做权限判断。
"""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from agent.main.context import get_current_user_id
from storage.milvus.document_vector_repo import PUBLIC_USER

from ._common import _assemble_matches, _embed_search_chunks, _format_tool_result


class QueryHandbookInput(BaseModel):
    """query_handbook 工具输入参数。"""

    query: str = Field(
        ...,
        description="查询问题，如：奖学金申请条件、转专业流程、毕业学分要求",
        min_length=1,
        max_length=500,
    )
    top_k: int = Field(default=5, description="返回相关片段数量", ge=1, le=20)


@tool(args_schema=QueryHandbookInput)
async def query_handbook(query: str, top_k: int = 5) -> str:
    """检索学校公开知识库（学生手册 / 校规校纪 / 政策制度）。

    只检索 `user_id=public` 分区，不混入个人成绩单 chunk。无登录态也可调用。
    返回片段带 source_doc_name / page_number，回答时必须引用来源，检索不到不编造。
    """
    # 公开分区不受 user_id 影响；显式传 [PUBLIC_USER] 表明意图与最小权限
    hits = await _embed_search_chunks(user_ids=[PUBLIC_USER], query=query, top_k=top_k)
    matches = await _assemble_matches(hits)
    return _format_tool_result(
        query=query,
        top_k=top_k,
        matches=matches,
        user_id=get_current_user_id(),
        scope="handbook",
    )
