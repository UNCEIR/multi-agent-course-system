# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在此仓库中工作时提供指导。

## 项目简介

学校公选课 Multi-Agent 推荐系统 —— 学生用自然语言描述选课偏好，系统从约 500 门真实公选课中完成召回、过滤、排序并给出可解释的推荐。

## 常用命令

```bash
# Python 虚拟环境（首次创建）
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -r python/requirements.txt

# Docker 服务（必须使用 --profile python）
docker compose -f docker-compose.python.yml --profile python up -d
docker compose -f docker-compose.python.yml --profile python ps
docker compose -f docker-compose.python.yml --profile python logs --tail=80 python-api

# Python 代码修改后重建镜像（Docker 会缓存构建层）
docker compose -f docker-compose.python.yml --profile python up -d --build python-api

# 导入课程数据
cd python
python scripts/ingest_course_dataset.py --limit 20   # 先少量验证
python scripts/ingest_course_dataset.py               # 全量约 500 门

# 回填缺失的 Milvus 向量
python scripts/backfill_milvus_vectors.py

# 测试 API
curl -sS -X POST http://localhost:8000/api/v1/recommend \
  -H "Content-Type: application/json" \
  --data-binary "@python/scripts/curl_recommend_payload.json"

# 前端（可选）
cd frontend && npm install && npm run dev    # → http://localhost:5173

# 测试
cd python
python -m pytest tests/ -v                         # 全部测试
python -m pytest tests/ -m "not slow"              # 跳过需要外部服务的慢速测试
python -m pytest tests/ --cov --cov-report=term-missing   # 带覆盖率

# 运行单个测试文件
python -m pytest tests/test_hard_constraint_prompt_fallback.py -v
```

## 架构

### 请求链路（固定 Pipeline —— 默认路径）

```
POST /api/v1/recommend
  → SupervisorOrchestrator
    → Phase 1:    StudentProfileAgent ∥ CourseRecallAgent（宽召回，profile=None）
                  └─ 画像成功后 → CourseRecallAgent（精召回，带画像）
    → Phase 1.5:  HardConstraintFilter（确定性过滤 —— 校区、类别、考试等）
    → Phase 1.75: LLM 语义初筛（仅在候选 > 40 且画像存在时触发）
    → Phase 2:    CourseRerankAgent ∥ CourseFeasibilityAgent
    → Phase 3:    RecommendationReasonAgent（串行，依赖最终课程和风险）
```

### 双模式编排

| 模式 | 触发方式 | 代码路径 |
|------|---------|-----------|
| 固定 Pipeline | 默认（`ab_engine.assign()` → `rec_strategy` → `control`/`treatment_llm`） | `supervisor.recommend()` |
| ReAct 工具调用 | 需要路由到 `react_vs_pipeline` 实验 → `react` 分组 | `supervisor._react_recommend()` |

**当前状态**：`supervisor.recommend()` 调用 `ab_engine.assign(user_id)`，默认使用实验 `rec_strategy`（分组：`control`、`treatment_llm`）。`react_vs_pipeline` 实验已在 `ab_test.py:48` 注册，但 supervisor 从未路由到它。第 101 行的 `if experiment.get("group") == "react"` 检查目前是死代码，除非将 supervisor 改为使用 `react_vs_pipeline` 实验。

ReAct 模式使用 7 个工具（`orchestrator/react_tools.py`）：`extract_profile`、`search_courses`、`filter_hard_constraints`（已锁定 —— 如 LLM 跳过，循环结束时会强制执行）、`semantic_filter_courses`、`rerank_courses`、`check_feasibility`、`generate_reasons`。最多 10 轮 LLM 工具调用。

### 关键设计决策

1. **评分职责分离**：`CourseRecallAgent._score_candidates()` 负责广度（仅关键词匹配 + 热度 —— 接受 `profile` 参数但有意不使用）。`CourseRerankAgent._compute_score()` 负责精度（完整的 profile 偏好匹配 + Milvus COSINE 融合：`final = profile_score * (1.0 + milvus_sim * 0.5)`）。乘法公式确保规则分为 0 时，Milvus 语义相似度无法"拯救"该课程。

2. **硬约束是确定性过滤，而非评分项**：`HardConstraintFilter` 在重排之前移除违规课程，LLM 重排器永远不会看到它们。候选不足时返回 `hard_constraint_sparse` 警告 —— 不会悄悄放宽约束。

3. **每个请求只调用一次 Embedding**：`CourseRecallAgent._execute()` 在入口处计算一次 `query_embedding`，然后传递给语义缓存探测、Milvus 搜索和缓存索引三个消费者 —— 从 3 次调用降到 1 次。

4. **Redis 仅缓存候选课程 ID，不缓存完整课程对象**：缓存命中 → 仍回 MySQL 取完整数据，确保容量和约束信息始终是最新的。

5. **所有 Agent 继承 `BaseAgent`**：模板方法模式，内置 tenacity 重试、耗时追踪、错误计数和 `_fallback()`。每个 Agent 独立失败，返回降级结果。

### 数据架构

| 存储 | 内容 | 用途 |
|------|------|------|
| MySQL `course_records` | 500 门课程结构化字段 + `raw_json` | 事实来源 |
| MySQL `course_chunks` | 500×4=2000 条文本块（basic、schedule_capacity、learning_profile、audience_tags） | 块元数据 |
| Milvus `course_chunks_real` | 2000 条向量，维度 1152 | 语义召回 |
| Redis | 候选课程 ID 列表（非完整对象） | 召回缓存（TTL 15 分钟） |

