# 课程数据字段收敛与热度编码 - 执行清单

- [x] 检查当前仓库状态和字段影响面，确认不覆盖无关改动。
- [x] 修改课程数据生成脚本，删除旧来源/限制/history 明细字段，热度改为 0-4 数值编码，同名课程不再追加班级后缀。
- [x] 重新生成 `course_dataset_tools/output/public_elective_courses.csv`，确保输出 500 条新数据。
- [x] 同步 MySQL 初始化脚本与 Python 仓储层，`popularity_level` 使用 `TINYINT` 并以整数读写。
- [x] 同步 CSV 入库和 Milvus chunk 文本字段，保留 `avg_history_enrollment_ratio`，确保 `popularity_level=0` 不被跳过。
- [x] 同步 Course DTO、Agent 规则/prompt 与前端类型，删除已废弃字段，热度逻辑使用 int 编码。
- [x] 运行数据和测试验证，记录结果与后续首次启动/重新导入要求。

## Review

- 数据生成：`python course_dataset_tools\build_course_dataset.py` 成功生成 500 行 CSV。
- CSV 校验：行数为 500；`inference_note`、`data_source`、`source_visible_fields`、`major_limit`、`grade_limit`、`original_course_name`、`prerequisite`、`attendance_required`、逐年 `history_2023/2024/2025_*` 字段均不存在；`avg_history_enrollment_ratio` 保留；`popularity_level` 均为 `0-4`；未发现脚本生成的 `-N班` 后缀。
- 代码引用校验：全仓未发现已删除字段名残留。
- 语法验证：`python -m compileall "course_dataset_tools" "python\agents" "python\models" "python\repositories" "python\scripts"` 通过。
- 单元测试：`python -m pytest tests/ -m "not slow" -v` 在收集阶段失败，当前 Python 环境缺少项目依赖 `structlog`、`redis`、`langchain_core`，未进入测试执行。
- Lint：ReadLints 检查本轮编辑文件，未发现 linter 错误。
- 后续要求：首次启动新环境后需按新 schema 初始化 MySQL，并重新运行课程 CSV ingest 以刷新 MySQL `course_records/course_chunks` 和 Milvus chunk 向量；本轮未自动删库、删卷或删除 Milvus collection，也未运行真实 embedding 全量导入。

---

# 容器内导入前 50 门课程与推荐链路验证 - 执行清单

- [x] 核对 README、AGENTS、Compose、settings、导入脚本、Supervisor 和 Agent 日志模式，确认本轮只处理后端与容器内导入。
- [x] 验证 `python/.env` 中所需变量是否存在，不记录或输出密钥值。
- [x] 补充 Supervisor 关键阶段少量 `structlog` 日志，避免打印完整 prompt、密钥或逐课程/chunk 明细。
- [x] 运行 Python 语法或相关测试检查，确认日志改动没有破坏后端代码。
- [x] 建立或复用 `.venv`，安装 `python/requirements.txt` 依赖。
- [x] 使用 `docker compose -f docker-compose.python.yml --profile python up -d --build` 构建并启动后端相关容器。（本轮继续执行：已将 MySQL 宿主机端口改为 `3307` 后启动成功）
- [x] 验证 `python-api`、MySQL、Redis、Milvus 及依赖容器状态和近期日志。
- [x] 在 `python-api` 容器内执行 `python scripts/ingest_course_dataset.py --csv <容器内 course.csv 路径> --limit 50`。
- [x] 验证导入脚本输出本次处理 `courses=50`、`chunks=200`，并尽量用容器内 MySQL/Milvus 方式核对数量或连通性。
- [x] 请求 `/health` 与 `/api/v1/recommend`，查看新增 Supervisor 日志和现有链路日志。
- [x] 在本节 Review 记录已执行命令、结果、失败或风险。

## 本轮 Review

