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
| 固定 Pipeline | 默认实验 `react_vs_pipeline` → `pipeline` 分组（50%） | `supervisor.recommend()` |
| ReAct 工具调用 | 默认实验 `react_vs_pipeline` → `react` 分组（50%） | `supervisor._react_recommend()` |

**路由机制**：`supervisor.recommend()` 与流式入口都调用 `ab_engine.assign(user_id, "react_vs_pipeline")`。`ab_test.py` 的 `assign()` / `assign_thompson()` 默认实验已改为 `react_vs_pipeline`（分组 `react` / `pipeline`，各 50%，按 user_id 一致性哈希分桶，同一用户始终落同一组）。返回 `group == "react"` 时走 `_react_recommend()`，否则走固定 Pipeline。`graph.py` 的 LangGraph 演示链路也用同一实验写 `experiment_group`。

> ⚠️ `rec_strategy` 实验仍在 `ab_test.py` 注册（分组 `control` / `treatment_llm`），但其 config（rerank: rule_based vs llm）**未被 pipeline 消费** —— 只作为 response 字段透传，不影响实际重排，是未来切换重排策略的占位实验。要真正切换重排方式，应在 RerankAgent 读取该 group 的 config。

ReAct 模式使用 7 个工具（`orchestrator/react_tools.py`）：`extract_profile`、`search_courses`、`filter_hard_constraints`（已锁定 —— 如 LLM 跳过，循环结束时会强制执行）、`semantic_filter_courses`、`rerank_courses`、`check_feasibility`、`generate_reasons`。最多 `max_rounds = 20` 轮 LLM 工具调用（同步与流式两条 `_react_recommend` 路径一致）。

### API 端点（`python/main.py`）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/recommend` | 同步推荐 —— Supervisor 主链路，按 A/B 自动分流 Pipeline / ReAct |
| `POST` | `/api/v1/recommend/stream` | SSE 流式（Pipeline 路径，`supervisor.stream_recommend`） |
| `POST` | `/api/v1/recommend/react` | 强制 ReAct 同步（`supervisor.react_recommend`，绕过 A/B 分流） |
| `POST` | `/api/v1/recommend/react/stream` | 强制 ReAct 流式 |
| `POST` | `/api/v1/recommend/graph` | LangGraph 演示链路（`rec_graph.ainvoke`），结果结构与主链路不同 |
| `GET` | `/api/v1/experiments` | 所有 A/B 实验状态 |
| `POST` | `/api/v1/experiments/{id}/outcome` | 记录实验结果 |
| `GET` | `/api/v1/metrics` | Agent / 业务指标 |
| `GET` | `/health`、`/api/v1/health` | MySQL / Redis / Milvus / LLM / Embedding 探活 |

> `/recommend` 随 A/B 分流；`/recommend/react*` 直接走 ReAct，可用来与 Pipeline 路径对照；`/recommend/graph` 仅展示 LangGraph 能力。

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
| Milvus `course_chunks_real` | 每门课 4 条向量，维度 1024 | 语义召回 |
| Redis | 候选课程 ID 列表（非完整对象） | 召回缓存（TTL 15 分钟） |

分块策略避免语义稀释 —— 例如"不考试、作业少"命中 `learning_profile` 块，不会被校区、地点等文本淹没。

### LLM 与 Embedding —— 统一走公司中转站 OpenAI 协议

LLM 与 Embedding 均通过公司内部中转站（`one.zhique.cn`）暴露为 OpenAI 兼容协议，共用同一套 `api_key` / `base_url`（`/v1`）。

| | LLM | Embedding |
|---|---|---|
| 端点 | `/v1/chat/completions`（OpenAI 兼容） | `/v1/embeddings`（OpenAI 兼容） |
| 客户端 | `ChatOpenAI` | `OpenAIEmbeddingClient`（`embedding_client.py`） |
| 模型 | `deepseek-v4-flash`（可配置） | `text-embedding-v4`（可配置，维度 1024） |

> 注：`settings.py` 中 `llm_model` 默认值为 `deepseek-v4-pro`，但 `python/.env` 实际配置为 `deepseek-v4-flash`；`embedding_base_url` 默认空字符串，实际值由 `.env` 的 `ECOM_EMBEDDING_BASE_URL` 提供（与 LLM 共用 `https://one.zhique.cn/v1`）。

- `ECOM_EMBEDDING_PROVIDER=openai` 走 `OpenAIEmbeddingClient`（默认）；`dashscope_multimodal` 仍保留为旧 DashScope 原生协议的兼容 provider，仅在直连灵积 MaaS 时使用。
- 中转站证书 SAN 不匹配时需 `ECOM_HTTPX_VERIFY_SSL=false`。
- 旧 MaaS 直连配置（`/compatible-mode/v1` + DashScope `/api/v1`）已废弃，不要再切回。

