from __future__ import annotations

import random
from typing import Any

from models.schemas import Product, ProductRecallResult, UserProfile
from repositories import MilvusRepository, MySQLRepository
from services import build_embedding_client

from .base_agent import BaseAgent


class ProductRecallAgent(BaseAgent):
    def __init__(self):
        from config import get_settings
        settings = get_settings()
        super().__init__(
            name="product_recall",
            timeout=settings.agent_timeout_product_recall,
        )
        self.mysql_repo = MySQLRepository()
        self.embedding_client = build_embedding_client()
        self.milvus_repo = MilvusRepository(self.embedding_client)

    async def _execute(self, **kwargs: Any) -> ProductRecallResult:
        user_profile: UserProfile | None = kwargs.get("user_profile")
        intent: str = kwargs.get("intent", "recommend")
        num_items: int = kwargs.get("num_items", 10)
        context: dict = kwargs.get("context", {})

        query = (context.get("query") or "").strip()
        preferred = user_profile.preferred_categories if user_profile else []
        db_candidates = self.mysql_repo.fetch_products(
            limit=max(num_items * 6, 30),
            categories=preferred,
            query_text=query if intent in ("search", "purchase") else "",
        )
        if not db_candidates:
            db_candidates = self._fallback_products()

        strategies = ["mysql_hot"]
        if db_candidates:
            _ = self.milvus_repo.upsert_products([p.model_dump() for p in db_candidates])
        semantic_ids = self.milvus_repo.search(query=query, limit=num_items * 3) if query else []
        id_to_product = {product.product_id: product for product in db_candidates}
        semantic_products = [id_to_product[pid] for pid in semantic_ids if pid in id_to_product]
        if semantic_products:
            strategies.append("milvus_semantic")

        cf_results = self._collaborative_filter(user_profile, db_candidates)
        hot_results = self._popularity_recall(db_candidates)
        candidates = self._merge_dedup([semantic_products, cf_results, hot_results])

        if user_profile:
            candidates = self._apply_diversity(candidates, user_profile)

        candidates = candidates[: num_items * 3]

        return ProductRecallResult(
            success=True,
            products=candidates,
            recall_strategies=strategies,
            data={"total_candidates": len(candidates), "strategies": strategies},
            confidence=0.85,
        )

    def _fallback_products(self) -> list[Product]:
        return [
            Product(product_id="P001", name="iPhone 16 Pro", category="手机", price=7999.0, brand="Apple", seller_id="S01", stock=500, tags=["旗舰", "新品"], rating=4.8, review_count=3200, sales_count_30d=15000, cost_price=5500.0),
            Product(product_id="P003", name="AirPods Pro 3", category="耳机", price=1899.0, brand="Apple", seller_id="S01", stock=1000, tags=["降噪", "无线"], rating=4.9, review_count=5600, sales_count_30d=25000, cost_price=1100.0),
            Product(product_id="P005", name="iPad Air M3", category="平板", price=4799.0, brand="Apple", seller_id="S01", stock=400, tags=["学习", "办公"], rating=4.7, review_count=2100, sales_count_30d=9000, cost_price=3200.0),
            Product(product_id="P010", name="罗技MX Master 3S", category="配件", price=749.0, brand="罗技", seller_id="S08", stock=500, tags=["无线", "办公"], rating=4.8, review_count=3800, sales_count_30d=18000, cost_price=450.0),
            Product(product_id="P016", name="MacBook Pro 14 M4", category="笔记本", price=12999.0, brand="Apple", seller_id="S01", stock=120, tags=["办公", "M4芯片"], rating=4.9, review_count=1100, sales_count_30d=5000, cost_price=9500.0),
        ]

    def _collaborative_filter(self, profile: UserProfile | None, products: list[Product]) -> list[Product]:
        if not profile:
            return self._popularity_recall(products)

        preferred = set(profile.preferred_categories) if profile.preferred_categories else set()
        if not preferred:
            return self._popularity_recall(products)

        scored = []
        for p in products:
            score = 0.0
            if p.category in preferred:
                score += 5.0
            if profile.price_range[0] <= p.price <= profile.price_range[1]:
                score += 2.0
            if p.rating >= 4.5:
                score += 1.0
            score += random.uniform(0, 1)
            scored.append((score, p))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored]

    def _popularity_recall(self, products: list[Product]) -> list[Product]:
        scored = [(p.sales_count_30d + random.uniform(0, 100), p) for p in products]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored]

    def _merge_dedup(self, result_sets: list[list[Product]]) -> list[Product]:
        if not result_sets:
            return []
        seen: set[str] = set()
        merged = []
        max_len = max((len(r) for r in result_sets), default=0)
        for i in range(max_len):
            for result_set in result_sets:
                if i < len(result_set):
                    p = result_set[i]
                    if p.product_id not in seen:
                        seen.add(p.product_id)
                        merged.append(p)
        return merged

    def _apply_diversity(self, products: list[Product], profile: UserProfile) -> list[Product]:
        preferred = set(profile.preferred_categories) if profile.preferred_categories else set()
        preferred_items = []
        non_preferred_items = []

        for p in products:
            if p.category in preferred:
                preferred_items.append(p)
            else:
                non_preferred_items.append(p)

        random.shuffle(non_preferred_items)
        result = []
        pi, ni = 0, 0
        while len(result) < len(products):
            if pi < len(preferred_items):
                result.append(preferred_items[pi])
                pi += 1
            if ni < len(non_preferred_items) and len(result) < len(products):
                result.append(non_preferred_items[ni])
                ni += 1
            if pi >= len(preferred_items) and ni >= len(non_preferred_items):
                break

        return result