- 已阅读 `README.md`、`AGENTS.md`、`docker-compose.python.yml`、`docker-compose.python.pull-mirror.yml`、`python/config/settings.py`、`python/scripts/ingest_course_dataset.py`、`python/orchestrator/supervisor.py` 和相关 Agent，实现范围限定在后端。
- 已核对 `python/.env` 中 LLM、Embedding、Milvus 相关变量名存在；未在任务文档中记录任何密钥值。注意：`ECOM_HTTPX_VERIFY_SSL` 当前未显式配置，如后续真实 LLM/Embedding 调用出现证书校验错误，应按项目规则设为 `false` 后重建容器。
- 已修改 `python/orchestrator/supervisor.py`：新增 Phase 1、结构化补充召回、Phase 2、Phase 3 的阶段级 `structlog` 日志；启动日志不再记录 prompt 内容，只记录 `prompt_chars` 和 `context_keys`。
- 已执行 `python -m compileall "python/orchestrator/supervisor.py"`，通过。
- 已建立/复用 `.venv` 并执行 `.\.venv\Scripts\python -m pip install -r .\python\requirements.txt`，依赖安装成功。
- 已执行 `..\.venv\Scripts\python -m pytest tests/ -m "not slow" -v`，结果为 18 passed、1 deselected。
- 已尝试 `docker compose -f docker-compose.python.yml --profile python up -d --build`，失败于 Docker 拉取 `milvusdb/milvus:v2.4.6`：Docker 守护进程连接 `127.0.0.1:7890` 被拒绝。
- 已按 README 尝试镜像代理覆盖命令 `docker compose -f docker-compose.python.yml -f docker-compose.python.pull-mirror.yml --profile python up -d --build`，仍失败于拉取 `quay.io/coreos/etcd:v3.5.14`，根因同为 Docker 守护进程代理 `127.0.0.1:7890` 被拒绝。
- 已执行 `docker image ls --format "{{.Repository}}:{{.Tag}}"`，本机未列出可复用镜像，因此无法离线继续启动容器。
- 未完成：容器状态验证、`python-api` 容器内 `--limit 50` 导入、导入数量校验、`/health` 和 `/api/v1/recommend` 链路验证。解除阻塞方式：启动本机 `127.0.0.1:7890` 代理，或在 Docker Desktop 中移除/修正 daemon proxy/配置可用 registry mirror 后重新执行 Compose 构建启动。

## 本轮重试 Review（2026-05-16）

- 已先检查当前 Compose 和 Docker 容器状态：初始无运行中的项目服务或容器。
- 已重新执行 `docker compose -f docker-compose.python.yml --profile python up -d --build`；本轮未再出现 Docker daemon 代理 `127.0.0.1:7890` 拒绝连接问题，基础镜像拉取和 `python-api` 镜像构建均成功。
- Compose 在启动 MySQL 阶段失败：宿主机 `0.0.0.0:3306` 已被占用，错误为 `ports are not available: exposing port TCP 0.0.0.0:3306`。
- 已确认占用 `3306` 的本机监听进程为 `mysqld`（PID 8108）。当前 Compose 仅 `redis`、`minio`、`etcd` 处于运行/启动状态，`mysql`、`milvus`、`python-api` 尚未启动。
- 因 `python-api` 容器未运行，本轮未执行容器内 `--limit 50` CSV 导入、`courses=50/chunks=200` 校验、`/health` 与 `/api/v1/recommend` 验证，也未查看到新增 Supervisor 阶段日志。
- 下一步：释放或改配宿主机 `3306` 端口后重新运行 Compose；如不希望停止本机 MySQL，可改 Compose 的宿主端口映射但保持容器内 MySQL 连接不变。不要清库或删除卷。

## 本轮继续执行 Review（2026-05-16）

