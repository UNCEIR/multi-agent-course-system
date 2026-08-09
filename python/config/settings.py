from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env 默认可在「仓库根」或「python/」下；仅依赖 cwd 的 ".env" 会导致在 python/ 里起服务时读不到根目录配置，
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
    app_name: str = "multi-agent-course-system"
    debug: bool = False
    llm_api_key: str = ""
    llm_base_url: str = ""
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
    mysql_password: str = "123456"
    mysql_database: str = "course_system"
    mysql_pool_size: int = 10
    mysql_max_overflow: int = 20

    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_user: str = ""
    milvus_password: str = ""
    milvus_uri: str = ""
    milvus_collection: str = "product_embeddings"
    course_milvus_collection: str = "course_chunks_real"
    document_milvus_collection: str = "document_chunks"
    milvus_dimension: int = 1024
    milvus_metric_type: str = "COSINE"
    milvus_index_type: str = "AUTOINDEX"

  
    embedding_provider: str = "openai"
    embedding_dimension: int = 1024
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-v4"
    embedding_batch_size: int = 8
    embedding_timeout_seconds: float = 30.0
    httpx_verify_ssl: bool = True

    ab_test_enabled: bool = True
    ab_test_default_bucket_count: int = 100

    agent_timeout_user_profile: float = 15.0
    agent_timeout_product_recall: float = 10.0
    agent_timeout_product_rerank: float = 15.0
    agent_timeout_marketing_copy: float = 20.0
    agent_timeout_inventory: float = 20.0

    # ── v2.0.0 主 Agent 记忆 / skill / checkpoint 配置 ─────────────────
    memory_dir: str = ""  # 长期记忆目录（AGENTS.md 所在目录，默认 <repo_root>/python/memories）
    skills_dir: str = ""  # skill 技能文档目录（默认 <repo_root>/python/skills）
    checkpoint_sqlite_path: str = ""  # SqliteSaver 持久路径（默认 <repo_root>/python/.checkpoint.db）

    agent_context_window_tokens: int = 128000  # 模型上下文窗口（deepseek-v4-flash ≈ 128K）
    agent_compaction_trigger_tokens: int | None = None  # None 时用 context_window-13000
    agent_compaction_keep_tokens: int = 20000  # 决策 11: keepRecentTokens=20000
    agent_compaction_trigger_messages: int | None = 8  # demo 用 messages 触发（生产置 None 走 token 阈值）

    supervisor_max_retries: int = 2
    supervisor_global_timeout: float = 30.0
    stream_timeout_seconds: float = 60.0

    langchain_api_key: str = ""

    langchain_endpoint: str = "https://api.smith.langchain.com"
    langchain_tracing_v2: bool = True
    langchain_project: str = "multi-agent-course-system"

  
    model_config = SettingsConfigDict(
        env_file=_env_file_candidates(),
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