### LangSmith Tracing —— 三个 AOP 单点，零侵入全覆盖

**设计原则**：不侵入任何 Agent / Supervisor / Graph 代码，在工厂层和配置层实现 AOP 全覆盖。

| AOP 单点 | 文件 | 覆盖范围 |
|---------|------|---------|
| 配置激活层 | `python/services/tracing.py` | 启动时一次性把 `settings.langchain_*` 写入 `LANGCHAIN_*` + `LANGSMITH_*` 双命名空间 |
| LLM 工厂 | `python/services/llm_client.py` | 所有 LLM 调用走 `build_chat_openai` / `build_tool_calling_llm` → `ChatOpenAI` → 自动 trace |
| Embedding 工厂 | `python/services/embedding_client.py` | 底层委托 `langchain_openai.OpenAIEmbeddings` + `@traceable` 装饰 → 自动 trace |

**关键约束**：

- `configure_langsmith_tracing()` 在 `main.py` **模块最顶部**调用（在 `import orchestrator.supervisor` 之前），原因是 `langsmith.utils.get_env_var` 有 `lru_cache`，若在 env 就位前被读取，返回值会被永久冻结。`services/__init__.py` 顶层无 eager import langchain，此 import 链安全。
- 所有新增 LLM 功能**必须走工厂**，禁止直接 `ChatOpenAI(...)` 或裸 `httpx` 调 LLM/Embedding API。
- `get_settings()` 有 `lru_cache`，测试时直接 `monkeypatch.setenv` 不生效，需 mock `get_settings` 返回 fake settings（见 `tests/test_tracing.py`）。
- `/health` 暴露 `langsmith` 字段（`get_tracing_status()` 诊断是否激活），便于排查"为什么没有 trace"。

**v2.0.0 兼容**：deepagents 和 FastGPT MCP 接入后自动覆盖——
- deepagents（决策 3）：`create_deep_agent(model=工厂创建的 ChatOpenAI)` → 内部 LLM 调用走 `BaseChatModel` callback → 自动 trace。`create_agent` 还额外用 `@traceable` 装饰 middleware 钩子。
- FastGPT MCP（决策 8）：`langchain-mcp-adapters` 的 `load_mcp_tools` 把 MCP 工具转成 `StructuredTool` → `ToolNode` → 工具调用边界自动 trace。MCP 工具内部（FastGPT workflow 执行）是 TS 侧黑盒，已知边界。
- **Docker `--build` 陷阱**：改 `tracing.py`、`embedding_client.py` 或 `main.py` 后必须重建镜像，否则容器跑旧代码，tracing 不会生效。

## 文档与工作流

- **`docs/INDEX.md` 是文档总索引**。架构细节查 `docs/architecture.md`、`docs/code-walkthrough.md`、`docs/supervisor-main-orchestration.md`；本文件不重复这些深度内容。`docs/notes/` 是历轮任务复盘笔记（证据来源），`docs/llm-intern/` 是项目包装/真值边界层，`docs/interview-*.md` 是面试材料。
- **`docs/v2.0.0/` 是 v2.0.0 升级的工作区**。`plan.md` 是总计划（Phase 0-3 概要），`notes/2026-07-27-设计决策问答记录.md` + `notes/2026-07-28-设计决策补充说明.md` 是 15 个设计决策的问答记录与详细论证。**每次进入 plan 模式生成具体 Phase 阶段的 plan 时，必须先读 `docs/v2.0.0/plan.md` + `notes/` 对应决策，确保与已定决策一致**。
- **`openspec/` 是 spec-driven 变更工作流**。`openspec/specs/` 存当前规范，`openspec/changes/` 存变更提案（已合并的归档在 `changes/archive/`，如 `2026-05-28-fix-category-fuzzy-match`）。配套 Cursor 命令 `opsx-propose` / `opsx-apply` / `opsx-explore` / `opsx-archive`。改 spec 级行为前先看现有 spec。
- **`tasks/` 有 `todo.md`（待办）与 `lessons.md`（经验）**。`.cursor/rules/write-notes-for-project.mdc`（Cursor `alwaysApply`）要求每次对话读 `todo.md` 并把复盘写入 `docs/notes/` —— 这是 Cursor 端规则，Claude Code 默认不自动执行；需要同等行为时请明示。

## v2.0.0 工程深度要求（必须体现）

> 以下要求源自 `docs/v2.0.0/需求.md` 第 47-57 行，是 v2.0.0 区别于 v1.0.0 的核心深度指标。每个 Phase 的详细 plan 和实现都必须对照这些要求，确保项目能考察开发者的 agent 应用落地能力。

