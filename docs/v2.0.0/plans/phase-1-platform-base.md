# Phase 1 详细计划：平台基座

> 本文件是 `../plan.md` Phase 1 的**详细实施计划**，承接 `notes/2026-07-28-设计决策补充说明.md` 决策 1/3/4/6/6b/7/8/9/11/12/13/14/15。Phase 0 已 GO（2026-07-29，deepagents 0.6.12 可用、中转站 tool-calling 双向兼容、Docker 构建通过），Phase 1 在此基座上搭建平台基座。
>
> 日期：2026-08-05
> 状态：待执行
> 门控属性：**非 go/no-go 门**（Phase 0 已过）——子项失败走降级回退，不阻塞整体。

> **当前执行修订（2026-08-08）**：本阶段以统一 deepagent 工厂、ToolRegistry、Python 本地文档解析/分块、v1 推荐 tool 包装和可测试的 `/documents/upload` 为验收范围。FastGPT、FastGPT MCP、FastGPT client、真实外部 KB 和 MySQL/Milvus 文档持久化不属于当前阶段验收条件，保留在后续阶段。

## 当前验证记录

- 已通过：统一 deepagent 场景工厂、ToolRegistry、异步 SQLite checkpointer、Skills/Memory backend 路由、v1 `recommend_courses` tool 委托、CSV 本地解析、确定性分块、`/api/v1/documents/upload` 本地 multipart 闭环。
- 已通过：`cd python; python -m pytest tests/ -m "not slow" -q`，结果为 `95 passed, 4 deselected`。
- 未纳入：FastGPT/MCP、真实 LLM 对话、外部 MySQL/Milvus 文档入库、报告/评价寄语/PPT 业务逻辑。

---

## 1. 目标与范围

### 1.1 目标（八条验证轴）

| # | 验证轴 | 验证什么 | 对应决策 |
|---|--------|---------|---------|
| A | **v1 不破** | `/recommend` 仍工作（curl 冒烟返回课程），v1 内部零改动 | 决策 4 |
| B | **v1 包装为 deepagents ReAct tool** | v1 的 7 个 ReAct 工具迁移为 `@tool`（执行逻辑复用 v1 Agent 实例），`recommend_courses` tool 用 `create_deep_agent` 编译为 deepagents ReAct agent，能完成 tool-calling 循环 | 决策 4/9 |
| C | **MinIO 双角色** | 共享 MinIO 实例（升级现有 minio 服务暴露端口），双桶 `source-documents` + `report-artifacts`，`storage/minio/minio_repo.py` 客户端封装可用 | 决策 6 |
| D | **文档流水线 Python 兜底** | `POST /api/v1/documents/upload` 实装：源文档存 MinIO → Python 解析（CSV/PDF/doc）→ 分块（v1 4 块 + generic_fixed 重写）→ 向量化入 Milvus `document_chunks` collection → 元数据入 MySQL `document_records`/`document_chunks` 表 | 决策 6/6b/13 |
| E | **FastGPT 部署能起** | docker-compose 加 5 个 FastGPT 服务（官方 ghcr.io 镜像，自带 mongo+pg+redis），健康检查绿，python-api `depends_on` healthy；Python 端不连真实 | 决策 6b/8 |
| F | **FastGPT client 封装骨架** | `tools/mcp_client.py`（MCP client，懒加载）+ `tools/fastgpt_kb_client.py`（HTTP admin client）封装就绪，单测 mock 验证接口；Phase 3 换 real | 决策 6b/8 |
| G | **ToolRegistry + 主 agent 骨架 + skills 技能目录** | `tools/registry.py`（启动注册内置 tool + MCP 懒加载 + allowlist）+ `tools/circuit_breaker.py`（熔断器）+ `skills/` 下 SKILL.md 技能文档 + `agent/main/` 包（`build_main_agent()` 工厂，传 `skills=["/skills/"]`，不接 `/chat`） | 决策 7/11/12 |
| H | **LangSmith tracing 覆盖** | 新增 5 个 `LLMTaskName` 枚举值，所有新 LLM 调用走工厂 + task_name | CLAUDE.md 硬约束 |

### 1.2 范围（Phase 1 刻意不做的事）

- **不**接 `/chat` 路由（主 agent 只写 `build_main_agent()` 工厂，不注册到 `main.py`）—— Phase 3
- **不**做 `query_knowledge` tool 的实际 Q&A 检索（依赖 `/chat`）—— Phase 3
- **不**做 compaction / checkpointing RedisSaver（只预留接口）—— Phase 3
- **不**做报告 / 评价寄语 agent（`/report` `/evaluation`）—— Phase 2
- **不**做 FastGPT 真实集成（后台初始化、KB 主链路摄入、MCP 真实连接）—— Phase 3
- **不**做 FastGPT 二次开发源码构建（Phase 1 用官方 ghcr.io 镜像，Phase 3 换二次开发源码构建）
- **不**做通用 chat 插件 tool 实装（`image_generate`/`code_interpreter`/`mindmap_generator` 只写骨架 + `NotImplementedError`）—— Phase 3/4
- **不**做前端
- **不**提 openspec change proposal（用户决定不提）

### 1.3 贯穿原则（Phase 1 即遵守，跨 Phase 持续）

1. **agent 编排 vs 能力分离**：`agent/` 只做编排（路由/委派/调度/对话管理），不持有具体能力实现。`tools/` 放原子能力（解析/分块/向量化/渲染/搜索/插件/注册层/熔断/MCP），以 `@tool` 装饰器 + Pydantic `args_schema` 暴露。`skills/` 放 SKILL.md 技能文档（deepagents SkillsMiddleware 自动加载的渐进式披露指令），每个技能一个子目录 + `SKILL.md`。`agent/documents/` 只留编排门面，`parser.py`/`chunker.py` 下放到 `tools/documents/`。
2. **deepagents 优先，FastGPT 拖拽并存**：Phase 1-2 先用 deepagents 框架编码实现。Phase 3 起引入 FastGPT 拖拽构建，作为同业务备选/增强。两者通过 feature flag 切换，不冲突。
3. **插件体系预留**：Phase 1 在 `tools/` 预留插件 tool 骨架（`image_generate`/`code_interpreter`/`mindmap_generator` = `NotImplementedError`），验证 ToolRegistry 扩展性。
4. **工具架构文档化**：每个 tool 独立 `.md` 说明文档，每个 skill 独立 `SKILL.md` 指令文档，Phase 1 结束时生成 `docs/v2.0.0/skills-tools-architecture.md`。

### 1.3 试金石（Definition of Done）

八条同时满足 = **Phase 1 GO**：

1. `/recommend` 仍工作（curl 冒烟返回课程，v1 内部零改动）
2. `documents/upload` 闭环（上传 CSV → MinIO 存原件 + MySQL/Milvus 入库 + 返回 `dataset_id`/`chunks_count`）
3. `build_main_agent()` 能编译（`create_deep_agent` 返回 `CompiledStateGraph`）+ 单测 mock tool 能 invoke
4. ToolRegistry 启动注册内置 tool + MCP 懒加载接口可用（单测 mock）
5. `recommend_courses` tool 能调 v1 Agent 完成 ReAct 循环（单测 mock LLM 验证 tool 调用链）
6. circuit breaker 单测（连续 3 次失败熔断 / 复位）
7. `docker compose up -d` 全服务起（python-api/mysql/redis/milvus/etcd/minio + 5 FastGPT 服务健康）
8. v1 回归 `tests/ -m "not slow"` 全绿（`test_supervisor_pipeline.py` 已删，无预存失败）

---

## 2. 风险与假设

### 2.1 已识别风险

| 风险 | 影响 | Phase 1 如何暴露 | 回退 |
|------|------|------------------|------|
| FastGPT 5 服务起不来（ghcr.io 镜像拉不动 / 健康检查不过） | python-api `depends_on` healthy 阻塞启动 | Step 1 docker-compose 升级 | compose 里 FastGPT 服务加 `profiles: [fastgpt]` 隔离（默认不起，Phase 3 再起），python-api `depends_on` 去掉 FastGPT |
| deepagents 主 agent 编译失败（版本漂移，Phase 0 是 0.6.12） | `build_main_agent()` 崩 | Step 4 | 锁定 `deepagents==0.6.12`（`requirements.txt` 改 pin） |
| `recommend_courses` tool 调 v1 Agent 失败（ReAct 循环超时 / tool-calling 不返回） | tool 不可用 | Step 3 + Step 5 单测 | tool 薄包装 `supervisor.react_recommend()` 而非 deepagents agent（降级为 v1 手写 loop） |
| MinIO 升级（暴露端口 + 改 access_key）破坏 milvus | milvus 起不来 | Step 1 + Step 7 | 新增独立 `python-minio` 服务（不动 milvus 依赖的 minio） |
| Milvus `document_chunks` collection 自动建失败（schema/索引冲突） | documents/upload 向量入库失败 | Step 5 | 改为脚本手动建（`scripts/init_document_collection.py`） |
| FastGPT 自带 mongo/pg 与现有 mysql/redis 端口冲突 | 服务起不来 | Step 1 | 端口映射错开（mongo 27017→27018，pg 5432→5433） |
| `langchain-mcp-adapters` 未安装（Phase 0 §7 已发现） | MCP client 封装 import 失败 | Step 2 | `pip install langchain-mcp-adapters` 补装（requirements 已列，venv 漏装） |

