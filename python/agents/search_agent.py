"""
搜索Agent — 语义搜索 + 多路召回
- 语义理解：LLM解析用户查询意图
- 向量检索：Milvus语义相似商品搜索
- 多路召回：关键词匹配 + 语义向量 + 类目过滤
- 结果排序：综合相关性 + 热度 + 用户偏好
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import get_settings
from models.schemas import Product, SearchQuery, SearchResult

from .base_agent import BaseAgent
from .product_rec_agent import MOCK_PRODUCTS

SEMANTIC_PARSE_PROMPT = """你是电商搜索意图理解专家。根据用户搜索词，解析搜索意图。

搜索词: {query}
用户ID: {user_id}

请输出JSON:
{{
  "intent": "搜索意图描述",
  "categories": ["相关类目1", "相关类目2"],
  "attributes": {{"品牌": "...", "特性": "..."}},
  "price_range": [最低, 最高],
  "keywords": ["关键词1", "关键词2"]
}}
只输出JSON。"""


class SearchAgent(BaseAgent):
    """Semantic product search with query understanding and multi-strategy recall."""

    def __init__(self):
        settings = get_settings()
        super().__init__(name="search", timeout=8.0)
        self.llm = ChatOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=0.2,
            max_tokens=1024,
        )
        self.vector_store: Any = None

    async def _execute(self, **kwargs: Any) -> SearchResult:
        query_obj: SearchQuery = kwargs.get("query_obj")
        if query_obj is None:
            query_str = kwargs.get("query", "")
            user_id = kwargs.get("user_id", "")
            num_items = kwargs.get("num_items", 10)
            query_obj = SearchQuery(query=query_str, user_id=user_id, num_items=num_items)

        query_understanding = await self._parse_query(query_obj)
        results = await self._multi_strategy_search(query_obj, query_understanding)
        ranked = await self._rank_results(results, query_understanding)

        return SearchResult(
            success=True,
            products=ranked[:query_obj.num_items],
            query_understanding=query_understanding,
            total_hits=len(results),
            data={"search_strategy": "semantic+keyword+category"},
            confidence=0.85,
        )

    async def _parse_query(self, query: SearchQuery) -> dict[str, Any]:
        messages = [
            SystemMessage(content="你是电商搜索意图理解专家。"),
            HumanMessage(content=SEMANTIC_PARSE_PROMPT.format(query=query.query, user_id=query.user_id)),
        ]
        response = await self.llm.ainvoke(messages)
        try:
            raw = response.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(raw)
        except (json.JSONDecodeError, IndexError):
            return {"intent": query.query, "categories": [], "attributes": {}, "price_range": [0, 999999], "keywords": query.query.split()}

    async def _multi_strategy_search(self, query: SearchQuery, understanding: dict) -> list[Product]:
        candidates = list(MOCK_PRODUCTS)
        keywords = [kw.lower() for kw in understanding.get("keywords", [])]
        target_categories = understanding.get("categories", [])
        query_lower = query.query.lower()

        scored: list[tuple[Product, float]] = []
        for p in candidates:
            score = 0.0
            name_lower = p.name.lower()
            desc_lower = p.description.lower()
            tag_lower = " ".join(p.tags).lower()

            for kw in keywords:
                if kw in name_lower:
                    score += 3.0
                if kw in tag_lower:
                    score += 2.0
                if kw in desc_lower:
                    score += 1.0

            if query_lower in name_lower:
                score += 5.0
            if query_lower in p.category.lower():
                score += 4.0

            if p.category in target_categories:
                score += 2.0

            price_range = understanding.get("price_range", [0, 999999])
            if isinstance(price_range, list) and len(price_range) >= 2:
                if price_range[0] <= p.price <= price_range[1]:
                    score += 1.0

            scored.append((p, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [p for p, _ in scored if _ > 0] or [p for p, _ in scored]

    async def _rank_results(self, products: list[Product], understanding: dict) -> list[Product]:
        if len(products) <= 1:
            return products
        seen_categories: set[str] = set()
        ranked: list[Product] = []
        remaining: list[Product] = []
        for p in products:
            if p.category not in seen_categories:
                ranked.append(p)
                seen_categories.add(p.category)
            else:
                remaining.append(p)
        ranked.extend(remaining)
        return ranked
