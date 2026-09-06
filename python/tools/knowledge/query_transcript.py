# -*- coding: utf-8 -*-
"""个人成绩单检索工具 — query_transcript。

只查 user_id=<current_user_id> 的个人分区（修过哪些课 / 某科成绩 / 绩点）。
与 query_handbook 完全分离：候选集 100% 命中本人成绩单 top_k=3，
不再混入公开手册 chunk。强权限隔离：未登录返 error，不允许他人代查。

user_id 由系统统一注入（agent.main.context），工具不依赖 LLM 猜。
"""

from __future__ import annotations

import json

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from agent.main.context import get_current_user_id
from storage.milvus.document_vector_repo import PUBLIC_USER

from ._common import _assemble_matches, _embed_search_chunks, _format_tool_result


class QueryTranscriptInput(BaseModel):
    """query_transcript 工具输入参数。"""

    query: str = Field(
        ...,
        description="查询本人学业问题，如：我修过哪些课、某科成绩、我的绩点",
        min_length=1,
        max_length=500,
    )
    top_k: int = Field(default=3, description="返回相关片段数量", ge=1, le=20)


@tool(args_schema=QueryTranscriptInput)
async def query_transcript(query: str, top_k: int = 3) -> str:
    """检索当前登录用户的个人成绩单（私有分区，仅本人可见）。

    何时用：学生问"我修过哪些课 / 某科成绩 / 绩点"等个人学业问题。
    何时不用：学校公开制度（奖学金、转专业、毕业学分要求）请用 query_handbook
    （public 分区）；本人个人数据在公开手册里查不到，公开制度也不要用本工具。

    - 未登录（user_id 为空）或 user_id=public → 返回 "需要登录" 错误，不查任何分区
    - 隔离：只查 user_ids=[user_id]，绝不查其他用户；不允许调用方传 user_id
    - 默认 top_k=3（个人查询精度优先，避免公开手册 chunk 污染）
    """
    user_id = get_current_user_id()
    if not user_id or user_id == PUBLIC_USER:
        return json.dumps(
            {
                "error": "未登录或匿名状态，无法查询个人成绩单",
                "scope": "transcript",
                "matches": [],
            },
            ensure_ascii=False,
        )

    # 强权限隔离：只查 user_id 本人分区，绝不混入其他用户或公开手册
    hits = await _embed_search_chunks(user_ids=[user_id], query=query, top_k=top_k)
    matches = await _assemble_matches(hits)
    return _format_tool_result(
        query=query,
        top_k=top_k,
        matches=matches,
        user_id=user_id,
        scope="transcript",
    )