### Agent 端到端能力（所有涉及的 agent 都要体现）
1. **意图识别**：agent如何识别用户意图（推荐/报告/评价寄语/通用知识 Q&A/PPT 生成），路由到对应 tool/subagent。参考 claude-code `assembleToolPool` + LLM 推理路由。
2. **MCP 集成**：如何经 MCP 调用外部 TS 服务（FastGPT mcp_server）+ MCP 工具动态发现（`tools/list` + JSON Schema）。参考决策 8 补充。
3. **多轮对话记忆管理**：compaction（阈值 `contextWindow-13000`，保留 `keepRecentTokens=20000`）+ 结构化摘要（Goal/Progress/Key Decisions/Next Steps/Critical Context）+ checkpointing（Redis 后端，`thread_id` 恢复）。参考决策 11 补充。
4. **端到端 agent 评测**：如何评测 agent 端到端表现（意图识别准确率、工具调用成功率、检索召回率/精度、幻觉率、端到端延迟）。需设计评测指标与测试集。
5. **多 agent routing**：主 agent 如何在多 subagent/tool 间路由（`/chat` LLM 推理 + TodoWrite 规划）。参考决策 10 补充。
6. **monitor agent 在线表现利用**：如何利用 `/metrics`（v1 已有 Agent/业务指标）监控 agent 在线表现，发现退化/异常。参考 v1 `prometheus-client` + structlog。

### RAG 检索策略与数据指标
7. **检索策略细节体现具体数据指标**：召回率、精度、F1、语义缓存命中率、硬约束过滤率、rerank 排序质量（NDCG）、Milvus COSINE 融合权重效果。v1 已有部分（`_score_candidates` 广度 vs `_compute_score` 精度），v2 需扩展到 FastGPT KB Q&A 场景。
8. **工具调用出错优化**：检索不全/召回不好时如何优化（调整 top_k、语义缓存阈值、分块策略、embedding 模型、rerank 权重）。需有可观测的指标驱动调优，不是盲调。
9. **RAG 端到端质量维度与 phase 指标**：每个涉及 RAG 的 phase 必须围绕以下 6 个质量点建立可观测指标、声明问题并提供优化策略：① PDF 解析干净度（表格/公式/版式还原率、解析失败率）；② chunk 切分合理性（块大小分布、边界截断率、语义完整性，对比 v1 的 4 块策略 basic/schedule_capacity/learning_profile/audience_tags）；③ 检索能否找到关键内容（召回率/精度/Hit@k，对照 `_score_candidates` 广度 vs `_compute_score` 精度）；④ Rerank 延迟（P95 排序耗时 vs NDCG 增益，避免过高延迟拖垮流式输出）；⑤ Prompt 稳定输出（JSON 解析成功率、字段缺失率、重试次数，对照 FeasibilityAgent `_parse_advice_json` 静默兜底）；⑥ 答案证据可追踪（引用 chunk_id/来源页码回链、幻觉率）。指标驱动调优，不是盲调。

### Agent Harness 与 Loop 思想
10. **agent harness 包括 loop 一系列思想**：think→act→observe 循环、TodoWrite 规划、工具调用链路、subagent 委派/隔离、文件系统上下文卸载。参考 deepagents + claude-code/pi 源码（决策 3/4/7/11 补充）。
11. **工具调用链路断掉时的处理**：工具 try/catch→isError result → circuit breaker（3 次熔断）→ 部分结果保留（extractPartialResult）→ checkpointing 恢复 → 降级（如 KB 不可用走 Python 兜底脚本）。参考决策 12 补充。
12. **模型幻觉导致错误行动时的兜底**：确定性计算（统计/加权）用 Python 不用 LLM；LLM 只产文本段，数值引用文件不记忆；compaction 摘要落盘；subagent 上下文隔离。参考决策 5/11 补充。

### 多模态与插件扩展
13. **通用 agent 可加入图谱识别等多模态 LLM**：v2.0.0 通用知识 agent 可接入多模态 LLM（如图谱/图片识别），接入定制开发的插件（FastGPT 自定义 agent/KB）。
14. **PPT 生成系统（新增点）**：参考 OpenMAIC，围绕大学生课程小组 PPT 汇报场景，搭建 AI 生成 PPT 功能微课件自动生成系统（多 agent 协作，支持画布/动画/PPT，用户输入提示词选择类型如期末 PPT 课设/小组汇报）。参考 `E:\Agent\OpenMAIC` 的 `pptxgenjs` + DSL→PPTX 渲染管线。

### 数据源
15. **通用知识 agent 数据源**：`E:\Agent\multi-agent-course-system\广东工业大学2025年学生手册.pdf` 作为通用知识 Q&A 的种子数据源（经文档流水线摄入 FastGPT KB）。
16. **网页搜索 MCP 工具**：通用 agent 具有网页搜索这类 MCP 工具功能（`tavily-python`，已加 requirements）。

