from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "Multi-Agent E-Commerce System"
    debug: bool = False

    llm_api_key: str = ""
    llm_base_url: str = "https://api.minimax.chat/v1"
    llm_model: str = "MiniMax-M1"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2048

    redis_url: str = "redis://localhost:6379/0"
    feature_ttl_seconds: int = 86400

    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection: str = "product_embeddings"

    database_url: str = "sqlite:///./ecommerce.db"

    ab_test_enabled: bool = True
    ab_test_default_bucket_count: int = 100

    agent_timeout_user_profile: float = 5.0
    agent_timeout_intent_recognition: float = 4.0
    agent_timeout_product_recall: float = 6.0
    agent_timeout_semantic_search: float = 6.0
    agent_timeout_product_rerank: float = 8.0
    agent_timeout_marketing_copy: float = 10.0
    agent_timeout_review_summary: float = 8.0
    agent_timeout_image_score: float = 5.0
    agent_timeout_inventory: float = 5.0
    agent_timeout_price_optimization: float = 6.0
    agent_timeout_fraud_detection: float = 5.0
    agent_timeout_customer_service: float = 5.0

    supervisor_max_retries: int = 2
    supervisor_global_timeout: float = 30.0

    model_config = {"env_file": ".env", "env_prefix": "ECOM_"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
