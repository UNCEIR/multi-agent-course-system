from __future__ import annotations

import random
from typing import Any

from models.schemas import IntentType, Product, ProductRecallResult, UserProfile, UserSegment

from .base_agent import BaseAgent

MOCK_PRODUCTS = [
    Product(product_id="P001", name="iPhone 16 Pro", category="手机", price=7999.0, brand="Apple", seller_id="S01", stock=500, tags=["旗舰", "新品", "5G"], rating=4.8, review_count=3200, sales_count_30d=15000, cost_price=5500.0),
    Product(product_id="P002", name="华为 Mate 70", category="手机", price=5999.0, brand="华为", seller_id="S02", stock=300, tags=["旗舰", "国产", "鸿蒙"], rating=4.7, review_count=2800, sales_count_30d=12000, cost_price=4000.0),
    Product(product_id="P003", name="AirPods Pro 3", category="耳机", price=1899.0, brand="Apple", seller_id="S01", stock=1000, tags=["降噪", "无线", "H2芯片"], rating=4.9, review_count=5600, sales_count_30d=25000, cost_price=1100.0),
    Product(product_id="P004", name="Sony WH-1000XM6", category="耳机", price=2499.0, brand="Sony", seller_id="S03", stock=200, tags=["头戴", "降噪", "Hi-Res"], rating=4.8, review_count=1800, sales_count_30d=8000, cost_price=1600.0),
    Product(product_id="P005", name="iPad Air M3", category="平板", price=4799.0, brand="Apple", seller_id="S01", stock=400, tags=["学习", "办公", "M3芯片"], rating=4.7, review_count=2100, sales_count_30d=9000, cost_price=3200.0),
    Product(product_id="P006", name="小米平板7 Pro", category="平板", price=2499.0, brand="小米", seller_id="S04", stock=600, tags=["性价比", "娱乐", "120Hz"], rating=4.5, review_count=1200, sales_count_30d=6000, cost_price=1700.0),
    Product(product_id="P007", name="Anker 140W充电器", category="配件", price=399.0, brand="Anker", seller_id="S05", stock=2000, tags=["快充", "便携", "GaN"], rating=4.6, review_count=4300, sales_count_30d=30000, cost_price=200.0),
    Product(product_id="P008", name="联想拯救者Y9000P", category="笔记本", price=8999.0, brand="联想", seller_id="S06", stock=150, tags=["游戏", "RTX4060", "高刷"], rating=4.7, review_count=900, sales_count_30d=3500, cost_price=6500.0),
    Product(product_id="P009", name="戴尔U2724D显示器", category="显示器", price=3299.0, brand="Dell", seller_id="S07", stock=80, tags=["4K", "IPS", "Type-C"], rating=4.6, review_count=600, sales_count_30d=2000, cost_price=2200.0),
    Product(product_id="P010", name="罗技MX Master 3S", category="配件", price=749.0, brand="罗技", seller_id="S08", stock=500, tags=["无线", "办公", "人体工学"], rating=4.8, review_count=3800, sales_count_30d=18000, cost_price=450.0),
    Product(product_id="P011", name="三星980 Pro 2TB", category="存储", price=1199.0, brand="三星", seller_id="S09", stock=300, tags=["SSD", "高速", "PCIe4.0"], rating=4.9, review_count=2100, sales_count_30d=10000, cost_price=800.0),
    Product(product_id="P012", name="绿联氮化镓65W", category="配件", price=129.0, brand="绿联", seller_id="S10", stock=5000, tags=["快充", "性价比", "多口"], rating=4.4, review_count=5800, sales_count_30d=45000, cost_price=60.0),
    Product(product_id="P013", name="Apple Watch Ultra 3", category="穿戴", price=5999.0, brand="Apple", seller_id="S01", stock=200, tags=["运动", "健康", "钛金属"], rating=4.8, review_count=1500, sales_count_30d=7000, cost_price=4000.0),
    Product(product_id="P014", name="大疆Mini 4 Pro", category="无人机", price=4788.0, brand="大疆", seller_id="S11", stock=100, tags=["航拍", "便携", "4K"], rating=4.9, review_count=800, sales_count_30d=3000, cost_price=3200.0),
    Product(product_id="P015", name="Switch 2", category="游戏机", price=2499.0, brand="Nintendo", seller_id="S12", stock=50, tags=["新品", "游戏", "多人"], rating=4.6, review_count=400, sales_count_30d=5000, cost_price=1800.0),
    Product(product_id="P016", name="MacBook Pro 14 M4", category="笔记本", price=12999.0, brand="Apple", seller_id="S01", stock=120, tags=["办公", "M4芯片", "Retina"], rating=4.9, review_count=1100, sales_count_30d=5000, cost_price=9500.0),
    Product(product_id="P017", name="华为FreeBuds Pro 4", category="耳机", price=1199.0, brand="华为", seller_id="S02", stock=800, tags=["降噪", "无线", "星闪"], rating=4.5, review_count=1600, sales_count_30d=8000, cost_price=700.0),
    Product(product_id="P018", name="小米14 Ultra", category="手机", price=5999.0, brand="小米", seller_id="S04", stock=400, tags=["徕卡", "旗舰", "快充"], rating=4.6, review_count=1800, sales_count_30d=9000, cost_price=4000.0),
    Product(product_id="P019", name="Kindle Scribe 2026", category="电子书", price=2799.0, brand="Amazon", seller_id="S13", stock=250, tags=["阅读", "手写", "护眼"], rating=4.4, review_count=500, sales_count_30d=3000, cost_price=1900.0),
    Product(product_id="P020", name="极米H6投影仪", category="投影仪", price=5999.0, brand="极米", seller_id="S14", stock=90, tags=["4K", "家庭影院", "便携"], rating=4.5, review_count=350, sales_count_30d=1500, cost_price=4200.0),
    Product(product_id="P021", name="华为手环9", category="穿戴", price=269.0, brand="华为", seller_id="S02", stock=3000, tags=["运动", "健康", "长续航"], rating=4.3, review_count=4200, sales_count_30d=20000, cost_price=150.0),
    Product(product_id="P022", name="小米充电宝20000", category="配件", price=149.0, brand="小米", seller_id="S04", stock=4000, tags=["大容量", "快充", "便携"], rating=4.5, review_count=6800, sales_count_30d=50000, cost_price=80.0),
    Product(product_id="P023", name="AirTag 4只装", category="配件", price=599.0, brand="Apple", seller_id="S01", stock=1500, tags=["定位", "防丢", "UWB"], rating=4.7, review_count=3200, sales_count_30d=15000, cost_price=350.0),
    Product(product_id="P024", name="索尼A7M5", category="相机", price=18999.0, brand="Sony", seller_id="S03", stock=30, tags=["全画幅", "微单", "8K"], rating=4.9, review_count=200, sales_count_30d=800, cost_price=14000.0),
    Product(product_id="P025", name="罗技G Pro X 2", category="配件", price=1499.0, brand="罗技", seller_id="S08", stock=300, tags=["游戏", "无线", "Lightspeed"], rating=4.7, review_count=700, sales_count_30d=4000, cost_price=900.0),
]