### 2.2 假设

- Phase 0 已验证 deepagents 0.6.12 + 中转站 tool-calling 双向兼容（前提成立）
- `python/.env` 已有可用 `LLM_*` / `EMBEDDING_*` / `MYSQL_*` / `MILVUS_*`（v1 已验证）
- FastGPT 官方 ghcr.io 镜像可拉取（或配 DaoCloud 镜像加速，Phase 0 已用）
- v1 `agent/recommend/` 下 5 个 Agent 类（`StudentProfileAgent` 等）可被 `@tool` 包装调用（`run()` 方法签名稳定）

---

## 3. 实施步骤

> 原则：**由外到内、逐层加变量**。先 docker 服务（外层），再 storage/client（中间层），再 tools（业务工具），再 agent（编排），最后 api（路由）。每步跑 `compileall` + `pytest`，出错可回滚单步。

### Step 1：docker-compose 升级（共享 MinIO + 5 FastGPT 服务）

**目标**：升级现有 `minio` 服务为共享实例（暴露端口 + 双桶），新增 5 个 FastGPT 服务（官方 ghcr.io 镜像，自带 mongo+pg+redis），配健康检查，python-api `depends_on` FastGPT healthy。

**改动文件**：`docker-compose.yml`

**改动点**：

1. **升级现有 `minio` 服务**（milvus 依赖 → 共享实例）：
   - 暴露端口 `9002:9002`（API）+ `9002:9002`（console）
   - `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` 从 `.env` 读（`MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY`，默认 `minioadmin`/`minioadmin`）
   - 加 healthcheck：`curl -f http://localhost:9002/minio/health/live` 或 TCP 探活
   - milvus 的 `MINIO_ADDRESS=minio:9002` 不变（共享实例）

2. **新增 5 个 FastGPT 服务**（官方 ghcr.io 镜像，Phase 1 不做二次开发源码构建）：
   - `fastgpt`：`ghcr.io/labring/fastgpt:v4.14.23`，端口 `3000:3000`，环境变量用 `x-share-db-config` + `x-app-env-config` + `x-service-env-config`（参考 `E:\Agent\FastGPT\docker-compose.yml`）
   - **存储后端**：Phase 1 用 FastGPT **自带 minio**（`fastgpt-minio` 服务），避免共享现有 minio 实例影响 FastGPT 或 Milvus。`STORAGE_S3_ENDPOINT` 指向 `fastgpt-minio:9002`。Phase 3 集成时再评估是否复用共享 minio。
   - > 对比方案：复用共享 minio（`minio:9002`）——被否掉，因为共享 minio 的 access_key 改动会同时影响 milvus 和 FastGPT，风险过大。
   - `fastgpt-mcp-server`：`ghcr.io/labring/fastgpt-mcp_server:v4.14.23`，端口 `3003:3000`，`FASTGPT_ENDPOINT=http://fastgpt:3000`
   - `fastgpt-mongo`：`mongo:6`，端口 `27017:27017`（或错开 `27018:27017` 避免宿主冲突），healthcheck `mongosh --eval 'db.runCommand({ping:1})'`
   - `fastgpt-pg`：`pgvector/pgvector:pg16`（自带 pgvector），端口 `5432:5432`（或错开 `5433:5432`），healthcheck `pg_isready`
   - `fastgpt-redis`：`redis:7-alpine`，端口 `6380:6379`（错开现有 redis 6379），healthcheck `redis-cli ping`

3. **python-api `depends_on`**：
   - 加 `fastgpt-mcp-server: condition: service_healthy`（用户选定）
   - 保留现有 `mysql`/`redis`/`milvus` 依赖

4. **环境变量**（FastGPT 服务用，Phase 1 只配占位，Phase 3 填真实）：
   - `x-default-root-psw` / `x-system-key` / `x-aes256-secret-key` 等（参考 FastGPT 官方 compose，用默认值或从 `.env` 读）

**验证点**：
- `docker compose up -d` 全服务起
- `docker compose ps` 全 healthy
- `curl http://localhost:8000/health` 仍返回 200（v1 不破）
- `curl http://localhost:3000` FastGPT 主服务可达（TCP 探活）
- `curl http://localhost:9002` MinIO console 可达

**回退**：FastGPT 服务起不来 → 加 `profiles: [fastgpt]` 隔离，python-api `depends_on` 去掉 FastGPT，Step 2-5 继续用 mock。

### Step 2：storage/client 封装层（MinIO + FastGPT client）

**目标**：写 MinIO 客户端封装 + FastGPT MCP client（放 tools/ 因为 MCP 是工具注册发现层）+ FastGPT HTTP admin client，均懒加载，单测 mock。

**新增文件**：

1. **`python/storage/minio/__init__.py`** + **`python/storage/minio/minio_repo.py`**：
   - `MinioRepository` 类：`ensure_bucket(bucket_name)` / `upload(bucket, path, data) -> object_path` / `download(bucket, path) -> bytes` / `presigned_url(bucket, path, expiry) -> str`
   - 启动时 `ensure_bucket("source-documents")` + `ensure_bucket("report-artifacts")`
   - 用 `minio>=7.2.0` 依赖
   - 配置从 `settings.minio_endpoint`/`minio_port`/`minio_access_key`/`minio_secret_key`/`minio_secure` 读

2. **`python/storage/fastgpt/__init__.py`** + **`python/storage/fastgpt/fastgpt_kb_client.py`**（放 storage/ 而非 tools/，因为是存储层客户端）：
   - `FastGPTKBClient` 类：`ingest(file_path, dataset_name, chunk_strategy) -> {dataset_id, chunks_count, status}` / `list_datasets() -> list` / `delete_dataset(dataset_id)`
   - 用 `httpx`，base_url 从 `settings.fastgpt_api_base` 读（默认 `http://localhost:3000/api`）
   - Phase 1 不连真实，单测 mock httpx
   - 注：决策 6b 的 HTTP admin API（KB 管理 upload/split/embed）走此 client

3. **`python/tools/mcp_client.py`**（MCP client，放 tools/ 因为 MCP 是工具注册发现层，对应 deepagents 的 ToolNode 扩展）：
   - `MCPClient` 类：`__init__(server_url_template, key)` 存配置不建连 / `connect() -> list[BaseTool]`（首次调 `MultiServerMCPClient` + `load_mcp_tools`，缓存连接）/ `is_connected() -> bool`
   - 用 `langchain-mcp-adapters` 的 `MultiServerMCPClient`，`transport="sse"`，url 从 `settings.fastgpt_mcp_url` 读（默认 `http://localhost:3003/{key}/sse`，`{key}` 占位运行时替换为 `settings.fastgpt_mcp_key`）
   - Phase 1 不连真实，单测 mock `MultiServerMCPClient`

**验证点**：
- `python -m compileall storage/ tools/mcp_client.py` 通过
- `python -m pytest tests/test_minio_repo.py tests/test_fastgpt_kb_client.py tests/test_mcp_client.py -v` 全绿（mock）

### Step 3：tools/ 迁移（v1 7 ReAct 工具 + recommend_courses tool + 内置 tool 骨架）

**目标**：v1 的 7 个 ReAct 工具迁移为 `@tool`（执行逻辑复用 v1 Agent 实例），`recommend_courses` tool 用 `create_deep_agent` 编译为 deepagents ReAct agent，其他内置 tool 写骨架。

**新增文件**：

1. **`python/tools/recommend/__init__.py`** + 7 个 `@tool` 文件：
   - `extract_profile.py`：`@tool` 包装 `runtime.supervisor.student_profile_agent.run()`
   - `search_courses.py`：`@tool` 包装 `runtime.supervisor.course_recall_agent.run()`（strategy: wide/refined）
   - `filter_hard_constraints.py`：`@tool` 包装 `runtime.supervisor.hard_constraint_filter.filter()`
   - `semantic_filter_courses.py`：`@tool` 包装 `runtime.supervisor._semantic_filter()`（或提取为公共方法）
   - `rerank_courses.py`：`@tool` 包装 `runtime.supervisor.course_rerank_agent.run()`
   - `check_feasibility.py`：`@tool` 包装 `runtime.supervisor.course_feasibility_agent.run()`
   - `generate_reasons.py`：`@tool` 包装 `runtime.supervisor.recommendation_reason_agent.run()`
   - 每个 `@tool` 用 Pydantic `args_schema`，LangChain 自动生成 JSON Schema
   - 执行逻辑复用 v1 Agent 实例（`runtime.supervisor.xxx_agent`），不重写

2. **`python/tools/recommend_courses.py`**：
   - `RecommendCoursesInput`（Pydantic）：`query: str` / `student_id: str` / `constraints: dict = {}` / `num_items: int = 10`
   - `RecommendCoursesOutput`（Pydantic）：`courses: list[Course]` / `warnings: list[str]` / `experiment_group: str`
   - `build_recommend_agent()`：`create_deep_agent(model=build_tool_calling_llm(...), tools=[7 个 @tool], system_prompt=REACT_SYSTEM_PROMPT)` → 返回 `CompiledStateGraph`
   - `recommend_courses(input: RecommendCoursesInput) -> RecommendCoursesOutput`：`@tool` 包装，调 `build_recommend_agent().invoke({"messages": [...]})`，映射结果
   - system_prompt 复用 v1 `REACT_SYSTEM_PROMPT`（`supervisor.py:840-847`）