- 已按用户确认方案将 `docker-compose.python.yml` 中 MySQL 宿主机端口映射改为 `3307:3306`，容器内端口和 `python-api` 连接配置仍保持 `3306`。
- 已执行 `docker compose -f docker-compose.python.yml --profile python up -d --build`，构建使用缓存完成，`redis`、`minio`、`etcd`、`mysql`、`milvus`、`python-api` 均启动；MySQL 状态为 healthy，宿主机端口为 `3307->3306`。
- 已确认 `python-api` 镜像内没有 `/app/course_dataset_tools/output/course.csv`，因此已将宿主机 `course_dataset_tools/output/course.csv` 复制到容器 `/tmp/course.csv`。
- 已在 `python-api` 容器内执行 `python scripts/ingest_course_dataset.py --csv /tmp/course.csv --limit 50`，但导入失败，未得到 `courses=50`、`chunks=200` 输出。
- 导入失败的明确错误：MySQL 执行 `ALTER TABLE course_records ADD COLUMN IF NOT EXISTS has_exam TINYINT DEFAULT 0` 返回 1064 语法错误；失败发生在 `CourseRepository.ensure_schema()` 阶段。
- 已查询容器内 MySQL 当前计数：`course_records=0`，`course_chunks=0`；本轮未完成前 50 门课程导入。
- `/health` 返回 200，状态为 healthy，依赖检查显示 `mysql=true`、`redis=true`、`milvus=true`。
- `/api/v1/recommend` 返回 200，并返回 2 门课程；但由于数据库计数为 0 且日志显示召回策略包含 `fallback_mock`，该结果不能证明课程 CSV 已导入。
- `python-api` 日志中已看到 `course_supervisor.start`、`course_supervisor.phase1_complete`、`course_supervisor.phase2_complete`、`course_supervisor.phase3_complete`、`course_supervisor.complete`。
- 日志中同时出现外部调用问题：Embedding 向量搜索因 MaaS 域名证书 hostname mismatch 失败，`student_profile` 与 `recommendation_reason` 均为 `Connection error.`；这与项目规则中 `ECOM_HTTPX_VERIFY_SSL=false` 的要求一致，但本轮未修改 `.env`。
- ReadLints 检查本轮编辑文件时仅报告 `tasks/todo.md` 已存在的 Markdown 多个一级标题警告，未改动文档结构。

## 导入阻塞修复 Review（2026-05-16）

- 根因：`CourseRepository.ensure_schema()` 使用 `ALTER TABLE course_records ADD COLUMN IF NOT EXISTS ...`，目标 MySQL `8.0.46` 对该语法返回 1064，导致导入在建表兼容检查阶段中断。
- 修改：已将 `python/repositories/course_repository.py` 的加列逻辑改为先查询 `information_schema.COLUMNS`，列不存在时再执行 `ALTER TABLE ... ADD COLUMN ...`；保持幂等，仅处理 `has_exam`、`group_work_required` 两列。
- 配置：`python-api` 容器内第一次重试已越过 MySQL DDL，但 embedding API 因 MaaS 域名证书校验失败中断；按项目规则为 `python/.env` 补充非密钥配置 `ECOM_HTTPX_VERIFY_SSL=false`，未输出任何密钥。
- 验证：已执行 `python -m compileall -q "python/repositories/course_repository.py" "python/scripts/ingest_course_dataset.py"`，通过；`ReadLints` 检查 `python/repositories/course_repository.py` 无 linter 错误。
- 构建：已执行 `docker compose -f docker-compose.python.yml --profile python up -d --build`，`redis`、`minio`、`etcd`、`mysql`、`milvus`、`python-api` 均运行；MySQL 为 healthy，宿主机端口映射为 `3307->3306`。
- 导入：重建容器后 `/tmp/course.csv` 丢失，已重新从 `course_dataset_tools/output/course.csv` 复制到 `python-api:/tmp/course.csv`；最终在容器内执行 `python scripts/ingest_course_dataset.py --csv /tmp/course.csv --limit 50` 成功，stdout 返回 `courses=50`、`chunks=200`、`status=ok`。
- 结果：MySQL 当前计数为 `course_records=50`、`course_chunks=200`；Milvus collection `course_chunks_real` 当前 `num_entities=225`。Milvus 数量高于 200 是因为此前失败重试期间已成功写入过部分向量，本轮未按约束清库或删除数据。
- 剩余风险：embedding 外部 API 曾出现一次 `UNEXPECTED_EOF_WHILE_READING`，随后不改代码重试成功；若后续全量 500 门导入，可关注外部 API 稳定性或补充重试策略。

