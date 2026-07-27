from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env 默认可在「仓库根」或「python/」下；仅依赖 cwd 的 ".env" 会导致在 python/ 里起服务时读不到根目录配置，
# 从而回落到默认 MiniMax 地址，灵积控制台无调用记录。
_PYTHON_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PYTHON_ROOT.parent


def _env_file_candidates() -> tuple[str, ...] | str:
    paths: list[Path] = []
    for candidate in (_REPO_ROOT / ".env", _PYTHON_ROOT / ".env"):
        if candidate.is_file():
            paths.append(candidate)
    if paths:
        return tuple(str(p) for p in paths)
    return ".env"


class Settings(BaseSettings):
    app_name: str = "Public Elective Course Multi-Agent System"
    debug: bool = False

    llm_api_key: str = ""
    llm_base_url: str = "https://one.zhique.cn/v1"
    llm_model: str = "deepseek-v4-flash"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096
    llm_enable_thinking: bool = True

    redis_url: str = "redis://localhost:6379/0"
    feature_ttl_seconds: int = 86400
    course_recall_cache_enabled: bool = True
    course_recall_cache_ttl_seconds: int = 900
    course_recall_cache_lock_ttl_seconds: int = 5
    course_recall_cache_wait_retries: int = 3
    course_recall_cache_wait_seconds: float = 0.1
    course_recall_cache_semantic_enabled: bool = True
    course_recall_cache_semantic_threshold: float = 0.95
    course_recall_cache_semantic_max_candidates: int = 12
    course_recall_cache_semantic_min_prompt_chars: int = 8

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
    course_milvus_collection: str = "course_chunks_real"
    milvus_dimension: int = 1024
    milvus_metric_type: str = "COSINE"
    milvus_index_type: str = "AUTOINDEX"

    # Embedding 走公司内部中转站的 OpenAI /embeddings 协议；
    # 保留 dashscope_multimodal 作为旧 DashScope 原生协议的兼容 provider。
    embedding_provider: str = "openai"
    embedding_dimension: int = 1024
    embedding_base_url: str = "https://one.zhique.cn/v1"
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-v4"
    embedding_batch_size: int = 8
    embedding_timeout_seconds: float = 30.0
    httpx_verify_ssl: bool = True

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
    stream_timeout_seconds: float = 60.0

    # 兼容约束：保留 ECOM_ 历史前缀，避免破坏现有 .env / 容器配置 / 测试环境。
    # env_file 先仓库根再 python/，后者同名变量覆盖前者。
    model_config = SettingsConfigDict(
        env_file=_env_file_candidates(),
        env_prefix="ECOM_",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