3. **`python/tools/compute_weighted_grade.py`**：`@tool` 骨架（Phase 2 报告场景用，Phase 1 只写签名 + 占位实现）
4. **`python/tools/transcript_parser.py`**：`@tool` 骨架（Phase 2）
5. **`python/tools/report_renderer.py`**：`@tool` 骨架（Phase 2，Jinja2 + WeasyPrint）
6. **`python/tools/evaluation_generator.py`**：`@tool` 骨架（Phase 2）
7. **`python/tools/web_search.py`**：`@tool` 骨架（tavily，Phase 3 `/chat` 用）
8. **插件 tool 骨架**（Phase 3/4 通用 chat 插件，Phase 1 只写签名 + `NotImplementedError`，用于验证 ToolRegistry 扩展性）：
   - `python/tools/image_generate.py`：`image_generate` tool（图片生成，经 MCP 调图片生成服务）
   - `python/tools/code_interpreter.py`：`code_interpreter` tool（沙箱执行/代码生成）
   - `python/tools/mindmap_generator.py`：`mindmap_generator` tool（文本→思维导图 DSL→渲染）

**v1 兼容**：
- `agent/recommend/react_tools.py` + `supervisor._react_recommend()` 保留为 v1 兼容（`/recommend/react` 端点直达），标记 deprecated，Phase 2/3 清理
- v1 的 5 个 Agent 类 + Pipeline 路径零改动（决策 4）

**验证点**：
- `python -m compileall tools/` 通过
- `python -m pytest tests/test_recommend_courses_tool.py -v` 全绿（mock v1 Agent + mock LLM，验证 tool 调用链）

### Step 4：tools/ 注册层 + 主 agent 骨架 + skills/ 技能目录 + circuit breaker

**目标**：写 ToolRegistry（放 `tools/registry.py`，启动注册内置 tool + MCP 懒加载 + allowlist），主 agent 工厂（`agent/main/` 包，传 `skills=["/skills/"]` 让 SkillsMiddleware 自动加载技能文档，不接 `/chat`），circuit breaker 实装（放 `tools/circuit_breaker.py`），skills/ 技能目录（放 SKILL.md 文件供 SkillsMiddleware 注入 system prompt）。

**改动文件**：

1. **`python/tools/registry.py`**（ToolRegistry，从 skills/ 移到 tools/）：
   - `ToolRegistry` 类：
     - `register(tool: BaseTool)`：注册内置 tool
     - `register_mcp(server_url: str, key: str)`：存配置不建连（懒加载）
     - `get_all(allowed: list[str] | None = None) -> list[BaseTool]`：返回 tool 列表，按 allowlist 过滤；首次含 MCP tool 时调 `MCPClient.connect()` 建连 + `load_mcp_tools`（缓存）
     - `get_tool(name: str) -> BaseTool | None`
   - `runtime.init()` 里实例化 `tool_registry`，启动注册所有内置 `@tool`（Step 3 写的）
   - MCP client 懒加载：`register_mcp` 只存配置，首次 `get_all()` 含 MCP 时才建连
   - 移除 `skills/` 下的注册层概念：skills/ 只放 SKILL.md 文件，不做 Python 代码

2. **`python/tools/circuit_breaker.py`**（CircuitBreaker，从 skills/ 移到 tools/）：
   - `CircuitBreaker` 类：`failure_threshold=3` / `reset_timeout=60`（从 settings 读）
   - 状态：`closed` / `open` / `half_open`
   - `call(func, *args, **kwargs)`：包装 tool 调用，连续 `failure_threshold` 次失败 → `open`（拒绝调用），`reset_timeout` 后 `half_open`（试探），成功 → `closed`
   - 集成到 `ToolRegistry.get_tool()` 返回的 tool wrapper（tool 调用前过 circuit breaker）

3. **`python/skills/` 技能目录**（SKILL.md 文件，Phase 1 创建 2 个技能）：
   - `python/skills/recommend-courses/SKILL.md`：推荐课程技能，允许 all tools
     ```markdown
     ---
     name: recommend-courses
     description: 根据学生自然语言需求，完成公选课个性化推荐。当用户表达选课需求时使用。
     allowed_tools: [recommend_courses, extract_profile, search_courses, filter_hard_constraints, rerank_courses, check_feasibility, generate_reasons]
     ---
     ## 推荐课程流程
     1. 调 `recommend_courses` tool 传入 query（学生选课需求）
     2. tool 内部按 extract_profile → search_courses → filter_hard_constraints → rerank → check_feasibility → generate_reasons 顺序执行
     3. 返回推荐结果列表 + 推荐理由
     ```
   - `python/skills/document-ingestion/SKILL.md`：文档摄入技能
     ```markdown
     ---
     name: document-ingestion
     description: 上传文档到知识库，支持 CSV/PDF/doc 格式，自动分块向量化入库。当用户需要上传文档或导入数据时使用。
     allowed_tools: [read_file, write_file]
     ---
     ## 文档摄入流程
     1. 接收用户上传的文件
     2. 调 `/api/v1/documents/upload` 端点
     3. 文件经解析→分块→向量化→入库
     ```
   - `python/skills/__init__.py`：更新 docstring，说明 skills/ 是 SKILL.md 目录，非 Python 代码
   - `python/skills/README.md`：更新为 SKILL.md 说明

4. **`python/agent/main/__init__.py`** + **`python/agent/main/agent.py`** + **`python/agent/main/prompt.py`** + **`python/agent/main/subagents.py`**（subagent 工厂占位）：
   - `build_main_agent()`：`create_deep_agent(model=build_chat_openai(...), tools=runtime.tool_registry.get_all(), skills=["/skills/"], system_prompt=MAIN_AGENT_SYSTEM_PROMPT)` → 返回 `CompiledStateGraph`
     - 注意：`skills=["/skills/"]` 会在 Docker 容器内指向打包后的 skills 目录，SkillsMiddleware 自动扫描子目录 SKILL.md 加载到 system prompt
   - `MAIN_AGENT_SYSTEM_PROMPT`：Phase 1 简化（"你是公选课系统的主 agent，根据用户意图调用工具。如需多步规划，使用 TodoWrite 记录任务列表。"），在 prompt 中预留 `TodoWrite` 指令模板
   - `subagents.py`：subagent 工厂占位，返回 `CompiledStateGraph` 的 stub（`build_report_subagent()` / `build_evaluation_agent()` / `build_ppt_agent()`，Phase 2/3 实装）
   - 不注册到 `main.py`（Phase 3 接 `/chat`）
   - 单测 mock tool 验证 `build_main_agent()` 能编译 + invoke

**验证点**：
- `python -m compileall tools/registry.py tools/circuit_breaker.py agent/main/` 通过
- `python -m pytest tests/test_tool_registry.py tests/test_circuit_breaker.py tests/test_main_agent.py -v` 全绿
- `ls skills/recommend-courses/SKILL.md skills/document-ingestion/SKILL.md` 存在

### Step 5：documents/upload 实装 + LLMTaskName 扩展 + runtime 接入

**目标**：实装 `POST /api/v1/documents/upload` 端点（Python 兜底全链路 + FastGPT mock），扩展 LLMTaskName 枚举，runtime.init() 接入新单例。

**新增/改动文件**：

1. **`python/tools/documents/__init__.py`** + **`python/tools/documents/parser.py`** + **`python/tools/documents/chunker.py`**：
   - `parser.py`：CSV/PDF/doc 解析（重写，不依赖 v1 `ingest_course_dataset.py`）
   - `chunker.py`：v1 4 块策略（重写）+ generic_fixed（按字符/token 切，512 + 50 overlap）+ auto（按文件类型选）

2. **`python/agent/documents/__init__.py`** + **`python/agent/documents/service.py`**（编排门面，调 tools/ 中的能力）：
   - `DocumentIngestionService` 类（`service.py`）：`ingest(file: UploadFile, dataset_name: str, chunk_strategy: str) -> {dataset_id, chunks_count, status}`
     - 1. 存源文档到 MinIO `source-documents` 桶（`minio_repo.upload()`）
     - 2. Python 兜底解析（调 `tools/documents/parser.py`）
     - 3. 分块（调 `tools/documents/chunker.py`；`chunk_strategy` 参数选 `course_four_block`/`generic_fixed`/`auto`）
     - 4. 向量化（`ai/embedding_client.py`）+ 入 Milvus `document_chunks` collection（`storage/milvus/document_vector_repo.py`）
     - 5. 元数据入 MySQL `document_records`/`document_chunks` 表（`storage/mysql/document_repo.py`）
     - 6. FastGPT KB 摄入主链路：调 `FastGPTKBClient.ingest()`（Phase 1 mock，不连真实）
   - `agent/documents/` 只做编排门面，不持有能力实现

2. **`python/storage/milvus/document_vector_repo.py`**：
   - `DocumentVectorRepository` 类：`__init__` 检查 `document_chunks` collection 是否存在，不存在则创建（10 字段 schema：pk/id/vector/dataset_name/source_doc_name/chunk_type/chunk_index/content/page_number/created_at，COSINE + AUTOINDEX）
   - `upsert(chunks: list)` / `search(query_vector, dataset_name, top_k) -> list`
   - `runtime.init()` 里实例化（与 `CourseVectorRepository` 并列）

