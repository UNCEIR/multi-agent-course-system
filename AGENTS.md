# AGENTS.md

学校公选课 Multi-Agent 推荐系统。学生用自然语言描述选课偏好，系统从 500 门公选课中召回、排序、检查选课风险并返回推荐。

## 环境配置

`python/config/settings.py` 的 `_env_file_candidates()` 按顺序检查：根目录 `.env` → `python/.env` → CWD `.env`。仓库默认只有 `python/.env`（根目录的 `.env` 需自行从 `.env.example` 创建）。所有 env var 使用 `ECOM_` 前缀。

Docker Compose 只注入 `python/.env`。本地 `python main.py` 运行时若根目录无 `.env`，则只加载 `python/.env`。

## 启动命令

```bash
# Python 环境
python -m venv .venv && .venv\Scripts\Activate.ps1
python -m pip install -r python/requirements.txt

# Docker 服务（注意 --profile python 是必须的）
docker compose -f docker-compose.python.yml --profile python up -d
docker compose -f docker-compose.python.yml --profile python ps
docker compose -f docker-compose.python.yml --profile python logs --tail=80 python-api

# 改了 Python 代码后重建镜像
docker compose -f docker-compose.python.yml --profile python up -d --build python-api

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

`pytest.ini` 配置了 `asyncio_mode = auto`，注册了 5 个 marker（`unit`、`integration`、`slow`、`agent`、`api`），并开启了 `--strict-markers`。用未注册的 marker 会直接报错。

覆盖率：`python -m pytest tests/ --cov --cov-report=term-missing`（配置见 `.coveragerc`）。

## 架构

### Supervisor 编排流程

```
Phase 1:    StudentProfileAgent ∥ CourseRecallAgent (profile=None, wide recall)
            └─ 画像成功后, CourseRecallAgent (with profile, refined recall)