### 参考项目（E:\Agent\ 下）
- `E:\Agent\pi` —— agent harness/compaction/skills（TS，原生工具，无 MCP）
- `E:\Agent\claude-code` —— AgentTool/subagent/autoCompact/circuit breaker/MCPTool（TS，原生+MCP 混合）
- `E:\Agent\OpenMAIC` —— call_agent 委派/allowlist gate/PPTX 渲染（TS，Vercel AI SDK + pi-agent-core）
- `E:\Agent\FastGPT` —— mcp_server/KB/工作流编排/Code 节点（TS，MCP server+client）

## 常见陷阱

- **任何 Python 代码修改后 Docker 必须 `--build`** —— 镜像在构建时复制源码。
- **`.env` 加载顺序**：仓库根目录 `.env` → `python/.env`（后者覆盖前者）。Docker 仅注入 `python/.env`。如果两者都存在，根目录的值可能被静默覆盖。
- **MySQL 宿主机端口是 3307→3306**：宿主机连接 `localhost:3307`，容器内用 `mysql:3306`。
- **`ECOM_HTTPX_VERIFY_SSL=false`** 是必需的，当 MaaS 端点使用自定义域名证书且 SAN 不匹配时。
- **HardConstraintFilter 类别匹配是纯子串**：`"理工"` **不匹配** `"自然科学与工程技术"`。需要在 `student_profile_agent.py:190`（`category_rules`）和 `hard_constraint_filter.py:201`（`_fuzzy_text_match`）中添加别名映射。
- **FeasibilityAgent 的 LLM 调用失败是静默的**：`_parse_advice_json()` 解析失败时返回空 dict → 规则兜底，不抛异常。排查时搜索日志 `llm_advice_parse_empty` 或 `llm_advice_failed`。
- **FeasibilityAgent 最多送 12 门课给 LLM**（`max_tokens=4096`）。超过 12 门 → 仅走规则兜底。
- **语义缓存阈值是 0.95**（从 0.9 提高），因为 1024 维向量对句式模板相似但关键词不同的查询区分度不足。Prompt 始终参与缓存 key 计算。
- **无 CI/CD** —— 没有 `.github/workflows`。不要尝试 CI 命令。
- **前端无 lint/test/format 脚本** —— `npm run lint`、`npm test`、`npm run format` 都不存在。
- **`_score_candidates` 接受但不使用 `profile` 参数是有意为之**，不是 bug。
- **`pytest.ini` 启用了 `--strict-markers`** —— 使用未注册的 marker 会导致测试失败。注册的 marker：`unit`、`integration`、`slow`、`agent`、`api`；`asyncio_mode = auto`。
- **仓库根目录的旧 `docker-compose.yml` 是电商系统前身用的** —— 公选课系统请使用 `docker-compose.python.yml --profile python`。
- **`AGENTS.md` 已删除**（与 CLAUDE.md 内容重复，统一以 CLAUDE.md 为准）。

## 核心文件

| 文件 | 职责 |
|------|------|
| `python/main.py` | FastAPI 入口 —— 薄层，委托给 Supervisor |
| `python/config/settings.py` | 所有配置，`ECOM_` 前缀，先加载仓库根 `.env` 再加载 `python/.env` |
| `python/models/schemas.py` | Pydantic 模型：请求、响应、Course、StudentProfile、AgentResult |
| `python/orchestrator/supervisor.py` | 核心编排（约 940 行）—— Pipeline + ReAct 双模式 |
| `python/orchestrator/hard_constraint_filter.py` | 确定性硬约束过滤 |
| `python/orchestrator/react_tools.py` | 7 个 ReAct 工具定义 + `ReactToolExecutor` |
| `python/orchestrator/graph.py` | LangGraph 演示链路（`/api/v1/recommend/graph`），独立 StateGraph，不复用 Supervisor 主链路 |
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
| `python/services/llm_client.py` | LLM 工厂 `build_chat_openai` / `build_tool_calling_llm` —— 所有 LLM 调用唯一入口，LangSmith tracing 覆盖基座 |
| `python/services/tracing.py` | LangSmith 配置激活层 —— 启动时把 `settings.langchain_*` 映射为 `LANGCHAIN_*` + `LANGSMITH_*` 双命名空间 |
| `python/services/embedding_client.py` | Embedding 工厂 —— 底层委托 `OpenAIEmbeddings` + `@traceable`，自动被 LangSmith trace |
| `python/services/stream_token_markup_parser.py` | SSE token 级 `[COURSE:id:name]` 标记解析器 |
| `python/scripts/ingest_course_dataset.py` | CSV → MySQL + Milvus 数据导入流水线 |
| `frontend/src/pages/RecommendPage.tsx` | 推荐主界面 |
| `frontend/src/pages/MonitorPage.tsx` | 实验/指标仪表盘 |
| `frontend/src/components/StreamView.tsx` | SSE 流式推荐展示 |
