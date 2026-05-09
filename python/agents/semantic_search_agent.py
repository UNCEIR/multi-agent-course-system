from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import get_settings
from models.schemas import Product, ProductRecallResult, SemanticSearchResult, UserProfile

from .base_agent import BaseAgent

SYSTEM_PROMPT = """你是一个电商语义搜索专家。
理解用户的搜索查询,并进行语义扩展,找到最相关的商品。

任务:
1. 分析查询的真实语义意图
2. 从候选商品中筛选最语义相关的商品
3. 考虑同义词、上下位词、相关品类扩展

输出JSON:
{
  "query_understanding": "对查询的语义理解",
  "expanded_queries": ["扩展关键词1", "扩展关键词2"],
  "matched_product_ids": ["P001", "P003", "P005"],
  "relevance_scores": {"P001": 0.95, "P003": 0.88}
}

只输出JSON,不要其他内容。"""


class SemanticSearchAgent(BaseAgent):
    def __init__(self):
        settings = get_settings()
        super().__init__(
            name="semantic_search",
            timeout=settings.agent_timeout_semantic_search,
        )
        self.llm = ChatOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=0.2,
            max_tokens=1024,
        )
        self.vector_store: Any = None

    async def _execute(self, **kwargs: Any) -> SemanticSearchResult:
        query: str = kwargs.get("query", "")
        user_profile: UserProfile | None = kwargs.get("user_profile")
        candidates: list[Product] = kwargs.get("candidates", [])

        if not query or not candidates:
            return SemanticSearchResult(
                success=True,
                products=candidates,
                query_understanding="无搜索查询",
                data={},
                confidence=1.0,
            )

        search_data = await self._semantic_search(query, user_profile, candidates)
        matched_ids = set(search_data.get("matched_product_ids", []))

        matched_products = [p for p in candidates if p.product_id in matched_ids]
        if not matched_products:
            matched_products = candidates

        return SemanticSearchResult(
            success=True,
            products=matched_products,
            query_understanding=search_data.get("query_understanding", query),
            data={
                "expanded_queries": search_data.get("expanded_queries", []),
                "relevance_scores": search_data.get("relevance_scores", {}),
            },
            confidence=0.82,
        )

    async def _semantic_search(
        self, query: str, profile: UserProfile | None, candidates: list[Product]
    ) -> dict:
        if self.vector_store:
            pass

        candidate_summary = [
            {"id": p.product_id, "name": p.name, "category": p.category,
             "brand": p.brand, "tags": p.tags}
            for p in candidates
        ]

        profile_context = ""
        if profile and profile.preferred_categories:
            profile_context = f"\n用户偏好类目: {', '.join(profile.preferred_categories)}"

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"查询: {query}{profile_context}\n候选商品: {json.dumps(candidate_summary, ensure_ascii=False)}"),
        ]
        response = await self.llm.ainvoke(messages)
        return self._parse_json(response.content)

    def _parse_json(self, raw: str) -> dict:
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(cleaned)
        except (json.JSONDecodeError, IndexError):
            return {}
