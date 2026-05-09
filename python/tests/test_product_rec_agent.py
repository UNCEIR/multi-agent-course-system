"""Unit tests for ProductRecAgent — recall, rerank, filtering."""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.product_rec_agent import ProductRecAgent
from models.schemas import Product, UserProfile, UserSegment, ProductRecResult


class TestProductRecAgent:
    @pytest.mark.agent
    async def test_recall_all_candidates(self):
        """Without profile, all mock products are returned as candidates."""
        agent = ProductRecAgent()
        candidates = await agent._recall(None, limit=100)

        assert len(candidates) > 0
        assert len(candidates) <= 15  # total MOCK_PRODUCTS count

    @pytest.mark.agent
    async def test_recall_preferred_categories_first(self):
        """Products matching preferred categories are sorted first."""
        agent = ProductRecAgent()
        profile = UserProfile(
            user_id="test",
            preferred_categories=["耳机"],
            segments=[UserSegment.ACTIVE],
        )
        candidates = await agent._recall(profile, limit=10)

        assert len(candidates) >= 2
        first_categories = [p.category for p in candidates[:2]]
        assert first_categories.count("耳机") > 0

    @pytest.mark.agent
    async def test_recall_respects_limit(self):
        """Recall limit caps the number of returned candidates."""
        agent = ProductRecAgent()
        candidates = await agent._recall(None, limit=3)
        assert len(candidates) == 3

    @pytest.mark.agent
    async def test_rerank_without_profile_returns_top_n(self):
        """Without profile, rerank returns first N product IDs."""
        agent = ProductRecAgent()
        candidates = [
            Product(product_id="P001", name="A", category="手机", price=100, stock=10),
            Product(product_id="P002", name="B", category="耳机", price=200, stock=20),
            Product(product_id="P003", name="C", category="平板", price=300, stock=30),
        ]
        ranked = await agent._rerank(None, candidates, 2)

        assert len(ranked) == 2
        assert ranked == ["P001", "P002"]

    @pytest.mark.agent
    async def test_rerank_with_profile_calls_llm(self):
        """With profile, rerank calls LLM and returns parsed IDs."""
        agent = ProductRecAgent()
        profile = UserProfile(
            user_id="test",
            preferred_categories=["手机"],
            segments=[UserSegment.ACTIVE],
        )
        candidates = [
            Product(product_id="P001", name="iPhone", category="手机", price=7999, stock=500, tags=["旗舰"]),
            Product(product_id="P002", name="Mate 70", category="手机", price=5999, stock=300, tags=["旗舰"]),
        ]

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value.content = '["P001","P002"]'
        agent.llm = mock_llm

        ranked = await agent._rerank(profile, candidates, 2)

        assert ranked == ["P001", "P002"]
        mock_llm.ainvoke.assert_called_once()

    @pytest.mark.agent
    async def test_rerank_llm_bad_json_fallback(self):
        """If LLM returns invalid JSON, fall back to default ordering."""
        agent = ProductRecAgent()
        profile = UserProfile(
            user_id="test",
            preferred_categories=["手机"],
            segments=[UserSegment.ACTIVE],
        )
        candidates = [
            Product(product_id="P001", name="A", category="手机", price=100, stock=10),
            Product(product_id="P002", name="B", category="耳机", price=200, stock=20),
        ]

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value.content = "not valid json at all"
        agent.llm = mock_llm

        ranked = await agent._rerank(profile, candidates, 2)

        assert len(ranked) == 2
        assert "P001" in ranked

    @pytest.mark.agent
    async def test_execute_returns_product_rec_result(self):
        """Full execute returns ProductRecResult with products, strategy, and metadata."""
        agent = ProductRecAgent()

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value.content = '["P001","P003","P005"]'
        agent.llm = mock_llm

        profile = UserProfile(
            user_id="test",
            preferred_categories=["手机"],
            segments=[UserSegment.ACTIVE],
        )
        result = await agent._execute(user_profile=profile, num_items=3)

        assert isinstance(result, ProductRecResult)
        assert result.success is True
        assert len(result.products) == 3
        assert result.recall_strategy == "collaborative_filter+vector+hot"
        assert "candidate_count" in result.data
        assert result.confidence == 0.8

    @pytest.mark.agent
    async def test_execute_pads_with_extra_candidates(self):
        """If LLM returns fewer IDs than requested, extra candidates fill in."""
        agent = ProductRecAgent()

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value.content = '["P001"]'
        agent.llm = mock_llm

        result = await agent._execute(num_items=5)

        assert result.success is True
        assert len(result.products) == 5
