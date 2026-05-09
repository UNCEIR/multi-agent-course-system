"""Unit tests for InventoryAgent — stock checking, alerts, purchase limits."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.inventory_agent import (
    InventoryAgent,
    SAFETY_STOCK_THRESHOLD,
    LOW_STOCK_THRESHOLD,
    HOT_ITEM_PURCHASE_LIMIT,
)
from models.schemas import Product, InventoryResult


class TestInventoryAgent:
    @pytest.mark.agent
    async def test_all_products_available(self):
        """All products with stock > 0 are marked available."""
        agent = InventoryAgent()
        products = [
            Product(product_id="P001", name="A", category="手机", price=100, stock=500, tags=[]),
            Product(product_id="P002", name="B", category="耳机", price=200, stock=1000, tags=[]),
        ]
        result = await agent._execute(products=products)

        assert isinstance(result, InventoryResult)
        assert result.success is True
        assert set(result.available_products) == {"P001", "P002"}

    @pytest.mark.agent
    async def test_out_of_stock_filtered(self):
        """Products with stock 0 are filtered out."""
        agent = InventoryAgent()
        products = [
            Product(product_id="P001", name="A", category="手机", price=100, stock=500, tags=[]),
            Product(product_id="P002", name="B", category="耳机", price=200, stock=0, tags=[]),
        ]
        result = await agent._execute(products=products)

        assert result.available_products == ["P001"]
        assert "P002" not in result.available_products

    @pytest.mark.agent
    async def test_critical_stock_alert(self):
        """Stock <= SAFETY_STOCK_THRESHOLD triggers critical alert."""
        agent = InventoryAgent()
        products = [
            Product(product_id="P001", name="A", category="手机", price=100, stock=30, tags=[]),
        ]
        result = await agent._execute(products=products)

        assert len(result.low_stock_alerts) == 1
        alert = result.low_stock_alerts[0]
        assert alert["level"] == "critical"
        assert alert["action"] == "urgent_restock"
        assert alert["product_id"] == "P001"

    @pytest.mark.agent
    async def test_warning_stock_alert(self):
        """Stock between SAFETY and LOW thresholds triggers warning alert."""
        agent = InventoryAgent()
        products = [
            Product(product_id="P001", name="A", category="手机", price=100, stock=80, tags=[]),
        ]
        result = await agent._execute(products=products)

        assert len(result.low_stock_alerts) == 1
        alert = result.low_stock_alerts[0]
        assert alert["level"] == "warning"
        assert alert["action"] == "plan_restock"

    @pytest.mark.agent
    async def test_no_alert_for_normal_stock(self):
        """Stock above LOW_STOCK_THRESHOLD produces no alert."""
        agent = InventoryAgent()
        products = [
            Product(product_id="P001", name="A", category="手机", price=100, stock=500, tags=[]),
        ]
        result = await agent._execute(products=products)

        assert len(result.low_stock_alerts) == 0

    @pytest.mark.agent
    def test_critical_stock_purchase_limit(self):
        """Stock <= safety threshold limits purchase to 1."""
        agent = InventoryAgent()
        product = Product(product_id="P001", name="A", category="手机", price=100, stock=30, tags=[])
        limit = agent._calc_purchase_limit(product, 30)
        assert limit == 1

    @pytest.mark.agent
    def test_hot_low_stock_purchase_limit(self):
        """Hot product with low stock limited to HOT_ITEM_PURCHASE_LIMIT."""
        agent = InventoryAgent()
        product = Product(product_id="P001", name="A", category="手机", price=100, stock=80, tags=["新品", "旗舰"])
        limit = agent._calc_purchase_limit(product, 80)
        assert limit == HOT_ITEM_PURCHASE_LIMIT

    @pytest.mark.agent
    def test_hot_moderate_stock_purchase_limit(self):
        """Hot product with stock <= 300 limited to 3."""
        agent = InventoryAgent()
        product = Product(product_id="P001", name="A", category="手机", price=100, stock=250, tags=["新品"])
        limit = agent._calc_purchase_limit(product, 250)
        assert limit == 3

    @pytest.mark.agent
    def test_normal_stock_no_limit(self):
        """Normal stock with non-hot product has no purchase limit."""
        agent = InventoryAgent()
        product = Product(product_id="P001", name="A", category="手机", price=100, stock=500, tags=["日常"])
        limit = agent._calc_purchase_limit(product, 500)
        assert limit is None

    @pytest.mark.agent
    def test_hot_product_detection_flags(self):
        """Hot product detection via tags (旗舰 or 新品)."""
        agent = InventoryAgent()

        flagship = Product(product_id="P001", name="A", category="手机", price=100, stock=80, tags=["旗舰"])
        assert agent._calc_purchase_limit(flagship, 80) == HOT_ITEM_PURCHASE_LIMIT

        new_item = Product(product_id="P002", name="B", category="耳机", price=200, stock=80, tags=["新品"])
        assert agent._calc_purchase_limit(new_item, 80) == HOT_ITEM_PURCHASE_LIMIT

        normal = Product(product_id="P003", name="C", category="平板", price=300, stock=80, tags=["日常"])
        assert agent._calc_purchase_limit(normal, 80) is None

    @pytest.mark.agent
    async def test_empty_products_returns_empty_result(self):
        """Empty product list returns empty everything."""
        agent = InventoryAgent()
        result = await agent._execute(products=[])

        assert result.success is True
        assert result.available_products == []
        assert result.low_stock_alerts == []
        assert result.purchase_limits == {}
        assert result.data["total_checked"] == 0

    @pytest.mark.agent
    async def test_result_confidence(self):
        """Inventory result confidence is 0.95."""
        agent = InventoryAgent()
        products = [Product(product_id="P001", name="A", category="手机", price=100, stock=500, tags=[])]
        result = await agent._execute(products=products)
        assert result.confidence == 0.95