---

# Milvus 多余课程向量清理 - 执行清单

- [x] 确认 `course_chunks_real` collection、`chunk_id` 主键、MySQL `course_chunks.chunk_id` 保留集合和 Milvus delete/query 能力。
- [x] 从 MySQL 读取当前 200 个 `chunk_id`，从 Milvus 读取当前所有 `chunk_id`，计算只存在于 Milvus 的多余向量。
- [x] 使用 Milvus 主键 `chunk_id in [...]` 定向删除多余向量，不清空 MySQL，不删除成功导入的 200 个 chunk 向量。
- [x] 删除后执行 `flush`/等待一致性，并验证 Milvus 剩余 `chunk_id` 与 MySQL 200 个 `chunk_id` 完全一致。
- [x] 请求 `/health` 确认 Milvus 仍可用。
- [x] 在本节 Review 记录清理方式、删除数量、最终数量和风险。

## 本轮 Review（2026-05-16）

- 代码确认：`CourseVectorRepository` 使用 `settings.course_milvus_collection=course_chunks_real`，Milvus schema 中 `chunk_id` 为 VARCHAR 主键，字段包含 `course_id`、`chunk_type`、`embedding`；导入逻辑通过 `upsert_chunks()` 写入并 `flush()`。
- 保留集合：容器内 MySQL 校验为 `course_records=50`、`course_chunks=200`，以当前 `course_chunks.chunk_id` 作为唯一保留集合；本轮未对 MySQL 执行任何删除、清表或重建。
- 初次清理：从 Milvus 查询到可见 `chunk_id` 唯一集合已与 MySQL 200 个 `chunk_id` 完全一致，`extra_before=0`，因此没有可用 `chunk_id in [...]` 安全定向删除的异名多余向量。
- 数量差异原因：Milvus `num_entities` 为 223，但 query 可见行数为 200，判断剩余差异来自失败重试/upsert 期间留下的同主键旧版本或未压实段；直接按 `chunk_id` 删除会误删当前有效向量。
- 最终清理方式：从当前有效的 200 条 Milvus 记录读取 `chunk_id/course_id/chunk_type/embedding`，创建临时 collection 校验 `num_entities=200` 后，将原 `course_chunks_real` 重命名为备份、临时 collection 重命名回 `course_chunks_real`，验证通过后删除备份；未重新调用 embedding API。
- 清理结果：源 collection `num_entities=223`，有效向量 200 条，重建后 `course_chunks_real num_entities=200`、query 行数 200，剩余 `chunk_id` 与 MySQL 200 个 `chunk_id` 完全一致，清除了 23 条陈旧实体统计对应的残留。
- 健康检查：`GET /health` 返回 `status=healthy`，依赖项 `mysql=true`、`redis=true`、`milvus=true`。
- 风险：本轮使用的是 PyMilvus ORM API，命令输出有 deprecation warning，但不影响执行结果；重建期间 collection 名称有短暂切换窗口，最终已验证同名 collection 可用且备份已删除。

---

# 前端 Vite / Node 兼容性（2026-05-17）

- [x] 确认报错：Node 20.17.0 不满足 Vite 8 的 engines；Rolldown 原生绑定 `@rolldown/binding-win32-x64-msvc` 缺失。
- [x] 将 `frontend/package.json` 中 `vite` 固定为 **`^6.4.2`**（兼容 Node ^20 全系列），补充 `engines.node`。
- [x] 删除 `frontend/node_modules` 与 `package-lock.json` 后重新 `npm install`，消除 Vite 8 残留。
- [x] 验证 `npm run build` 成功。

## 本轮 Review（2026-05-17）

- 详见 `docs/notes/2026-05-17-frontend-vite-node-rolldown.md`。备选方案为升级 Node 至 ≥20.19 或 ≥22.12 后继续用 Vite 8。

---

# Docker 启动与流式推荐验证（2026-05-18）

