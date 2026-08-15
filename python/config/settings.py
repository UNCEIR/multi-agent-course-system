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
    app_name: str = "mult-agent-university-system"
    debug: bool = False
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "qwen3.6-max-preview"
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

    agent_context_window_tokens: int = 128000  # 模型上下文窗口（qwen3.6-max-preview ≈ 128K）
    agent_compaction_trigger_tokens: int | None = None  # None 时用 context_window-13000
    agent_compaction_keep_tokens: int = 20000  # 决策 11: keepRecentTokens=20000
    agent_compaction_trigger_messages: int | None = 8  # demo 用 messages 触发（生产置 None 走 token 阈值）

    supervisor_max_retries: int = 2
    supervisor_global_timeout: float = 30.0
    stream_timeout_seconds: float = 60.0

    langchain_api_key: str = ""

    langchain_endpoint: str = "https://api.smith.langchain.com"
    langchain_tracing_v2: bool = True
    langchain_project: str = "mult-agent-university-system"

    # ── Phase 2：MinIO（report artifact 存储，本地兜底）─────────────
    minio_endpoint: str = "localhost"
    minio_port: int = 9000
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "12345678"
    minio_secure: bool = False
    minio_report_bucket: str = "report-artifacts"
    minio_connect_timeout: float = 3.0  # 探测/超时，超时自动走本地兜底

    # ── Phase 2：report（教师端批量成绩单）─────────────────────────
    report_download_ttl_hours: int = 24  # token 下载链接有效期
    report_download_secret: str = ""  # HMAC 签名密钥（.env 注入，空则禁用下载端点）
    report_max_file_mb: int = 10  # 单 Excel 上限
    report_max_files: int = 20  # 一次批量文件数上限
    report_render_concurrency: int = 4  # 渲染并发（WeasyPrint 同步：asyncio.to_thread + Semaphore）
    report_llm_fill_concurrency: int = 4  # LLM 填表/综合评语并发
    report_student_timeout_seconds: float = 60.0  # 单学生全链超时

    # ── Phase 2：evaluation（教师端生成 → 学生端同步）──────────────
    evaluation_radar_axis_count: int = 5  # 雷达轴数（硬约束：维度提案必须恰为 N 个）

    # ── Phase 2：MCP 服务器注册表（三服务器占位）───────────────────
    # 格式：{"server_name": {"transport": "streamable_http", "url": "...", "api_key_env": "...", "namespace": "search"}}
    # pydantic-settings 从 .env 注入 dict 需 JSON 字符串（如 MCP_SERVERS='{"tavily":{...}}'）
    mcp_servers: dict = {}

    # ── Phase 2：视觉模型（image_recognize 直连，复用文本模型 key）──
    vision_model: str = "qwen3-vl-plus"  # 多模态选型（用户 2026-08-13 确认）

    # ── Phase 2：插件工具 ────────────────────────────────────────────
    tavily_api_key: str = ""  # web_search 直连兜底（MCP 主路熔断时用）

    # ── Phase 2：即梦 4.0（火山引擎）图像生成 ────────────────────────
    volc_access_key: str = ""  # 火山引擎 AK（仅 .env，不入库）
    volc_secret_key: str = ""  # 火山引擎 SK（仅 .env，不入库）
    jimeng_req_key: str = "jimeng_t2i_v40"  # 即梦 4.0 服务标识
    jimeng_region: str = "cn-north-1"  # 签名 Region（固定）
    jimeng_service: str = "cv"  # 签名 Service（固定）
    jimeng_poll_interval_base: float = 3.0  # 轮询起始间隔（指数退避 3→6→10）
    jimeng_poll_interval_max: float = 10.0  # 轮询间隔封顶
    jimeng_poll_timeout: float = 120.0  # 总轮询超时（超时保留 task_id 可续查）
    jimeng_poll_max_attempts: int = 10  # 单次生成查询次数上限
    jimeng_scale_default: float = 0.7  # scale 默认值（文本遵从权重，eval 对照 0.5/0.7/0.9）

    # ── Phase 2：E2B 代码执行沙箱（e2b Python SDK 内核，自建 stdio MCP server）──
    e2b_api_key: str = ""  # E2B API key（仅 .env，不入库）
    e2b_sandbox_timeout: int = 300  # sandbox 保活 TTL 秒（每次执行后刷新）

    # ── Phase 2：chat 长期记忆（pi 机制移植）───────────────────────
    memory_extract_threshold_messages: int = 20  # 消息数达阈值触发跨会话记忆提取
    memory_extract_max_messages: int = 200  # 单批提取最大消息数（oldest-first 分批推进）
    memory_extract_retry_after_seconds: int = 600  # 提取失败退避间隔
    memory_entries_per_user_limit: int = 50  # 新会话注入的记忆条目上限（总字符 ≤2000）

    model_config = SettingsConfigDict(
        env_file=_env_file_candidates(),
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