3. **`python/storage/mysql/document_repo.py`**：
   - `DocumentRepository` 类：`create_dataset(...)` / `create_chunks(...)` / `get_dataset(dataset_id)` / `list_datasets()`
   - SQLAlchemy 模型：`DocumentRecord` / `DocumentChunk` 两表
   - `sql/init-db.sql` 同步加建表语句

4. **`python/api/documents.py`**：
   - 实装 `@router.post("/api/v1/documents/upload")`
   - 接收 `multipart/form-data`（`file: UploadFile` / `dataset_name: str` / `chunk_strategy: str = "auto"`）
   - 调 `DocumentIngestionService.ingest()`
   - 返回 `{dataset_id, chunks_count, status}`

5. **`python/agent/main.py`**：
   - `include_router(documents.router)` 注册 documents 路由
   - 保留 `recommend`/`health` 路由

6. **`python/ai/llm_task_name.py`**：
   - 新增 8 个枚举值（Phase 1 用 5 个 + Phase 3 预留 3 个占位）：
     - `MAIN_AGENT_ROUTER`（Phase 1 主 agent 路由）
     - `RECOMMEND_COURSES_TOOL`（Phase 1 recommend_courses tool）
     - `DOCUMENTS_UPLOAD`（Phase 1 文档上传）
     - `TRANSCRIPT_PARSER`（Phase 2 成绩单解析）
     - `EVALUATION_GENERATOR`（Phase 2 评价寄语生成）
     - `MCP_TOOL_CALL`（预留 Phase 3 MCP 工具调用边界）
     - `FASTGPT_KB_INGEST`（预留 Phase 3 FastGPT KB 摄入）
     - `QUERY_KNOWLEDGE`（预留 Phase 3 通用知识检索）
   - 所有新 LLM 调用走 `build_chat_openai`/`build_tool_calling_llm` + `task_name`

7. **`python/agent/runtime.py`**：
   - `init()` 加：`tool_registry = ToolRegistry()` + 注册内置 tool + `register_mcp(...)` + `minio_repo = MinioRepository()` + `document_vector_repo = DocumentVectorRepository(...)` + `document_repo = DocumentRepository()` + `fastgpt_kb_client = FastGPTKBClient()`
   - 全局单例赋值
   - ToolRegistry/MCPClient/CircuitBreaker 从 `tools.registry`/`tools.mcp_client`/`tools.circuit_breaker` 导入（不再从 `skills/` 导入）

8. **`python/config/settings.py`**：
   - 新增 8 类配置项（见 §5.1）

**验证点**：
- `python -m compileall` 全通过
- `python -m pytest tests/ -m "not slow" -v` 全绿（含 8 个新测试）
- `curl -X POST http://localhost:8000/api/v1/documents/upload -F file=@xxx.csv -F dataset_name=test -F chunk_strategy=auto` 返回 `{dataset_id, chunks_count, status}`
- `curl http://localhost:8000/api/v1/recommend` 仍工作（v1 不破）

---

## 4. 判定矩阵

| 试金石 | 通过条件 | 状态 |
|--------|---------|------|
| 轴 A v1 不破 | `/recommend` curl 冒烟返回课程 | ⏳ 待验证 |
| 轴 B v1 包装为 deepagents ReAct tool | `recommend_courses` tool 单测 mock LLM 验证 tool 调用链 | ⏳ 待验证 |
| 轴 C MinIO 双角色 | `minio_repo` 上传/下载/presigned 单测 + 双桶 ensure_bucket | ⏳ 待验证 |
| 轴 D 文档流水线 Python 兜底 | `documents/upload` 闭环（CSV→MinIO+MySQL+Milvus） | ⏳ 待验证 |
| 轴 E FastGPT 部署能起 | 5 FastGPT 服务健康检查绿，python-api depends_on healthy | ⏳ 待验证 |
| 轴 F FastGPT client 封装骨架 | `tools/mcp_client.py` + `tools/fastgpt_kb_client.py` 单测 mock 全绿 | ⏳ 待验证 |
| 轴 G ToolRegistry + 主 agent 骨架 + skills 技能目录 | `tools/registry.py` + `tools/circuit_breaker.py` + `skills/` 下 SKILL.md 存在 + `build_main_agent()` 单测全绿 | ⏳ 待验证 |
| 轴 H LangSmith tracing 覆盖 | 5 新 LLMTaskName 枚举 + 所有新 LLM 调用走工厂 | ⏳ 待验证 |

**判定**：
- **八条同时通过 → Phase 1 GO**：在本文件标 ✅，更新 `../plan.md` Phase 1 状态，进入 Phase 2。
- **子项失败 → 降级回退**（见 §6），不阻塞整体，记录降级点，Phase 2/3 补。

---

## 5. 依赖与环境

### 5.1 settings.py 新增配置项（8 类，无前缀）

```python
# MinIO（共享实例）
minio_endpoint: str = "localhost"
minio_port: int = 9002
minio_access_key: str = "minioadmin"
minio_secret_key: str = "minioadmin"
minio_secure: bool = False
minio_source_bucket: str = "source-documents"
minio_report_bucket: str = "report-artifacts"

# FastGPT（Phase 1 占位，Phase 3 填真实）
fastgpt_api_base: str = "http://localhost:3000/api"
fastgpt_mcp_url: str = "http://localhost:3003/{key}/sse"
fastgpt_mcp_key: str = ""
fastgpt_root_psw: str = ""
fastgpt_system_key: str = ""

# Circuit breaker
circuit_breaker_failure_threshold: int = 3
circuit_breaker_reset_timeout: int = 60
```

同步 `.env.example` + `python/.env` 占位。

### 5.2 requirements.txt（已就绪，Phase 1 需补装）

Phase 0 §7 发现 `langchain-mcp-adapters` venv 未装（requirements 列了但没装上），Phase 1 Step 2 前补装：

```bash
pip install langchain-mcp-adapters
```

其余依赖（`deepagents`/`minio`/`jinja2`/`weasyprint`/`python-docx`/`pypdf`/`tavily-python`）requirements 已列，Step 1-5 按需验证装上。

### 5.3 文件清单

| 路径 | 动作 | 说明 |
|------|------|------|
| `docker-compose.yml` | 改 | Step 1：升级 minio + 加 5 FastGPT 服务 |
| `python/storage/minio/minio_repo.py` | 新增 | Step 2：MinIO 客户端封装 |
| `python/storage/fastgpt/fastgpt_kb_client.py` | 新增 | Step 2：FastGPT HTTP admin client |
| `python/tools/mcp_client.py` | 新增 | Step 2：MCP client（懒加载，放 tools/ 作为工具注册发现层） |
| `python/tools/recommend/*.py` | 新增 | Step 3：7 个 @tool 包装 v1 Agent |
| `python/tools/recommend_courses.py` | 新增 | Step 3：recommend_courses tool（deepagents ReAct agent） |
| `python/tools/compute_weighted_grade.py` 等 5 个 | 新增 | Step 3：内置 tool 骨架（Phase 2/3 用） |
| `python/tools/registry.py` | 新增 | Step 4：ToolRegistry（从 skills/ 移到 tools/） |
| `python/tools/circuit_breaker.py` | 新增 | Step 4：CircuitBreaker（从 skills/ 移到 tools/） |
| `python/skills/recommend-courses/SKILL.md` | 新增 | Step 4：推荐课程技能文档（deepagents SkillsMiddleware 自动加载） |
| `python/skills/document-ingestion/SKILL.md` | 新增 | Step 4：文档摄入技能文档 |
| `python/agent/main/{__init__,agent,prompt}.py` | 新增 | Step 4：主 agent 工厂（不接 /chat） |
| `python/tools/image_generate.py` | 新增 | Step 3：插件 tool 骨架（Phase 3/4，`NotImplementedError`） |
| `python/tools/code_interpreter.py` | 新增 | Step 3：插件 tool 骨架（Phase 3/4，`NotImplementedError`） |
| `python/tools/mindmap_generator.py` | 新增 | Step 3：插件 tool 骨架（Phase 3/4，`NotImplementedError`） |
| `python/tools/documents/{parser,chunker}.py` | 新增 | Step 5：文档解析+分块能力（下放至 tools/） |
| `python/agent/documents/service.py` | 新增 | Step 5：文档摄入编排门面（调 tools/ 能力） |
| `python/storage/milvus/document_vector_repo.py` | 新增 | Step 5：document_chunks collection |
| `python/storage/mysql/document_repo.py` | 新增 | Step 5：document_records/document_chunks 表 |
| `python/api/documents.py` | 改 | Step 5：实装 upload 路由 |
| `python/agent/main.py` | 改 | Step 5：include_router(documents) |
| `python/ai/llm_task_name.py` | 改 | Step 5：加 5 枚举值 |
| `python/agent/runtime.py` | 改 | Step 5：接入新单例 |
| `python/config/settings.py` | 改 | Step 5：加 8 类配置项 |
| `sql/init-db.sql` | 改 | Step 5：加 document_records/document_chunks 建表 |
| `python/tests/test_*.py` | 新增 8 个 | Step 5：8 个新测试文件 |
| v1 `agent/recommend/` 代码 | **不动** | 决策 4：v1 内部零改动（react_tools.py + _react_recommend 保留 deprecated） |

---

## 6. 回退策略（子项降级）

Phase 1 非 go/no-go 门，子项失败走降级回退，不阻塞整体：