class ProductRecallAgent(BaseAgent):
    def __init__(self):
        from config import get_settings
        settings = get_settings()
        super().__init__(
            name="product_recall",
            timeout=settings.agent_timeout_product_recall,
        )

    async def _execute(self, **kwargs: Any) -> ProductRecallResult:
        user_profile: UserProfile | None = kwargs.get("user_profile")
        intent: str = kwargs.get("intent", "browse")
        num_items: int = kwargs.get("num_items", 10)
        context: dict = kwargs.get("context", {})

        strategies = ["collaborative_filter", "popularity_based"]
        candidates = list(MOCK_PRODUCTS)

        cf_results = self._collaborative_filter(user_profile, candidates)
        hot_results = self._popularity_recall(candidates)
        new_results = self._new_product_recall(candidates)

        if intent in ("search", "purchase"):
            query = context.get("query", "")
            if query:
                semantic_results = self._keyword_match(query, candidates)
                strategies.append("keyword_match")
                candidates = self._merge_dedup([cf_results, hot_results, new_results, semantic_results])
            else:
                candidates = self._merge_dedup([cf_results, hot_results, new_results])
        else:
            candidates = self._merge_dedup([cf_results, hot_results, new_results])

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

    def _new_product_recall(self, products: list[Product]) -> list[Product]:
        new_items = [p for p in products if "新品" in p.tags or p.review_count < 500]
        random.shuffle(new_items)
        return new_items

    def _keyword_match(self, query: str, products: list[Product]) -> list[Product]:
        query_lower = query.lower()
        scored = []
        for p in products:
            score = 0.0
            if query_lower in p.name.lower():
                score += 10.0
            if query_lower in p.category.lower():
                score += 8.0
            if query_lower in p.brand.lower():
                score += 6.0
            for tag in p.tags:
                if query_lower in tag.lower():
                    score += 3.0
            scored.append((score + random.uniform(0, 0.5), p))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored]

    def _merge_dedup(self, result_sets: list[list[Product]]) -> list[Product]:
        seen: set[str] = set()
        merged = []
        max_len = max(len(r) for r in result_sets)
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