- [x] `docker compose -f docker-compose.python.yml --profile python up -d --build` 启动依赖与 python-api；MySQL 宿主端口 `3307:3306`。
- [x] 核对 `python/.env` 含 `ECOM_HTTPX_VERIFY_SSL=false`（未记录密钥）。
- [x] `GET /health`：`deps` 全为 true。
- [x] `POST /api/v1/recommend`：200，全链路成功；日志含 `hard_constraint_filter.done`、`course_supervisor.phase15_complete`。
- [x] `POST /api/v1/stream_recommend`：修复路由与 Phase3 参数/超时后 200；SSE 含 `phase15_complete`、token 流、`phase3_complete`、`done`。
- [x] 单元测试：`pytest python/tests/test_stream_recommend.py` 5 passed。

## 本轮 Review

- 流式路径：注册表实际为 `/api/v1/recommend/stream`；已为 `/api/v1/stream_recommend` 增加别名（`main.py`）。
- Phase3 报错：`astream_reasons` 形参为 `profile`，编排器误传 `student_profile=`，已改为 `profile=`（`supervisor.py`）。
- 流式超时：`stream_timeout_seconds` 原从整次请求计时，Phase3 开始前已超过 60s 会误触发 `STREAM_TIMEOUT`；改为从 Phase3 流开始后计时（`supervisor.py`）。
- 验证记录详见 `docs/notes/2026-05-18-docker-stream-recommend-phase15.md`。

---

## 面试文档体系重构（2026-05-20）

- [x] 读取并梳理 `docs/architecture.md`、`docs/code-walkthrough.md`、`docs/interview-guide.md`、`docs/project-plan.md`、`docs/resume-template.md` 的现状与重复内容。
- [x] 设计重构后的文档分工：面试主入口、STAR 故事库、追问题库、架构讲法、代码证据链、Legacy 历史参考。
- [x] 编辑目标文档并按需新增索引/素材文档，确保中文表达聚焦“为什么、我改了什么、如何验证、可追问点”。
- [x] 执行轻量 Markdown 格式与链接检查，并用 ReadLints 检查编辑过的文档。
- [x] 在 `tasks/todo.md` 记录本轮 Review。
- [x] 在 `docs/notes/` 新增本次文档重构复盘笔记。

### 面试文档重构 Review

- 已重构 5 个目标文档：`docs/interview-guide.md` 改为面试准备主入口；`docs/resume-template.md` 收敛为简历 bullet 与口播模板；`docs/architecture.md` 保留架构事实并补充设计取舍/可追问点；`docs/code-walkthrough.md` 改为从入口到 Agent/召回/硬约束/流式输出的代码证据链；`docs/project-plan.md` 明确标注为 Legacy 电商历史规划。
- 已新增 3 个文档：`docs/INDEX.md`、`docs/interview-star-stories.md`、`docs/interview-question-bank.md`，用于减少 STAR、追问和简历内容在多个文档间重复。
- 已参考必要复盘材料：容器导入与链路验证、硬/软约束分离、流式推荐验证、Redis 缓存与硬约束排查改进；未搬空 `docs/notes`，保留时间线复盘。
- 验证：`ReadLints` 检查本轮编辑的 8 个 docs 文档已无 markdownlint 警告；`tasks/todo.md` 仍有历史多 H1 与重复 Review 警告，未为本轮任务重构整个任务文件。
- 验证：使用 `rg "\[[^\]]+\]\([^)]+\)" docs --glob "*.md"` 检查 Markdown 链接写法，未发现本轮根目录文档中的 Markdown 链接；当前文档间引用主要使用代码样式路径。
- 验证：使用 `rg "^\|---|^\|----|^### 代码承担的职责$|^### 支撑的面试故事$" docs --glob "*.md"` 复查后，匹配仅来自既有 `docs/notes` 历史复盘，未命中本轮编辑的根目录文档。
- 未完成/风险：原计划尝试用 Python 脚本做更完整的本地链接解析，但两次被 PowerShell 引号转义影响，未采用该结果；本轮改用 `rg` 轻量检查。未运行业务代码测试，因为本次只改 Markdown 文档。