| 子项失败 | 回退方案 | 影响 |
|---------|---------|------|
| FastGPT 5 服务起不来 | compose 加 `profiles: [fastgpt]` 隔离，python-api `depends_on` 去掉 FastGPT | Phase 1 FastGPT 部署验证轴 E 失败，client 封装仍写（mock），Phase 3 再起真实服务 |
| deepagents 主 agent 编译失败 | `requirements.txt` 锁 `deepagents==0.6.12` | 锁版本，重试 |
| `recommend_courses` tool 调 v1 Agent 失败 | tool 薄包装 `supervisor.react_recommend()`（v1 手写 loop）而非 deepagents agent | 降级为 v1 ReAct，丢失 deepagents 原生 loop（Phase 3 补） |
| MinIO 升级破坏 milvus | 新增独立 `python-minio` 服务（不动 milvus 依赖的 minio） | 多一个 minio 实例，资源增加 |
| Milvus `document_chunks` 自动建失败 | 改为 `scripts/init_document_collection.py` 脚本手动建 | 部署多一步 |
| `langchain-mcp-adapters` 未装 | `pip install` 补装 | 无影响 |

---

## 7. 与总 plan / 决策的衔接

- **本文件**：`docs/v2.0.0/plans/phase-1-platform-base.md`（用户指定放 `plans/`，与 Phase 0 详细计划同结构）
- **总 plan 引用**：`../plan.md` 第 58 行 `plans/phase-1-platform-base.md（待生成）` 应更新指向本文件 + 标状态
- **决策衔接**：
  - 决策 1/3：deepagents 主 agent 骨架（Step 4）
  - 决策 4/9：v1 包装为 deepagents ReAct tool（Step 3）
  - 决策 6/6b：MinIO 双角色 + 文档流水线 Python 兜底 + FastGPT client 封装骨架（Step 2/5）
  - 决策 7：ToolRegistry + 内置 tool + MCP-ready（Step 3/4）
  - 决策 8：MCP client 封装（Step 2，Phase 3 真实接入）
  - 决策 11/12：circuit breaker 实装 + tool try/catch + allowlist（Step 4）；compaction/checkpointing 推 Phase 3
  - 决策 13：`/api/v1/documents/upload` 端点（Step 5）
  - 决策 14：MySQL 富化（document_records/document_chunks 表，Step 5）
  - 决策 15：Phase 1 平台基座（本文件）
- **openspec**：用户决定**不提** openspec change proposal（偏离决策 15，记录在此）
- **后续 Phase**：GO 后生成 `phase-2-report-evaluation.md` 详细计划，再进 Phase 2 编码

### 7.1 Phase 1 范围切割决策（grill-me 沉淀）

| 项 | Phase 1 | Phase 2 | Phase 3 |
|----|---------|---------|---------|
| deepagents 主 agent 骨架 | ✅ `build_main_agent()` 工厂 | — | 接 `/chat` 路由 + 路由 prompt + compaction |
| ToolRegistry + 内置 tool | ✅ 注册 + allowlist | — | MCP 真实连接 |
| `recommend_courses` tool | ✅ deepagents ReAct agent | 报告 subagent 调用 | `/chat` 主 agent 调用 |
| MinIO 双角色 | ✅ 双桶 + client | 报告 artifact 存 report-artifacts | — |
| 文档流水线 | ✅ Python 兜底全链路 + FastGPT mock | — | FastGPT KB 主链路真实摄入 |
| FastGPT 部署 | ✅ 5 服务能起（不连真实） | — | 真实集成 + 后台初始化 + 二次开发源码构建 |
| `query_knowledge` tool | ❌ | — | ✅ Q&A 检索 |
| `/chat` 路由 | ❌ | — | ✅ |
| compaction/checkpointing | ❌（预留接口） | — | ✅ 实装 |
| circuit breaker | ✅ 实装 | — | — |
| 报告/评价寄语 agent | ❌ | ✅ | — |
| LLMTaskName 扩展 | ✅ 5 枚举值 | 补报告/评价枚举 | 补 chat/Q&A 枚举 |

### 7.2 Phase 3 后续补充内容（Phase 1 推迟项汇总）

> 本节集中列出 Phase 1 明确推迟到 Phase 3 的所有内容，作为 Phase 3 详细 plan 生成时的输入清单。Phase 2 不涉及这些项（Phase 2 只做报告+评价寄语场景）。

#### 7.2.1 FastGPT 真实集成（从 mock → real）

| 项 | Phase 1 状态 | Phase 3 待做 |
|----|-------------|-------------|
| FastGPT 镜像源 | 官方 ghcr.io 镜像（`ghcr.io/labring/fastgpt:v4.14.23` + `fastgpt-mcp_server:v4.14.23`） | 换二次开发源码构建（`E:\Agent\FastGPT` 源码，build context 指向或复制 dockerfile，pnpm install + bun build + Next.js build） |
| FastGPT 后台初始化 | 只配环境变量（root 密码/system key 占位） | 后台初始化脚本：登录 FastGPT UI → 创建 root 用户 → 创建 KB → 创建 app（simple/workflow/workflowTool）→ 生成 MCP key（绑定 app）→ 写入 `.env` 的 `FASTGPT_MCP_KEY` |
| MCP client 连接 | 懒加载接口 + 单测 mock（`tools/mcp_client.py`） | 真实连接：`MultiServerMCPClient` + `load_mcp_tools` 拉 FastGPT app 列表 → 转 LangChain `StructuredTool` → 注入 ToolRegistry |
| FastGPT KB 主链路摄入 | `FastGPTKBClient.ingest()` mock（`storage/fastgpt/fastgpt_kb_client.py`） | 真实调 FastGPT HTTP admin API（`/api/support/mcp/server/toolList` + `toolCall`，或 KB 管理 API upload/split/embed），`documents/upload` 主链路改走 FastGPT KB（Python 兜底降为备） |
| FastGPT KB 存储拓扑 | 待决（Phase 1 用 FastGPT 自带 mongo+pg，独立栈） | 评估是否复用现有 mysql/redis/milvus/minio（需侵入式改 FastGPT 配置/源码，决策 6b 待决项 2） |
| FastGPT 自定义 agent/KB 插件 | 不做 | 用户在 FastGPT 侧自建 agent/KB/插件，Python 主 agent 经 MCP 动态发现调用（决策 1 补充：FastGPT 既服务系统内置能力，也作用户自助创建平台） |
| FastGPT mcp_server SSE 规范 | 用旧 SSE 规范（已 deprecated） | 跟进 Streamable HTTP 新规范（2025-03-26，`Mcp-Session-Id` 会话管理） |

#### 7.2.2 `/chat` 主 agent 路由 + 通用知识 Q&A

| 项 | Phase 1 状态 | Phase 3 待做 |
|----|-------------|-------------|
| `/chat` 路由 | 不注册到 `main.py`（主 agent 只写 `build_main_agent()` 工厂） | `api/chat.py` 实装 + `main.py` `include_router(chat)`；请求 `{message, session_id, user_id}`，响应 SSE（token/tool_call/tool_result/final） |
| 主 agent 路由 prompt | 简化（"根据用户意图调用工具"） | 完整路由 prompt：推荐→`recommend_courses`；报告→委派 report subagent；评价寄语→委派 evaluation subagent；学校制度/科研/活动→`query_knowledge`；闲聊→直接回答；TodoWrite 规划多步，不确定时澄清（决策 10） |
| `query_knowledge` tool | 不做 | 实装 Q&A 检索：调 FastGPT KB-Q&A app（经 MCP 动态发现），返回答案 + 引用 chunk_id/来源页码（决策 6a/9 质量点⑥） |
| 通用知识种子数据 | 不做 | `广东工业大学2025年学生手册.pdf` 经文档流水线摄入 FastGPT KB（决策 15 数据源），作 `query_knowledge` 种子 |
| `web_search` tool | 骨架（`tools/web_search.py`，tavily） | 实装：tavily 网页搜索，主 agent 调用（决策 7/需求.md） |
| 会话隔离 | 不做 | 各端点独立 session（报告与评价寄语对话不共享，决策 5 重构）；`/chat` 用 `session_id` + checkpointing 恢复 |

**数据源清单**（main agent `query_knowledge` 检索源，均经文档流水线摄入 FastGPT KB）：

| 文件 | 大小 | 内容 | 角色 | 引入 |
|------|------|------|------|------|
| `广东工业大学2025年学生手册.pdf` | 5.3 MB | 学校制度/科研/活动/校规校纪 | 通用知识种子 | 决策 15 |
| `本科生中文成绩单(1860658).pdf` | 1.9 MB | 学生学业成绩表（2023秋-2026春，6 学期，148.5 学分，GPA 3.57，含课程名称/性质/学分/成绩） | 个人学业数据种子 | 2026-08-06 用户声明（本节新增） |

