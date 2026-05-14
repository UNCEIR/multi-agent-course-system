# AGENTS.md

学校公选课 Multi-Agent 推荐系统。学生用自然语言描述选课偏好，系统从 500 门公选课中召回、排序、检查选课风险并返回推荐。

## 环境配置

两个 `.env` 文件都会被 `python/config/settings.py` 的 `_env_file_candidates()` 加载（先根目录再 `python/`）。所有 env var 使用 `ECOM_` 前缀。

Docker Compose 只注入 `python/.env`；根目录 `.env` 供本地 `python main.py` 使用。两者内容保持同步。

## 启动命令

```bash
# Python 环境
python -m venv .venv && .venv\Scripts\Activate.ps1
python -m pip install -r python/requirements.txt

# Docker 服务（注意 --profile python 是必须的）
docker compose -f docker-compose.python.yml --profile python up -d
docker compose -f docker-compose.python.yml --profile python ps
docker compose -f docker-compose.python.yml --profile python logs --tail=80 python-api

# 导入数据
cd python
python scripts/ingest_course_dataset.py --limit 20   # 先少量验证
python scripts/ingest_course_dataset.py               # 全量 500 门

# 测试 API
curl -sS -X POST http://localhost:8000/api/v1/recommend \
  -H "Content-Type: application/json" \
  --data-binary "@python/scripts/curl_recommend_payload.json"
```

## 测试

```bash
cd python
python -m pytest tests/ -v                     # 全部测试
python -m pytest tests/ -m "not slow"          # 跳过需外部服务的测试
```

测试 mock 在 agent 层（`agent.vector_repo.search = MagicMock(...)`），不 mock 底层 embedding client。

## 架构关键事实

### LLM vs Embedding：两个不同的 API 协议

| | LLM | Embedding |
|---|---|---|
| 端点 | `/compatible-mode/v1` | `/api/v1` |
| 协议 | OpenAI 兼容 (`ChatOpenAI`) | **DashScope 原生** |
| 请求体 | `{"model":"...","messages":[...]}` | `{"model":"...","input":{"contents":[{"text":"..."}]},"parameters":{"dimension":1152}}` |
| 响应路径 | `choices[0].message` | `output.embeddings[].embedding` |

`tongyi-embedding-vision-plus-2026-03-06` **只支持 DashScope 原生 API**，不支持 OpenAI 兼容格式。不要试图把 embedding 切到 `/compatible-mode/v1/embeddings`——会返回 404 `model_not_supported`。

### Embedding Client 实例化链

```
main.py:48          → CourseVectorRepository(build_embedding_client())    # 全局单例（供 health check）
course_recall_agent.py:25 → CourseVectorRepository(build_embedding_client())  # Agent 自己再创建一个
```

两处都调用 `build_embedding_client()`，都读同一个 settings。`DashScopeMultimodalEmbeddingClient` 通过 `_build_endpoint()` 拼接完整 URL：`{base}/services/embeddings/multimodal-embedding/multimodal-embedding`。

### Redis 召回缓存

- 缓存 key 由 `RecallCacheKeyBuilder` 基于 **结构化 profile 字段**（domains、categories、campus 等）或 prompt 文本生成
- 默认 TTL = 15 分钟（`ECOM_COURSE_RECALL_CACHE_TTL_SECONDS=900`）
- 缓存命中时 `recall_strategies` 只包含 `redis_recall_cache_hit`——**完全不调 embedding API**
- 用相同 prompt 测试 15 分钟内会一直命中缓存，看不到 embedding 调用

### SSL 证书

MaaS 代理的自定义域名 `llm-oe8ejw5pgtze0knw.cn-beijing.maas.aliyuncs.com` 与 TLS 证书 SAN 不匹配。`ECOM_HTTPX_VERIFY_SSL=false` 必须设为 false，否则所有 LLM 和 embedding 请求都会因证书校验失败而报错。

### 数据存储

| 存储 | 表/Collection | 内容 |
|---|---|---|
| MySQL | `course_records` | 500 门课程完整结构化字段 |
| MySQL | `course_chunks` | 500×4=2000 条 chunk 文本元数据 |
| Milvus | `course_chunks_real` | 2000 条 1152 维向量 |

每门课拆成 4 类 chunk：`basic`、`schedule_capacity`、`learning_profile`、`audience_tags`。维度 1152（`ECOM_MILVUS_DIMENSION=1152`）。

### Supervisor 三阶段编排

```
Phase 1: StudentProfileAgent ∥ CourseRecallAgent (profile=None, wide recall)
         └─ 画像成功后, CourseRecallAgent (with profile, refined recall)
Phase 2: CourseRerankAgent ∥ CourseFeasibilityAgent
Phase 3: RecommendationReasonAgent (串行)
```

## 常见坑

- 改了 `embedding_client.py` 后 Docker 必须 `--build` 重建镜像才能生效
- `_env_file_candidates()` 会找根目录 `.env` 和 `python/.env` 两个文件，如果只改一个可能被另一个覆盖
- CSV 导入在嵌入向量阶段很慢（500门=2000次 API 调用），超时概率高，建议先用 `--limit` 验证
- 测试 `course_recall_cache.py` 直接用 mock 替换 `agent.vector_repo.search`，不会真正调 embedding
