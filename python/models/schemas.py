from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class UserSegment(str, Enum):
    NEW_USER = "new_user"
    ACTIVE = "active"
    HIGH_VALUE = "high_value"
    PRICE_SENSITIVE = "price_sensitive"
    CHURN_RISK = "churn_risk"


class IntentType(str, Enum):
    SEARCH = "search"
    RECOMMEND = "recommend"
    COMPARE = "compare"
    PURCHASE = "purchase"
    PRICE_CHECK = "price_check"
    ORDER_STATUS = "order_status"
    SUPPORT = "support"
    BROWSE = "browse"


class FraudLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class InventoryLevel(str, Enum):
    OUT_OF_STOCK = "out_of_stock"
    CRITICAL = "critical"
    LOW = "low"
    NORMAL = "normal"
    ABUNDANT = "abundant"


class PriceStrategy(str, Enum):
    STANDARD = "standard"
    PENETRATION = "penetration"
    SKIMMING = "skimming"
    DYNAMIC = "dynamic"
    PROMOTIONAL = "promotional"


class CopyStyle(str, Enum):
    FORMAL = "formal"
    CASUAL = "casual"
    URGENT = "urgent"
    LUXURY = "luxury"
    FRIENDLY = "friendly"


class SentimentPolarity(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    MIXED = "mixed"


class ServiceAction(str, Enum):
    NONE = "none"
    AUTO_REPLY = "auto_reply"
    ESCALATE_HUMAN = "escalate_human"
    REFUND_INITIATE = "refund_initiate"
    COUPON_ISSUE = "coupon_issue"


# -------------------- Data Models --------------------

class UserProfile(BaseModel):
    user_id: str
    age: int | None = None
    gender: str | None = None
    city: str | None = None
    segments: list[UserSegment] = Field(default_factory=list)
    preferred_categories: list[str] = Field(default_factory=list)
    price_range: tuple[float, float] = (0.0, 10000.0)
    recent_views: list[str] = Field(default_factory=list)
    recent_purchases: list[str] = Field(default_factory=list)
    rfm_score: dict[str, float] = Field(default_factory=dict)
    real_time_tags: dict[str, Any] = Field(default_factory=dict)


class Product(BaseModel):
    product_id: str
    name: str
    category: str
    price: float
    description: str = ""
    brand: str = ""
    seller_id: str = ""
    stock: int = 0
    tags: list[str] = Field(default_factory=list)
    score: float = 0.0
    image_url: str = ""
    rating: float = 0.0
    review_count: int = 0
    sales_count_30d: int = 0
    created_at: datetime | None = None
    cost_price: float = 0.0


class RecommendationRequest(BaseModel):
    user_id: str
    scene: str = "homepage"
    num_items: int = 10
    context: dict[str, Any] = Field(default_factory=dict)
    query: str = ""
    device_type: str = "web"


class RecommendationResponse(BaseModel):
    request_id: str
    user_id: str
    products: list[Product] = Field(default_factory=list)
    marketing_copies: list[dict[str, str]] = Field(default_factory=list)
    review_summaries: dict[str, str] = Field(default_factory=dict)
    image_scores: dict[str, float] = Field(default_factory=dict)
    price_adjustments: dict[str, float] = Field(default_factory=dict)
    fraud_assessment: dict[str, Any] = Field(default_factory=dict)
    service_recommendation: dict[str, Any] = Field(default_factory=dict)
    experiment_group: str = "control"
    agent_results: dict[str, AgentResult] = Field(default_factory=dict)
    agent_latencies: dict[str, float] = Field(default_factory=dict)
    total_latency_ms: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.now)


class AgentResult(BaseModel):
    agent_name: str
    success: bool = True
    latency_ms: float = 0.0
    error: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0


class UserProfileResult(AgentResult):
    agent_name: str = "user_profile"
    profile: UserProfile | None = None


class IntentRecognitionResult(AgentResult):
    agent_name: str = "intent_router"
    intent: IntentType = IntentType.BROWSE
    confidence_score: float = 0.5
    similarity_scores: dict[str, float] = Field(default_factory=dict)
    matched_template: str = ""
    target_agents: list[str] = Field(default_factory=list)
    extracted_entities: dict[str, Any] = Field(default_factory=dict)


class ProductRecallResult(AgentResult):
    agent_name: str = "product_recall"
    products: list[Product] = Field(default_factory=list)
    recall_strategies: list[str] = Field(default_factory=list)


class ProductRecResult(AgentResult):
    agent_name: str = "product_rec"
    products: list[Product] = Field(default_factory=list)
    recall_strategy: str = ""


class SemanticSearchResult(AgentResult):
    agent_name: str = "semantic_search"
    products: list[Product] = Field(default_factory=list)
    query_understanding: str = ""


class ProductRerankResult(AgentResult):
    agent_name: str = "product_rerank"
    products: list[Product] = Field(default_factory=list)
    rerank_strategy: str = ""


class MarketingCopyResult(AgentResult):
    agent_name: str = "marketing_copy"
    copies: list[dict[str, str]] = Field(default_factory=list)
    prompt_template_used: str = ""
    copy_style: CopyStyle = CopyStyle.FORMAL


class ReviewSummaryResult(AgentResult):
    agent_name: str = "review_summary"
    summaries: dict[str, str] = Field(default_factory=dict)
    sentiment_scores: dict[str, float] = Field(default_factory=dict)


class ImageScoreResult(AgentResult):
    agent_name: str = "image_score"
    scores: dict[str, float] = Field(default_factory=dict)
    attractiveness_tiers: dict[str, int] = Field(default_factory=dict)


class InventoryResult(AgentResult):
    agent_name: str = "inventory"
    available_products: list[str] = Field(default_factory=list)
    low_stock_alerts: list[dict[str, Any]] = Field(default_factory=list)
    purchase_limits: dict[str, int] = Field(default_factory=dict)
    inventory_levels: dict[str, InventoryLevel] = Field(default_factory=dict)
    filtered_products: list[dict[str, Any]] = Field(default_factory=list)


class PriceOptimizationResult(AgentResult):
    agent_name: str = "price_optimization"
    suggested_prices: dict[str, float] = Field(default_factory=dict)
    discount_amounts: dict[str, float] = Field(default_factory=dict)
    strategy: PriceStrategy = PriceStrategy.STANDARD


class FraudDetectionResult(AgentResult):
    agent_name: str = "fraud_detection"
    fraud_level: FraudLevel = FraudLevel.NONE
    risk_score: float = 0.0
    flagged_reasons: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


class CustomerServiceResult(AgentResult):
    agent_name: str = "customer_service"
    action: ServiceAction = ServiceAction.NONE
    response_template: str = ""
    auto_reply: str = ""
    escalation_reason: str | None = None