分块策略避免语义稀释 —— 例如"不考试、作业少"命中 `learning_profile` 块，不会被校区、地点等文本淹没。

### LLM 与 Embedding —— 两种不同的 API 协议

| | LLM | Embedding |
|---|---|---|
| 端点 | `/compatible-mode/v1`（OpenAI 兼容） | `/api/v1`（DashScope 原生） |
| 客户端 | `ChatOpenAI` | 自定义 `EmbeddingClient` |
| 模型 | 可配置 | `tongyi-embedding-vision-plus` |

Embedding 模型**不支持** OpenAI `/embeddings` 格式 —— 仅支持 DashScope 原生 API。**不要**将 Embedding 切换到 `/compatible-mode/v1`。

## 常见陷阱

- **任何 Python 代码修改后 Docker 必须 `--build`** —— 镜像在构建时复制源码。
- **`.env` 加载顺序**：仓库根目录 `.env` → `python/.env`（后者覆盖前者）。Docker 仅注入 `python/.env`。如果两者都存在，根目录的值可能被静默覆盖。
- **MySQL 宿主机端口是 3307→3306**：宿主机连接 `localhost:3307`，容器内用 `mysql:3306`。
- **`ECOM_HTTPX_VERIFY_SSL=false`** 是必需的，当 MaaS 端点使用自定义域名证书且 SAN 不匹配时。
- **HardConstraintFilter 类别匹配是纯子串**：`"理工"` **不匹配** `"自然科学与工程技术"`。需要在 `student_profile_agent.py:190`（`category_rules`）和 `hard_constraint_filter.py:201`（`_fuzzy_text_match`）中添加别名映射。
- **FeasibilityAgent 的 LLM 调用失败是静默的**：`_parse_advice_json()` 解析失败时返回空 dict → 规则兜底，不抛异常。排查时搜索日志 `llm_advice_parse_empty` 或 `llm_advice_failed`。
- **FeasibilityAgent 最多送 12 门课给 LLM**（`max_tokens=4096`）。超过 12 门 → 仅走规则兜底。
- **语义缓存阈值是 0.95**（从 0.9 提高），因为 1152 维向量对句式模板相似但关键词不同的查询区分度不足。Prompt 始终参与缓存 key 计算。
- **无 CI/CD** —— 没有 `.github/workflows`。不要尝试 CI 命令。
- **前端无 lint/test/format 脚本** —— `npm run lint`、`npm test`、`npm run format` 都不存在。
- **`_score_candidates` 接受但不使用 `profile` 参数是有意为之**，不是 bug。
- **`pytest.ini` 启用了 `--strict-markers`** —— 使用未注册的 marker 会导致测试失败。
- **仓库根目录的旧 `docker-compose.yml` 是电商系统前身用的** —— 公选课系统请使用 `docker-compose.python.yml --profile python`。

## 核心文件

| 文件 | 职责 |
|------|------|
| `python/main.py` | FastAPI 入口 —— 薄层，委托给 Supervisor |
| `python/config/settings.py` | 所有配置，`ECOM_` 前缀，先加载仓库根 `.env` 再加载 `python/.env` |
| `python/models/schemas.py` | Pydantic 模型：请求、响应、Course、StudentProfile、AgentResult |
| `python/orchestrator/supervisor.py` | 核心编排（约 800 行）—— Pipeline + ReAct 双模式 |
| `python/orchestrator/hard_constraint_filter.py` | 确定性硬约束过滤 |
| `python/orchestrator/react_tools.py` | 7 个 ReAct 工具定义 + `ReactToolExecutor` |
| `python/agents/base_agent.py` | Agent 基类，含重试/兜底/耗时统计 |
| `python/agents/student_profile_agent.py` | 从自然语言中提取结构化画像 + 硬约束 |
| `python/agents/course_recall_agent.py` | 多源召回（Redis→MySQL→Milvus→mock 兜底） |
| `python/agents/course_rerank_agent.py` | 规则预打分 + LLM 候选内重排 |
| `python/agents/course_feasibility_agent.py` | 容量/风险检查 + LLM 抢课建议（最多 12 门） |
| `python/agents/recommendation_reason_agent.py` | 生成每门课的推荐理由 |
| `python/repositories/course_repository.py` | MySQL 课程 CRUD |
| `python/repositories/course_vector_repository.py` | Milvus 向量检索 |
| `python/repositories/course_recall_cache_repository.py` | Redis 精确 + 语义召回缓存 |
| `python/services/ab_test.py` | A/B 分桶 + Thompson Sampling |
| `python/services/embedding_client.py` | DashScope 原生 Embedding 客户端 |
| `python/services/stream_token_markup_parser.py` | SSE token 级 `[COURSE:id:name]` 标记解析器 |
| `python/scripts/ingest_course_dataset.py` | CSV → MySQL + Milvus 数据导入流水线 |
| `frontend/src/pages/RecommendPage.tsx` | 推荐主界面 |
| `frontend/src/pages/MonitorPage.tsx` | 实验/指标仪表盘 |
| `frontend/src/components/StreamView.tsx` | SSE 流式推荐展示 |
