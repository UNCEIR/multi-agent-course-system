# -*- coding: utf-8 -*-
"""网页搜索 tool — MCP 主路（search/* namespace）+ tavily SDK 直连兜底。

MCP 熔断/不可达 → tavily 直连（非主路）→ 双失败 → 结构化 error。
"""

from __future__ import annotations

import json
import logging

from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class WebSearchInput(BaseModel):
    """web_search 工具输入参数。"""
    query: str = Field(..., description="搜索关键词", min_length=1, max_length=500)
    max_results: int = Field(default=5, description="返回结果数量", ge=1, le=20)


def _tavily_fallback(query: str, max_results: int) -> dict:
    """tavily SDK 直连兜底（非主路）。"""
    from config import get_settings

    api_key = get_settings().tavily_api_key
    if not api_key:
        return {"isError": True, "code": "TAVILY_NO_KEY", "message": "tavily api key 未配置"}
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=api_key)
        resp = client.search(query=query, max_results=max_results)
        results = [
            {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")[:300]}
            for r in resp.get("results", [])[:max_results]
        ]
        return {"query": query, "results": results, "source": "tavily-direct"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("tavily fallback failed: %s", exc)
        return {"isError": True, "code": "SEARCH_FAILED", "message": str(exc)[:200]}


@tool(args_schema=WebSearchInput)
async def web_search(query: str, max_results: int = 5) -> str:
    """搜索互联网获取实时信息（MCP 主路，熔断自动降级直连）。"""
    from tools.mcp_client import get_mcp_client

    client = get_mcp_client()
    tool_name = await _resolve_tavily_tool(client)
    result = await client.call_tool("tavily", tool_name, {"query": query, "max_results": max_results})
    if isinstance(result, dict) and result.get("isError"):
        logger.info("web_search MCP failed (%s), fallback direct", result.get("code"))
        result = _tavily_fallback(query, max_results)
    return json.dumps(_normalize_result(result), ensure_ascii=False)[:6000]


def _normalize_result(result) -> dict:
    """规范化 MCP 返回：兼容 dict 直返 与 MCP content 数组两种形态。

    tavily MCP 返回 `[{"type": "text", "text": "{json}"}]`，内层含
    query/results[{url,title,content}]；统一输出 {query, results}。
    """
    if isinstance(result, dict):
        payload = result
        if result.get("isError"):
            return result
    elif isinstance(result, str):
        # 测试替身/简化服务器直接返回文本
        return {"query": "", "results": [{"title": "", "url": "", "content": result}], "source": "tavily-mcp"}
    elif isinstance(result, list):
        payload = {}
        for item in result:
            text = (item or {}).get("text", "") if isinstance(item, dict) else ""
            if isinstance(text, str) and text.strip().startswith("{"):
                try:
                    payload = json.loads(text)
                    break
                except json.JSONDecodeError:
                    continue
    else:
        payload = {}
    raw_results = payload.get("results", [])
    if not isinstance(raw_results, list):
        raw_results = []
    results = [
        {
            "title": str(r.get("title", ""))[:120] if isinstance(r, dict) else "",
            "url": str(r.get("url", "")) if isinstance(r, dict) else "",
            "content": str(r.get("content", ""))[:300] if isinstance(r, dict) else "",
        }
        for r in raw_results[:10]
    ]
    return {
        "query": payload.get("query", ""),
        "results": results,
        "source": payload.get("source", "tavily-mcp"),  # 直连兜底保留 tavily-direct 标记
    }


# 真实 tavily MCP 暴露的工具名（tavily_search/extract/crawl/map），假服务器用 search；
# 连接后按实际暴露名对齐，缓存避免每次探测。
_TRAVILY_TOOL_CANDIDATES = ("tavily_search", "search", "web_search", "tavily-search")
_tavily_tool_name: str | None = None


async def _resolve_tavily_tool(client) -> str:
    global _tavily_tool_name
    if _tavily_tool_name:
        return _tavily_tool_name
    try:
        listed = await client.list_tools("tavily")
        names = {t.get("name", "").split("/")[-1] for t in listed}
        for cand in _TRAVILY_TOOL_CANDIDATES:
            if cand in names:
                _tavily_tool_name = cand
                return cand
    except Exception:  # noqa: BLE001
        pass
    _tavily_tool_name = "tavily_search"  # 兜底默认
    return _tavily_tool_name