Phase 1.5:  HardConstraintFilter (确定性硬约束过滤)
Phase 1.75: LLM 语义初筛 (候选 >40 且画像存在时触发，失败退规则)
Phase 2:    CourseRerankAgent ∥ CourseFeasibilityAgent
Phase 3:    RecommendationReasonAgent (串行)
```

Phase 1.5 违规直接剔除。候选不足时返回 `hard_constraint_sparse`，不放宽条件。

### Supervisor 两种编排模式

| 模式 | 触发方式 | 代码 |
|---|---|---|
| 固定 Pipeline | A/B assign group="control" | `supervisor.recommend()` |
| ReAct 工具调用 | A/B assign group="react" | `supervisor._react_recommend()` |

**ReAct 模式代码已实现但 A/B 实验里无 "react" group**——需在 `services/ab_test.py:48` 注册才能生效。ReAct 使用 7 个工具（`orchestrator/react_tools.py`），硬约束过滤工具锁死不可跳过。

### CourseRecallAgent：wide vs refined

Supervisor 每请求调两次召回——wide（profile=None）和 refined（带画像）。两次的 `prompt` 相同、embedding API 相同、Milvus 相同。**区别仅在于 MySQL 结构化查询的 WHERE 过滤条件不同**（wide 无 domain/campus/category 过滤，refined 有）。`_score_candidates` 忽略 profile 参数——这是设计决定：召回负责广度，精排评分由 RerankAgent 负责。

### 新增字段

- `StudentProfile.grade` / `StudentProfile.department`：`_heuristic_profile()` 正则提取，不作为硬约束
- `RecommendationResponse.priority_advice`：`dict[str, PriorityAdvice{advice, priority}]`，由 FeasibilityAgent 生成，已在顶层 API 响应中透传，前端渲染

### LLM vs Embedding：两个不同的 API 协议

| | LLM | Embedding |
|---|---|---|
| 端点 | `/compatible-mode/v1` | `/api/v1` |
| 协议 | OpenAI 兼容 (`ChatOpenAI`) | **DashScope 原生** |
| 请求体 | `{"model":"...","messages":[...]}` | `{"model":"...","input":{"contents":[{"text":"..."}]},"parameters":{"dimension":1024}}` |
| 响应路径 | `choices[0].message` | `output.embeddings[].embedding` |

`tongyi-embedding-vision-plus-2026-03-06` **只支持 DashScope 原生 API**，不支持 OpenAI 兼容格式。不要试图把 embedding 切到 `/compatible-mode/v1/embeddings`——会返回 404。

### LLM 批量调用与 Token 限制

- **FeasibilityAgent `_llm_priority_advice`**：`max_tokens=4096`，最多送 12 门课给 LLM。超过 12 门的走规则 fallback。若 max_tokens 太小导致 JSON 截断，`_parse_advice_json` 返回空 dict，静默回退到规则路径——**必须看 warning 日志才知道**
- **Supervisor `_llm_semantic_filter`**：`max_tokens=2048`，按 ID 数组返回，不受课程数量截断
- `bind_tools` 模式（ReAct 编排器）依赖 LLM 提供商支持 OpenAI function calling

### HardConstraintFilter 类别模糊匹配

`_fuzzy_text_match()` 做的是**纯子串匹配**（去掉"类"字后）：

```python
required_core = "理工类".replace("类", "") → "理工"
actual_core   = "自然科学与工程技术类".replace("类", "") → "自然科学与工程技术"
# "理工" in "自然科学与工程技术" → False
```

**"理工"不匹配"自然科学与工程技术"、"文科"不匹配"人文与社会科学"**。需要在两处修：
1. `student_profile_agent.py:190` `_extract_prompt_hard_constraints` 的 `category_rules` 补关键词
2. `hard_constraint_filter.py:201` `_fuzzy_text_match` 加别名映射表

### Embedding Client 实例化链

```
main.py:51          → CourseVectorRepository(build_embedding_client())    # 全局单例
course_recall_agent.py:27 → CourseVectorRepository(build_embedding_client())  # Agent 自建
```

两处都调用 `build_embedding_client()`，都读同一个 settings。

### Redis 召回缓存

- 缓存 key 由 `RecallCacheKeyBuilder` 基于结构化 profile 字段或 prompt 文本生成
- TTL = 15 分钟（`ECOM_COURSE_RECALL_CACHE_TTL_SECONDS=900`）
- 缓存命中时完全不调 embedding API，`recall_strategies` 只含 `redis_recall_cache_hit`
- 用相同 prompt 测试 15 分钟内会一直命中缓存

### 数据存储

| 存储 | 表/Collection | 内容 |
|---|---|---|
| MySQL | `course_records` | 500 门课程完整结构化字段 |
| MySQL | `course_chunks` | 500×4=2000 条 chunk 文本元数据 |
| Milvus | `course_chunks_real` | 2000 条 1024 维向量 |

每门课拆成 4 类 chunk：`basic`、`schedule_capacity`、`learning_profile`、`audience_tags`。维度 1024。

### CI/CD

此仓库无 CI 配置（无 `.github/workflows` 等），不要尝试 CI 命令。

### 前端

前端（Vite + React + TypeScript）**无 lint / test / format 脚本**。不要尝试 `npm run lint`、`npm test`、`npm run format`。

## 常见坑

- 改了任何 Python 代码后 Docker 必须 `--build` 重建镜像才能生效
- `_env_file_candidates()` 加载根目录 `.env` 和 `python/.env`，只改一个可能被另一个覆盖
- CSV 导入嵌入向量阶段很慢（500门=2000次 API 调用），超时概率高，先用 `--limit` 验证
- 测试 `course_recall_cache.py` 用 mock 替换 `agent.vector_repo.search`，不调 embedding
- Milvus 向量缺失时用 `python/scripts/backfill_milvus_vectors.py` 按 MySQL 差异补数
- 根目录 `docker-compose.yml` 是旧的电商系统，公选课只用 `docker-compose.python.yml --profile python`
- MySQL 宿主机端口 **3307→3306**；容器内用 3306，宿主机直连用 3307
- SSL 证书域名不匹配，`ECOM_HTTPX_VERIFY_SSL=false` **必须设为 false**
- **HardConstraintFilter 类别匹配是纯子串**：`"理工"` 不匹配 `"自然科学与工程技术"`。原因见上方 "HardConstraintFilter 类别模糊匹配" 章节
- **FeasibilityAgent LLM 调用失败可能静默**：`_parse_advice_json` 返回空 dict 时不抛异常，只走规则 fallback。排查时搜 `llm_advice_failed` 或 `llm_advice_parse_empty` 日志
- `_score_candidates` 接受 `profile` 参数但不用——**不是 bug**，召回阶段负责广度，精排由 RerankAgent 负责
