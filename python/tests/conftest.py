"""Shared fixtures for all Python tests."""

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def mock_llm_response():
    """Return a mock LangChain AIMessage with JSON content."""

    def _make(content: str):
        mock = MagicMock()
        mock.content = content
        return mock

    return _make


@pytest.fixture
def mock_chat_openai():
    """Return a mock ChatOpenAI that returns a configurable response."""
    with patch("agents.user_profile_agent.ChatOpenAI") as mock_cls, \
         patch("agents.product_rec_agent.ChatOpenAI") as mock_cls2, \
         patch("agents.marketing_copy_agent.ChatOpenAI") as mock_cls3:
        mock_cls.return_value.ainvoke = AsyncMock()
        mock_cls2.return_value.ainvoke = AsyncMock()
        mock_cls3.return_value.ainvoke = AsyncMock()
        yield mock_cls, mock_cls2, mock_cls3


@pytest.fixture
def sample_user_id():
    return "user_test_001"


@pytest.fixture
def sample_profile_data():
    """Sample parsed user profile dict."""
    return {
        "segments": ["active", "high_value"],
        "preferred_categories": ["手机", "耳机"],
        "price_range": [500, 8000],
        "rfm_score": {"recency": 0.85, "frequency": 0.6, "monetary": 0.7},
        "real_time_tags": {"活跃时段": "晚间", "偏好风格": "科技"},
    }


@pytest.fixture
def sample_candidate_products():
    """Sample products for recall testing."""
    from models.schemas import Product

    return [
        Product(product_id="P001", name="iPhone 16 Pro", category="手机", price=7999, brand="Apple", seller_id="S01", stock=500, tags=["旗舰", "新品"]),
        Product(product_id="P002", name="华为 Mate 70", category="手机", price=5999, brand="华为", seller_id="S02", stock=300, tags=["旗舰", "国产"]),
        Product(product_id="P003", name="AirPods Pro 3", category="耳机", price=1899, brand="Apple", seller_id="S01", stock=1000, tags=["降噪", "无线"]),
        Product(product_id="P005", name="iPad Air M3", category="平板", price=4799, brand="Apple", seller_id="S01", stock=400, tags=["学习", "办公"]),
        Product(product_id="P010", name="罗技MX Master 3S", category="配件", price=749, brand="罗技", seller_id="S08", stock=500, tags=["无线", "办公"]),
    ]


@pytest.fixture
def mock_settings(monkeypatch):
    """Override settings for test environment."""
    from config.settings import get_settings
    monkeypatch.setenv("ECOM_LLM_API_KEY", "sk-test-key")
    monkeypatch.setenv("ECOM_LLM_BASE_URL", "https://test-api.example.com/v1")
    monkeypatch.setenv("ECOM_LLM_MODEL", "test-model")
    monkeypatch.setenv("ECOM_REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("ECOM_DATABASE_URL", "sqlite:///:memory:")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