---

## Supervisor 主链路编排文档（2026-05-20）

- [x] 读取 `tasks/todo.md` 和项目复盘技能要求，确认本轮只做文档任务。
- [x] 阅读 `python/orchestrator/supervisor.py`、`python/orchestrator/hard_constraint_filter.py`、`python/main.py`、5 个 Agent、流式 token parser、LangGraph 示例和既有架构/面试文档。
- [x] 新增 `docs/supervisor-main-orchestration.md`，集中说明 Supervisor 主链路流程、原理、降级、LangChain/LangGraph 边界和面试 STAR 讲法。
- [x] 新增 `docs/notes/2026-05-20-supervisor-main-orchestration.md`，记录本轮文档任务复盘。
- [x] 执行 ReadLints 和 Markdown 轻量只读检查，记录验证结果。
- [x] 按用户反馈重构 `docs/supervisor-main-orchestration.md`：删除面试 STAR、LangChain/LangGraph 边界和老接口输出说明，改为流式接口工程细节文档。

### 本轮 Review

- 已确认生产推荐主路径是 `SupervisorOrchestrator`：`/api/v1/recommend` 调用 `recommend()`，`/api/v1/recommend/stream` 调用 `stream_recommend()`；`/api/v1/recommend/graph` 是 LangGraph 展示接口，不是同步/流式主路径。
- 已按阶段梳理主链路：Phase 1 画像与宽召回并行，画像成功后二次精召回；Phase 1.5 在重排前做确定性硬约束过滤；Phase 2 重排与可行性并行；Phase 3 串行生成推荐理由，流式路径用 marker parser 拆 token。
- 文档中已补充错误处理和降级边界：Agent fallback、LLM JSON 失败、Redis/Milvus/Embedding 失败、空候选、硬约束过严、数量不足和流式超时。
- 文档中已按 STAR 思路补充 60-90 秒口播、2-3 分钟展开版、追问回答和避免“报菜名”替换表。
- 验证：ReadLints 检查两份新增文档无 Markdown 诊断；只读搜索确认 `docs/supervisor-main-orchestration.md` 标题结构完整；两份新增文档未发现 Markdown 链接写法。
- 验证：ReadLints 仍报告 `tasks/todo.md` 历史多 H1 和重复 Review 标题警告，本轮仅追加任务记录，未重构历史任务文件。
- 本轮未修改业务代码，未提交 git commit，新增文件控制为 2 个。
- 用户反馈后已重写主文档为流式接口工程细节版，重点补充请求字段转换、召回缓存 key、Redis 精确/语义缓存、MySQL 结构化召回、Milvus chunk 召回、候选合并、召回初始打分公式、二次精召回、硬过滤规则、重排规则分、可行性 warning、Phase 3 marker parser、SSE 事件和 `done` 收口。
- 验证：ReadLints 检查 `docs/supervisor-main-orchestration.md` 无 Markdown 诊断；搜索确认主文档无 `STAR`、`LangChain`、`LangGraph`、`面试`、`报菜名`、`自测`、`老接口` 等残留表述。

---

## 流式编排架构问答与 note 沉淀（2026-05-20）

- [x] 澄清「没有结构化条件」、精确缓存 vs 语义缓存、前端 query/prompt 字段含义。
- [x] 说明 HardConstraintFilter 与 CourseFeasibilityAgent 职责边界及为何不合并 Phase。
- [x] 新增 `docs/notes/2026-05-20-stream-cache-feasibility-architecture-qna.md` 复盘笔记。

### 架构问答 Review

- 已对照 `RecallCacheKeyBuilder`、`CourseRecallAgent`、前端 `StreamView`/`RecommendPage`、`hard_constraint_filter.py`、`course_feasibility_agent.py` 与 Supervisor Phase 编排，确认问答结论与代码一致。
- 本轮未修改业务代码，未提交 git commit，未运行 pytest/Docker。