> ⚠️ 成绩单 PDF 是**个人学业数据**，非"通用知识"——它作为 main agent 可检索的知识库，回答"该生修了哪些课/某课成绩/平均绩点/某学期学分"等学业查询。与 `transcript_parser` tool（决策 14，解析 CSV 生成成绩单报告，Phase 2）是**不同场景**：这里是 KB 检索（Phase 3 `query_knowledge`，PDF 经分块向量化入 FastGPT KB），那里是结构化解析生成报告（CSV/Excel → 表格 → WeasyPrint PDF）。两者数据形态不同（PDF 检索 vs CSV 解析），不冲突，可并行存在。
>
> **摄入路径**（Phase 3 `query_knowledge` 实装时）：成绩单 PDF → `documents/upload` 端点（Phase 1 Step 5 已实装 Python 兜底链路）→ MinIO 存原件 → pypdf 解析文本 → 分块（`chunk_strategy=generic_fixed`，需处理表格版式，对照质量点①②）→ 向量化入 Milvus `document_chunks` collection → 元数据入 MySQL `document_records`/`document_chunks` → 同步入 FastGPT KB → main agent 经 MCP `query_knowledge` 检索。
>
> **Phase 1 衔接**：Phase 1 Step 5 的 `documents/upload` Python 兜底链路已能处理这个 PDF（pypdf 解析 + 分块 + 入库），可作为 Step 5 的真实测试数据（验证 PDF 解析干净度 + 表格版式还原率，质量点①）。但 `query_knowledge` 检索本身是 Phase 3。

#### 7.2.3 可靠性加固（compaction / checkpointing / 工具链路断裂兜底）

| 项 | Phase 1 状态 | Phase 3 待做 |
|----|-------------|-------------|
| compaction | 预留接口（不实装） | 实装：阈值 `context tokens > effectiveContextWindow - 13000`；保留最近 `keepRecentTokens=20000` tail；前面历史用 LLM 生成结构化摘要（Goal/Progress/Key Decisions/Next Steps/Critical Context）；摘要落盘，恢复时引用（决策 11） |
| checkpointing | 预留接口（不实装） | 实装：复用 v1 Redis 作 LangGraph checkpointer（自定义 `RedisSaver`，避免新增存储；备选 `SqliteSaver`）；`thread_id`（会话ID）→ 加载 checkpoint → 从中断点恢复；存 graph state（节点输出、工具调用、消息历史）（决策 12） |
| circuit breaker | ✅ Phase 1 实装（`tools/circuit_breaker.py`） | 集成到 deepagents tool 调用链路（Phase 1 是 ToolRegistry 层，Phase 3 扩展到 subagent 委派层） |
| 工具 try/catch → isError result | ✅ Phase 1 tool 函数内部 try/catch | 完整 pi/claude-code 模式：tool 失败 → isError result（不抛异常）→ agent 读 isError 决定重试/降级 |
| 部分结果保留（extractPartialResult） | 不做 | 长任务中断不丢进度（决策 12） |
| 权限门控（allowlist gate） | ✅ Phase 1 `get_all(allowed)` 接口 | 扩展到 subagent 委派层（参考 OpenMAIC，敏感操作门控） |
| 工具链路断裂兜底演示 | 不做 | 故意断工具（FastGPT KB 不可用）→ circuit breaker 熔断 → Python 兜底脚本 → 部分结果保留 → checkpointing 恢复 → 降级运行（决策 12/需求.md） |
| 幻觉兜底演示 | 不做 | LLM 试图自算统计 → schema 约束拦截 → 引用文件数值 → compaction 摘要落盘 → subagent 隔离（决策 5/11/需求.md） |

#### 7.2.4 其他 Phase 3 项

| 项 | Phase 1 状态 | Phase 3 待做 |
|----|-------------|-------------|
| TS MCP 桥接（pi/cc） | 只接 FastGPT 1 个 TS 服务 | 接 pi/cc 的 TS 服务（决策 8：v2 先接 1 个，后续扩展） |
| 多模态 LLM 接入 | 不做 | 通用 agent 加入图谱识别/图片识别（课程图谱可视化、成绩趋势图识别）（决策 13/需求.md） |
| 插件市场 | 不做 | 用户在 FastGPT 侧自建 agent/KB/插件，Python 主 agent 经 MCP 动态发现调用（决策 1 补充） |
| agent harness 深化 | 不做 | think→act→observe 循环可视化、工具调用链路追踪（OpenTelemetry）、subagent 委派树可视化、checkpointing 恢复演示（决策 10/需求.md） |
| LLMTaskName 枚举 | ✅ Phase 1 加 5 个（MAIN_AGENT_ROUTER/RECOMMEND_COURSES_TOOL/DOCUMENTS_UPLOAD/TRANSCRIPT_PARSER/EVALUATION_GENERATOR） | 补 chat/Q&A 枚举（CHAT_ROUTER/QUERY_KNOWLEDGE/WEB_SEARCH 等） |

#### 7.2.5 Phase 3 验证门控（预告）

Phase 3 GO 的试金石（Phase 3 详细 plan 生成时细化）：
1. `/chat` 路由正确（意图识别准确率达标）
2. MCP 调通 FastGPT app（`tools/list` + `tools/call` 双向）
3. compaction/circuit breaker 生效（长对话不崩 + 工具失败熔断）
4. PPT 生成可用（Phase 3 含 PPT 系统，参考 OpenMAIC）
5. 工具链路断裂兜底演示通过
6. 幻觉兜底演示通过

### 7.3 grill-me 关键决策记录

| # | 决策点 | 用户选择 |
|---|--------|---------|
| 1 | Phase 1 范围切割 | 聚焦基座+FastGPT 骨架（不接 /chat、不做 compaction/checkpointing、不做报告/评价 agent） |
| 2 | FastGPT 接入形态 | Phase 1 加精简 FastGPT 服务到 compose（5 服务，官方 ghcr.io 镜像） |
| 3 | MinIO 服务接入 | 升级现有 minio 为共享实例（暴露端口 + 双桶） |
| 4 | FastGPT KB 存储拓扑 | FastGPT 自带 mongo+pg（不复用现有 mysql/redis/milvus） |
| 5 | v1 subgraph 包装 | 包装为 deepagent 走 react（v1 7 工具迁为 @tool，执行逻辑复用 v1 Agent） |
| 6 | 工具迁移程度 | @tool 包装在 tools/，执行逻辑复用 v1 Agent（v1 react_tools.py + _react_recommend 保留 deprecated） |
| 7 | 主 agent 骨架程度 | 只写 `build_main_agent()` 工厂，不接 `/chat` |
| 8 | ToolRegistry 实例化 | 启动注册内置 tool，MCP 懒加载 |
| 9 | documents/upload 范围 | 实装 Python 兜底全链路 + FastGPT mock |
| 10 | chunk_strategy 选项 | 学生手册 PDF 推 Phase 3（/chat 通用 agent），Phase 1 课程 CSV 走 v1 4 块 |
| 11 | MinIO bucket 划分 | source-documents + report-artifacts 两桶 |
| 12 | MCP key 管理 | MCP key/url 从 .env 读 |
| 13 | 可靠性机制 Phase 1 | 额外实装 circuit breaker（compaction/checkpointing 推 Phase 3） |
| 14 | 主 agent 包位置 | `agent/main/` 包 |
| 15 | FastGPT compose 服务 | 5 服务：fastgpt/mcp/mongo/pg/redis |
| 16 | FastGPT 镜像源 | 官方 ghcr.io 镜像（Phase 3 换二次开发源码构建） |
| 17 | FastGPT 启动状态 | python-api depends_on FastGPT healthy |
| 18 | FastGPT 健康检查 | mongo/pg/redis 官方 healthcheck + fastgpt/mcp TCP 探活 |
| 19 | FastGPT 初始化 | Phase 1 只配环境变量，不做后台初始化 |
| 20 | v1 预存测试失败 | 已删测试用例，不用管 |
| 21 | LLMTaskName 扩展 | 新增 5 个枚举值 |
| 22 | Phase 1 验证门控 | 8 条试金石 |
| 23 | 实施顺序 | 5 步：docker→storage→tools→agent→api |
| 24 | 回退策略 | 子项降级回退 |
| 25 | settings 新增项 | 新增 8 类配置项 |
| 26 | documents 业务包 | `agent/documents/` 实装业务 |
| 27 | v1 4 块策略复用 | 重写分块逻辑（不依赖 ingest_course_dataset.py） |
| 28 | Milvus collection | 新建独立 document_chunks（不复用 course_chunks_real，通用文档非课程相关） |
| 29 | document_chunks schema | 10 字段 schema |
| 30 | collection 初始化 | 代码自动建 collection |
| 31 | MySQL 元数据表 | document_records + document_chunks 两表 |
| 32 | Phase 1 测试策略 | 8 个新测试文件 |
| 33 | openspec proposal | 不提 |

---

## 9. 数据库与建表（grill-me 沉淀）

> 本节承接用户要求：清空 `sql/init-db.sql` 电商遗留命名 + 清空所有 docker 数据卷 + 根据当前业务进展生成全新建表语句。grill-me 14 个子决策已沉淀。

### 9.1 数据库改名与密码联动

| 项 | 旧值（电商遗留） | 新值 | 同步改动文件 |
|----|------------------|------|-------------|
| 数据库名 | `ecommerce_ai` | `course_system` | `settings.py:47` / `docker-compose.yml`（`MYSQL_DATABASE` + `MYSQL_DATABASE`）/ `sql/init-db.sql`（`CREATE DATABASE` + `USE`） |
| root 密码 | `ecommerce123` | `123456` | `docker-compose.yml`（`MYSQL_ROOT_PASSWORD` + `MYSQL_PASSWORD` + healthcheck `-p`）/ `settings.py:46`（`mysql_password` 默认值） |
| 4 个电商遗留库 | `ecommerce_user`/`ecommerce_product`/`ecommerce_order`/`ecommerce_payment` | 删除 | `sql/init-db.sql`（只建 `course_system` 一个库） |

