from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from models.schemas import (
    InventoryResult,
    MarketingCopyResult,
    Product,
    ProductRecallResult,
    ProductRerankResult,
    RecommendationRequest,
    UserProfile,
    UserProfileResult,
    UserSegment,
)
from orchestrator.supervisor import SupervisorOrchestrator


@pytest.mark.agent
@pytest.mark.asyncio
async def test_supervisor_does_not_refill_out_of_stock_items():
    orchestrator = SupervisorOrchestrator()
    req = RecommendationRequest(user_id="U10001", num_items=2, query="手机")

    profile_result = UserProfileResult(
        success=True,
        profile=UserProfile(
            user_id="U10001",
            preferred_categories=["手机"],
            segments=[UserSegment.ACTIVE],
        ),
    )

    p1 = Product(product_id="P001", name="iPhone 16 Pro", category="手机", price=7999, stock=0)
    p2 = Product(product_id="P002", name="Mate 70", category="手机", price=5999, stock=10)
    recall_result = ProductRecallResult(success=True, products=[p1, p2], recall_strategies=["mysql_hot"])
    rerank_result = ProductRerankResult(success=True, products=[p1, p2], rerank_strategy="llm_rerank")
    inventory_result = InventoryResult(
        success=True,
        available_products=["P002"],
        filtered_products=[{"product_id": "P001", "reason": "out_of_stock"}],
        data={"total_checked": 2, "available_count": 1, "filtered_count": 1},
    )
    copy_result = MarketingCopyResult(success=True, copies=[{"product_id": "P002", "copy": "推荐文案"}])

    orchestrator.user_profile_agent.run = AsyncMock(return_value=profile_result)
    orchestrator.product_recall_agent.run = AsyncMock(return_value=recall_result)
    orchestrator.product_rerank_agent.run = AsyncMock(return_value=rerank_result)
    orchestrator.inventory_agent.run = AsyncMock(return_value=inventory_result)
    orchestrator.marketing_copy_agent.run = AsyncMock(return_value=copy_result)

    response = await orchestrator.recommend(req)

    assert [product.product_id for product in response.products] == ["P002"]
    assert "product_recall" in response.agent_results
    assert "product_rerank" in response.agent_results
    assert response.agent_results["inventory"].data["filtered_count"] == 1
