"""Unit tests for MarketingCopyAgent — template selection, parsing, compliance."""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.marketing_copy_agent import MarketingCopyAgent, FORBIDDEN_WORDS
from models.schemas import UserProfile, UserSegment, Product


class TestMarketingCopyAgent:
    @pytest.mark.agent
    def test_select_template_new_user_first(self):
        """Template priority: NEW_USER is selected when present."""
        agent = MarketingCopyAgent()
        profile = UserProfile(
            user_id="test",
            segments=[UserSegment.ACTIVE, UserSegment.NEW_USER],
        )
        result = agent._select_template(profile)
        assert result == UserSegment.NEW_USER

    @pytest.mark.agent
    def test_select_template_high_value(self):
        """HIGH_VALUE is selected when present (higher priority than ACTIVE)."""
        agent = MarketingCopyAgent()
        profile = UserProfile(
            user_id="test",
            segments=[UserSegment.ACTIVE, UserSegment.HIGH_VALUE],
        )
        result = agent._select_template(profile)
        assert result == UserSegment.HIGH_VALUE

    @pytest.mark.agent
    def test_select_template_churn_risk(self):
        """CHURN_RISK is selected when present."""
        agent = MarketingCopyAgent()
        profile = UserProfile(
            user_id="test",
            segments=[UserSegment.CHURN_RISK],
        )
        result = agent._select_template(profile)
        assert result == UserSegment.CHURN_RISK

    @pytest.mark.agent
    def test_select_template_price_sensitive(self):
        """PRICE_SENSITIVE is selected when present."""
        agent = MarketingCopyAgent()
        profile = UserProfile(
            user_id="test",
            segments=[UserSegment.PRICE_SENSITIVE, UserSegment.ACTIVE],
        )
        result = agent._select_template(profile)
        assert result == UserSegment.PRICE_SENSITIVE

    @pytest.mark.agent
    def test_select_template_none_profile_defaults_active(self):
        """None profile defaults to ACTIVE template."""
        agent = MarketingCopyAgent()
        result = agent._select_template(None)
        assert result == UserSegment.ACTIVE

    @pytest.mark.agent
    def test_select_template_empty_segments_defaults_active(self):
        """Profile with no segments defaults to ACTIVE."""
        agent = MarketingCopyAgent()
        profile = UserProfile(user_id="test", segments=[])
        result = agent._select_template(profile)
        assert result == UserSegment.ACTIVE

    @pytest.mark.agent
    def test_parse_copies_valid_json(self):
        """Valid JSON array of copy objects is parsed correctly."""
        agent = MarketingCopyAgent()
        raw = json.dumps([
            {"product_id": "P001", "copy": "文案内容1"},
            {"product_id": "P002", "copy": "文案内容2"},
        ])
        copies = agent._parse_copies(raw)

        assert len(copies) == 2
        assert copies[0]["product_id"] == "P001"
        assert copies[1]["product_id"] == "P002"

    @pytest.mark.agent
    def test_parse_copies_codeblock_wrapped(self):
        """JSON in markdown code blocks is cleaned before parsing."""
        agent = MarketingCopyAgent()
        raw = '```\n[{"product_id": "P001", "copy": "test"}]\n```'
        copies = agent._parse_copies(raw)

        assert len(copies) == 1
        assert copies[0]["product_id"] == "P001"

    @pytest.mark.agent
    def test_parse_copies_invalid_json_returns_empty(self):
        """Invalid JSON returns empty list."""
        agent = MarketingCopyAgent()
        copies = agent._parse_copies("garbage text here")
        assert copies == []

    @pytest.mark.agent
    def test_compliance_check_replaces_forbidden_words(self):
        """Forbidden advertising words are replaced with ***."""
        agent = MarketingCopyAgent()
        item = {"product_id": "P001", "copy": "这是最好的产品，绝对第一，100%有效"}
        cleaned = agent._compliance_check(item)

        for word in ["最好", "第一", "绝对", "100%"]:
            assert word not in cleaned["copy"]
        assert "***" in cleaned["copy"]

    @pytest.mark.agent
    def test_compliance_check_no_forbidden_words(self):
        """Text without forbidden words is unchanged."""
        agent = MarketingCopyAgent()
        item = {"product_id": "P001", "copy": "这是一段正常的普通文案"}
        cleaned = agent._compliance_check(item)
        assert cleaned["copy"] == "这是一段正常的普通文案"

    @pytest.mark.agent
    async def test_execute_empty_products(self):
        """With no products, returns empty copies with confidence 1.0."""
        agent = MarketingCopyAgent()
        result = await agent._execute(user_profile=None, products=[])

        assert result.success is True
        assert result.copies == []
        assert result.confidence == 1.0

    @pytest.mark.agent
    async def test_execute_with_products_calls_llm(self):
        """Full execute calls LLM to generate copies for products."""
        agent = MarketingCopyAgent()

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value.content = json.dumps([
            {"product_id": "P001", "copy": "品质之选，限时特惠"},
        ])
        agent.llm = mock_llm

        profile = UserProfile(
            user_id="test",
            segments=[UserSegment.HIGH_VALUE],
        )
        products = [
            Product(product_id="P001", name="Test Product", category="手机", price=5999, stock=100, tags=["旗舰"]),
        ]
        result = await agent._execute(user_profile=profile, products=products)

        assert result.success is True
        assert len(result.copies) == 1
        assert result.prompt_template_used == "high_value"
        mock_llm.ainvoke.assert_called_once()

    @pytest.mark.agent
    def test_forbidden_words_list_complete(self):
        """Forbidden words list contains expected entries."""
        expected = ["最好", "第一", "国家级", "全球首", "绝对", "100%", "永久", "万能", "祖传", "纯天然"]
        assert set(FORBIDDEN_WORDS) == set(expected)