**settings.py 默认值**（本地裸跑与 docker 一致）：
```python
mysql_host: str = "localhost"
mysql_port: int = 3306
mysql_user: str = "root"
mysql_password: str = "123456"      # 旧 ecommerce123
mysql_database: str = "course_system"  # 旧 ecommerce_ai
```

### 9.2 init-db.sql 角色定位（source of truth）

**决策**：`init-db.sql` 是建表**唯一 source of truth**（含 `CREATE DATABASE` + `USE` + 全部 `CREATE TABLE`）。

**联动改动**：
- `python/storage/mysql/course_repo.py`：**删除 `ensure_schema()` 建表逻辑**（`CREATE TABLE` + `_add_column_if_missing` + `_add_index_if_missing` 全删），只保留 CRUD（`upsert_course`/`replace_course_chunks`/`fetch_courses`/`fetch_courses_by_ids`）
- `python/storage/mysql/document_repo.py`（新写）：**不写 `ensure_schema()`**，只写 CRUD（`create_dataset`/`create_chunks`/`get_dataset`/`list_datasets`）
- `python/scripts/ingest_course_dataset.py` + `python/scripts/backfill_milvus_vectors.py`：**删除 `course_repo.ensure_schema()` 调用**，保留导入逻辑（表由 `init-db.sql` 建，脚本只 INSERT）
- 表结构变更方式：`docker compose down -v && docker compose up -d --build`（重建 mysql 容器，重跑 init-db.sql）

**理由**：v1 建表语句重复在 `init-db.sql` + `ensure_schema()` 两处是技术债（易漂移）；统一为 `init-db.sql` 唯一 source；用户已决定清空所有数据卷重建，正好适配。

### 9.3 数据卷清理与重建

**执行命令**（Phase 1 Step 1 执行）：
```bash
# 1. 停服务 + 删所有数据卷
docker compose down -v

# 2. 手动确认删卷（down -v 已删，此处复核）
docker volume rm multi-agent-course-system_mysql_python_data \
  multi-agent-course-system_redis_python_data \
  multi-agent-course-system_milvus_data \
  multi-agent-course-system_minio_data \
  multi-agent-course-system_etcd_data 2>/dev/null || true

# 3. 重建（新库名/新密码/新表）
docker compose up -d --build

# 4. 重新导入课程数据（500 门 × 4 chunk）
cd python
python scripts/ingest_course_dataset.py
```

**清理影响**：
- mysql：新 `init-db.sql` 首次初始化（库名 `course_system`/密码 `123456`/4 表）
- milvus：重新建 collection（`course_chunks_real` + `document_chunks`，代码自动建）
- redis：清空（召回缓存/特征/A/B 实验内存重置）
- minio：重新建桶（`source-documents` + `report-artifacts`，`ensure_bucket` 幂等）
- etcd：milvus 元数据重置

### 9.4 全新 init-db.sql 内容

```sql
-- ============================================================
-- init-db.sql — 公选课系统 MySQL 初始化
-- 库名: course_system (密码: 123456,见 docker-compose.yml)
-- 表清单:
--   course_records   — v1 课程结构化数据(500 门公选课)
--   course_chunks    — v1 课程文本块(每课 4 块:basic/schedule_capacity/learning_profile/audience_tags)
--   document_records — v2 文档摄入 dataset 级元数据(源文档)
--   document_chunks  — v2 文档摄入 chunk 级元数据(分块)
-- source of truth: 本文件是建表唯一来源,代码层(course_repo/document_repo)不建表只 CRUD
-- 重建方式: docker compose down -v && docker compose up -d --build
-- 字符集: utf8mb4 / utf8mb4_unicode_ci
-- ============================================================

CREATE DATABASE IF NOT EXISTS course_system DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE course_system;

-- ------------------------------------------------------------ course_records
CREATE TABLE IF NOT EXISTS course_records (
    course_id VARCHAR(64) PRIMARY KEY,
    course_name VARCHAR(255) NOT NULL,
    teacher VARCHAR(128) DEFAULT '',
    credits DECIMAL(4,2) DEFAULT 0,
    course_type VARCHAR(64) DEFAULT '',
    course_category VARCHAR(128) DEFAULT '',
    domain VARCHAR(128) DEFAULT '',
    campus VARCHAR(64) DEFAULT '',
    time_slot VARCHAR(128) DEFAULT '',
    capacity INT DEFAULT 0,
    current_enrolled INT DEFAULT 0,
    popularity_level TINYINT DEFAULT 0,
    has_exam TINYINT DEFAULT 0,
    group_work_required TINYINT DEFAULT 0,
    tags TEXT,
    raw_json JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    search_text TEXT GENERATED ALWAYS AS (CONCAT_WS(' ', course_name, teacher, course_category, domain, campus, time_slot, tags)) STORED,
    FULLTEXT INDEX ft_search_text (search_text) WITH PARSER ngram,
    INDEX idx_domain (domain),
    INDEX idx_course_category (course_category),
    INDEX idx_campus (campus),
    INDEX idx_popularity_enrolled (popularity_level DESC, current_enrolled DESC, course_id ASC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------ course_chunks
CREATE TABLE IF NOT EXISTS course_chunks (
    chunk_id VARCHAR(128) PRIMARY KEY,
    course_id VARCHAR(64) NOT NULL,
    chunk_index INT NOT NULL,
    chunk_type VARCHAR(64) NOT NULL,
    content TEXT NOT NULL,
    metadata_json JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_course_chunks_course (course_id),
    INDEX idx_course_chunks_type (chunk_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------ document_records
CREATE TABLE IF NOT EXISTS document_records (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    dataset_id VARCHAR(64) NOT NULL UNIQUE,
    dataset_name VARCHAR(255) NOT NULL,
    source_doc_name VARCHAR(512) NOT NULL,
    storage_path VARCHAR(1024) NOT NULL,
    file_type VARCHAR(16) NOT NULL,
    file_size BIGINT DEFAULT 0,
    chunk_strategy VARCHAR(32) DEFAULT 'auto',
    chunks_count INT DEFAULT 0,
    status VARCHAR(16) DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_doc_records_dataset_name (dataset_name),
    INDEX idx_doc_records_status (status),
    INDEX idx_doc_records_created (created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------ document_chunks
CREATE TABLE IF NOT EXISTS document_chunks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    chunk_id VARCHAR(64) NOT NULL UNIQUE,
    dataset_id VARCHAR(64) NOT NULL,
    chunk_index INT NOT NULL,
    chunk_type VARCHAR(32) DEFAULT 'generic_fixed',
    content_preview VARCHAR(512) DEFAULT '',
    page_number INT DEFAULT 0,
    milvus_vector_id VARCHAR(128) DEFAULT '',
    content TEXT NOT NULL,
    metadata_json JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_doc_chunks_dataset (dataset_id),
    INDEX idx_doc_chunks_type (chunk_type),
    INDEX idx_doc_chunks_page (dataset_id, page_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 9.5 表结构说明

**course_records（v1 课程数据，schema 不动只迁位置）**：
- 决策 4 v1 内部零改动 → schema 保持 v1
- `search_text` 生成列 + `ft_search_text` FULLTEXT 索引：**保留**（`course_repo.fetch_courses()` 第 235 行用 `MATCH(search_text) AGAINST(... IN NATURAL LANGUAGE MODE)` 做关键词召回，query_text > 2 字符时走全文搜索，是 v1 召回链路实际依赖）
- 4 个普通索引：`idx_domain`/`idx_course_category`/`idx_campus`/`idx_popularity_enrolled`（v1 召回过滤用）

**course_chunks（v1 课程文本块，schema 不动只迁位置）**：
- v1 4 块策略：`chunk_type` ∈ {basic, schedule_capacity, learning_profile, audience_tags}
- 2 个普通索引：`idx_course_chunks_course`/`idx_course_chunks_type`
- **不加外键**（用户决定）：原 v1 `ensure_schema` 的 `fk_course_chunks_course` 外键删除，删 `course_records` 不级联删 `course_chunks`（数据一致性靠代码）

**document_records（v2 文档摄入 dataset 级，13 字段 + 3 索引）**：
- `id` 自增 PK + `dataset_id` UUID 业务唯一
- `dataset_name` 索引（按数据集名查）/ `status` 索引（按状态查）/ `created_at` 索引（按时间排序）
- `error_message` 记录摄入失败原因（`status=failed` 时填）
- `chunk_strategy` ∈ {v1_four_block, generic_fixed, auto}

**document_chunks（v2 文档摄入 chunk 级，12 字段 + 3 索引）**：
- `id` 自增 PK + `chunk_id` UUID 业务唯一
- `dataset_id` 普通索引（**不加外键**，用户决定；删 dataset 时代码手动删 chunks）
- `chunk_type` 索引（按分块类型查）
- `(dataset_id, page_number)` 复合索引（按页码回链，决策 9 质量点⑥证据可追踪）
- `content_preview` 存前 512 字符（列表预览不读全量）/ `content` 全量文本（检索/回显）
- `milvus_vector_id` 回链 Milvus 主键

### 9.6 不建表项（内存模式保留）

| 项 | 存储方式 | 是否建表 | 理由 |
|----|---------|---------|------|
| A/B 实验配置 | `ab_test.py` 内存（`self.experiments` dict + `_init_default_experiments()` 注册 `react_vs_pipeline`/`rec_strategy`） | ❌ 不建 | v1 内存模式，进程重启重置默认实验；Phase 4 评测增强时再考虑落盘 |
| A/B 实验指标 | `ab_test.py` 内存（`self._metrics` list） | ❌ 不建 | 同上 |
| Agent 指标 | `metrics.py` 内存（`defaultdict` + `list`） | ❌ 不建 | v1 内存模式，`/metrics` 端点读内存；Phase 4 接 Prometheus 时再考虑落盘 |
| 业务事件 | `metrics.py` 内存（`self._business_events` list） | ❌ 不建 | 同上 |

**init-db.sql 不加初始数据**（不 INSERT）：A/B 实验配置由代码内存注册，课程数据由 `ingest_course_dataset.py` 脚本导入。

### 9.7 grill-me 决策记录（数据库与建表）

| # | 决策点 | 用户选择 |
|---|--------|---------|
| 34 | 数据库名 | `course_system`（旧 `ecommerce_ai`） |
| 35 | 数据库密码 | `123456`（旧 `ecommerce123`） |
| 36 | init-db.sql 角色 | 含全部建表（`CREATE DATABASE` + `USE` + 4 表 `CREATE TABLE`） |
| 37 | ensure_schema 去留 | 删 `ensure_schema` 建表逻辑，只留 CRUD（`course_repo`/`document_repo` 都不建表） |
| 38 | 4 个电商遗留库 | 删除（只建 `course_system` 一个库） |
| 39 | v1 表 schema | 不动（决策 4 v1 内部零改动），只迁建表位置到 init-db.sql |
| 40 | document_records DDL | 13 字段 + 3 索引（id/dataset_id/dataset_name/source_doc_name/storage_path/file_type/file_size/chunk_strategy/chunks_count/status/error_message/created_at/updated_at） |
| 41 | document_chunks DDL | 12 字段 + 3 索引（id/chunk_id/dataset_id/chunk_index/chunk_type/content_preview/page_number/milvus_vector_id/content/metadata_json/created_at） |
| 42 | 字符集排序 | `utf8mb4` / `utf8mb4_unicode_ci`（与 v1 一致） |
| 43 | ab_test/metrics 表 | 不建（v1 内存模式保留，Phase 4 再考虑落盘） |
| 44 | init-db.sql 初始数据 | 不加（A/B 实验代码注册，课程数据脚本导入） |
| 45 | 数据卷清理 | `docker compose down -v` 全清 + 重建 |
| 46 | ingest 脚本适配 | 删 `ensure_schema` 调用，保留导入逻辑 |
| 47 | document_repo ensure_schema | 不写（只 CRUD，与 course_repo 一致） |
| 48 | settings.py 默认值 | `mysql_password='123456'` / `mysql_database='course_system'` |
| 49 | init-db.sql 注释 | 加文件头注释（库名/表清单/source of truth/重建方式） |
| 50 | 建表顺序与外键 | 不加外键（course_chunks/document_chunks 都用普通索引，删父表不级联） |
| 51 | search_text 生成列 | 保留（v1 `fetch_courses` 第 235 行 `MATCH...AGAINST` 实际依赖全文搜索） |

---

## 10. 执行 Checklist（数据库与建表）

### Step 0（前置）：数据卷清理与建表
- [ ] `docker compose down -v`（停服务 + 删所有数据卷）
- [ ] 重写 `sql/init-db.sql`（§9.4 全新内容：库名 `course_system` + 4 表 + 文件头注释）
- [ ] 改 `docker-compose.yml`（`MYSQL_DATABASE=course_system` + `MYSQL_ROOT_PASSWORD=123456` + `MYSQL_DATABASE=course_system` + `MYSQL_PASSWORD=123456` + healthcheck `-p123456`）
- [ ] 改 `python/config/settings.py`（`mysql_password='123456'` + `mysql_database='course_system'`）
- [ ] 改 `python/storage/mysql/course_repo.py`（删 `ensure_schema` 建表逻辑，只留 CRUD）
- [ ] 改 `python/scripts/ingest_course_dataset.py` + `backfill_milvus_vectors.py`（删 `ensure_schema` 调用）
- [ ] `docker compose up -d --build`（重建，mysql 首次跑新 init-db.sql）
- [ ] `cd python && python scripts/ingest_course_dataset.py`（重新导入课程数据）
- [ ] `curl http://localhost:8000/api/v1/recommend` 验证 v1 召回仍工作（新库 + 新表 + 重新导入数据）

