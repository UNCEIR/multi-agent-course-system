from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "Public Elective Course Multi-Agent System"
    debug: bool = False

    llm_api_key: str = ""
    llm_base_url: str = "https://api.minimax.chat/v1"
    llm_model: str = "MiniMax-M1"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2048
    llm_enable_thinking: bool = False

    redis_url: str = "redis://localhost:6379/0"
    feature_ttl_seconds: int = 86400
    course_recall_cache_enabled: bool = True
    course_recall_cache_ttl_seconds: int = 900
    course_recall_cache_lock_ttl_seconds: int = 5
    course_recall_cache_wait_retries: int = 3
    course_recall_cache_wait_seconds: float = 0.1

    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "ecommerce123"
    mysql_database: str = "ecommerce_ai"
    mysql_pool_size: int = 10
    mysql_max_overflow: int = 20

    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_user: str = ""
    milvus_password: str = ""
    milvus_uri: str = ""
    milvus_collection: str = "product_embeddings"
    course_milvus_collection: str = "course_chunks"
    milvus_dimension: int = 64
    milvus_metric_type: str = "COSINE"
    milvus_index_type: str = "AUTOINDEX"

    database_url: str = "sqlite:///./ecommerce.db"
    embedding_provider: str = "local"
    embedding_dimension: int = 64
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "deterministic-local-v1"
    embedding_batch_size: int = 32
    embedding_timeout_seconds: float = 10.0

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

    # 兼容约束：保留 ECOM_ 历史前缀，避免破坏现有 .env / 容器配置 / 测试环境。
    # 本轮仅做文档与命名收敛，不修改环境变量前缀与字段默认行为。
    model_config = {"env_file": ".env", "env_prefix": "ECOM_"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
