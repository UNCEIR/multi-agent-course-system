from __future__ import annotations

import json
import random
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import get_settings
from models.schemas import Product, ProductRerankResult, UserProfile

from .base_agent import BaseAgent

RERANK_PROMPT = """你是电商推荐排序专家。根据用户画像和候选商品,重新排序并选出最优的{num_items}个商品。

用户画像:
{user_profile}

候选商品:
{candidates}

排序原则:
1. 用户偏好类目优先
2. 价格在用户可接受范围内
3. 保证类目多样性(相邻商品尽量不同类目)
4. 高评分商品优先
5. 新品适当加权
6. 避免同一卖家连续排列

输出商品ID JSON数组,按推荐优先级排序:
["product_id_1", "product_id_2", ...]

只输出JSON数组,不要其他内容。"""


class ProductRerankAgent(BaseAgent):
    def __init__(self):
        settings = get_settings()
        super().__init__(
            name="product_rerank",
            timeout=settings.agent_timeout_product_rerank,
        )
        self.llm = ChatOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=0.3,
            max_tokens=1024,
        )

    async def _execute(self, **kwargs: Any) -> ProductRerankResult:
        user_profile: UserProfile | None = kwargs.get("user_profile")
        candidates: list[Product] = kwargs.get("candidates", [])
        num_items: int = kwargs.get("num_items", 10)
        intent: str = kwargs.get("intent", "browse")

        if not candidates:
            return ProductRerankResult(
                success=True,
                products=[],
                rerank_strategy="empty",
                confidence=1.0,
            )

        if user_profile:
            ranked_ids = await self._llm_rerank(user_profile, candidates, num_items)
            strategy = "llm_rerank"
        else:
            ranked_ids = self._rule_based_rerank(candidates, num_items)
            strategy = "rule_based"

        id_to_product = {p.product_id: p for p in candidates}
        final_products = []
        for pid in ranked_ids:
            if pid in id_to_product:
                final_products.append(id_to_product[pid])

        if len(final_products) < num_items:
            for p in candidates:
                if p.product_id not in ranked_ids:
                    final_products.append(p)
                    if len(final_products) >= num_items:
                        break

        if intent == "purchase":
            final_products.sort(key=lambda p: p.rating, reverse=True)

        final_products = self._ensure_diversity(final_products, num_items)

        return ProductRerankResult(
            success=True,
            products=final_products[:num_items],
            rerank_strategy=strategy,
            data={"candidate_count": len(candidates), "output_count": len(final_products[:num_items])},
            confidence=0.82,
        )

    async def _llm_rerank(
        self, profile: UserProfile, candidates: list[Product], num_items: int
    ) -> list[str]:
        profile_summary = {
            "segments": [s.value for s in profile.segments],
            "preferred_categories": profile.preferred_categories,
            "price_range": list(profile.price_range),
        }
        candidate_summary = [
            {
                "id": p.product_id, "name": p.name, "category": p.category,
                "price": p.price, "brand": p.brand, "seller_id": p.seller_id,
                "rating": p.rating, "tags": p.tags,
            }
            for p in candidates
        ]

        prompt = RERANK_PROMPT.format(
            num_items=num_items,
            user_profile=json.dumps(profile_summary, ensure_ascii=False),
            candidates=json.dumps(candidate_summary, ensure_ascii=False),
        )

        messages = [
            SystemMessage(content="你是电商推荐排序专家。"),
            HumanMessage(content=prompt),
        ]
        response = await self.llm.ainvoke(messages)

        try:
            raw = response.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(raw)
        except (json.JSONDecodeError, IndexError):
            return [p.product_id for p in candidates[:num_items]]

    def _rule_based_rerank(self, candidates: list[Product], num_items: int) -> list[str]:
        scored = []
        for p in candidates:
            score = p.rating * 2 + (p.sales_count_30d / 1000) + random.uniform(0, 0.5)
            scored.append((score, p.product_id))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [pid for _, pid in scored[:num_items]]

    def _ensure_diversity(self, products: list[Product], num_items: int) -> list[Product]:
        if len(products) <= num_items:
            return products

        result = []
        categories_used: dict[str, int] = {}
        sellers_used: dict[str, int] = {}

        for p in products:
            cat_count = categories_used.get(p.category, 0)
            sel_count = sellers_used.get(p.seller_id, 0)
            if cat_count < 3 and sel_count < 2:
                result.append(p)
                categories_used[p.category] = cat_count + 1
                sellers_used[p.seller_id] = sel_count + 1
            if len(result) >= num_items:
                break

        while len(result) < num_items:
            for p in products:
                if p not in result:
                    result.append(p)
                    if len(result) >= num_items:
                        break

        return result