### Step 1：docker-compose 升级（FastGPT + MinIO 共享）
- [ ] 升级现有 minio 服务（暴露 9002/9002 + access_key 从 .env 读 + healthcheck）
- [ ] 新增 5 FastGPT 服务（fastgpt/mcp-server/mongo/pg/redis，官方 ghcr.io 镜像）
- [ ] 配 FastGPT 健康检查（mongo/pg/redis 官方 + fastgpt/mcp TCP 探活）
- [ ] python-api depends_on fastgpt-mcp-server healthy
- [ ] `docker compose up -d` 全服务起 + healthy
- [ ] `curl /health` 仍 200（v1 不破）

### Step 2：storage/client 封装层
- [ ] `storage/minio/minio_repo.py`（MinioRepository：ensure_bucket/upload/download/presigned_url）
- [ ] `storage/fastgpt/fastgpt_kb_client.py`（FastGPTKBClient：ingest/list_datasets/delete_dataset）
- [ ] `tools/mcp_client.py`（MCPClient：懒加载 connect）
- [ ] 补装 `langchain-mcp-adapters`
- [ ] 3 个新测试文件（test_minio_repo/test_fastgpt_kb_client/test_mcp_client，mock）

### Step 3：tools/ 迁移
- [ ] `tools/recommend/` 7 个 @tool（extract_profile/search_courses/filter_hard_constraints/semantic_filter_courses/rerank_courses/check_feasibility/generate_reasons）
- [ ] `tools/recommend_courses.py`（build_recommend_agent + recommend_courses @tool）
- [ ] 5 个内置 tool 骨架（compute_weighted_grade/transcript_parser/report_renderer/evaluation_generator/web_search）
- [ ] v1 react_tools.py + _react_recommend 标 deprecated（保留兼容）
- [ ] test_recommend_courses_tool.py（mock v1 Agent + LLM）

### Step 4：tools/ 注册层 + 主 agent + skills/ 技能目录 + circuit breaker
- [ ] `tools/registry.py`（ToolRegistry：register/register_mcp/get_all(allowed)/get_tool）
- [ ] `tools/circuit_breaker.py`（CircuitBreaker：closed/open/half_open）
- [ ] `skills/recommend-courses/SKILL.md`（推荐课程技能文档）
- [ ] `skills/document-ingestion/SKILL.md`（文档摄入技能文档）
- [ ] `agent/main/` 包（build_main_agent 工厂，传 skills=["/skills/"]，不接 /chat）
- [ ] test_tool_registry.py / test_circuit_breaker.py / test_main_agent.py

### Step 5：documents/upload + LLMTaskName + runtime
- [ ] `tools/documents/` 包（parser.py/chunker.py，下放至 tools/ 层）
- [ ] `agent/documents/` 包（service.py 编排门面，调 tools/ 能力）
- [ ] `storage/milvus/document_vector_repo.py`（自动建 document_chunks collection，10 字段 schema）
- [ ] `storage/mysql/document_repo.py`（DocumentRecord/DocumentChunk 两表）
- [ ] `sql/init-db.sql` 加建表语句
- [ ] `api/documents.py` 实装 upload 路由
- [ ] `agent/main.py` include_router(documents)
- [ ] `ai/llm_task_name.py` 加 8 枚举值（5 个 Phase 1 用 + 3 个 Phase 3 预留占位）
- [ ] `agent/runtime.py` 接入新单例（tool_registry/minio_repo/document_vector_repo/document_repo/fastgpt_kb_client）
- [ ] `config/settings.py` 加 8 类配置项
- [ ] `.env.example` + `python/.env` 占位
- [ ] test_documents_upload.py（mock 全链路）

### 验证门控
- [ ] 轴 A：`curl /api/v1/recommend` 返回课程
- [ ] 轴 B：test_recommend_courses_tool 全绿
- [ ] 轴 C：test_minio_repo 全绿 + 双桶 ensure_bucket
- [ ] 轴 D：`curl /api/v1/documents/upload` 闭环（CSV→MinIO+MySQL+Milvus）
- [ ] 轴 E：5 FastGPT 服务健康检查绿
- [ ] 轴 F：test_mcp_client + test_fastgpt_kb_client 全绿
- [ ] 轴 G：test_tool_registry + test_circuit_breaker + test_main_agent 全绿 + skills/ 下 SKILL.md 存在
- [ ] 轴 H：8 新 LLMTaskName 枚举 + 新 LLM 调用走工厂
- [ ] `python -m pytest tests/ -m "not slow" -v` 全绿
- [ ] 同步更新 `CLAUDE.md` 架构章节、核心文件表、`agent/`/`skills/`/`tools/` README
- [ ] 生成 `docs/v2.0.0/skills-tools-architecture.md`（工具架构说明文档）
- [ ] 更新 `../plan.md` Phase 1 状态 → **GO**
