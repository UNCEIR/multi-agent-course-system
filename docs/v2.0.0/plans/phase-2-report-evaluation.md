# Phase 2 详细计划：报告 + 评价寄语 + 主 Agent 插件/MCP

> 本文件是 `../plan.md` Phase 2 的**详细实施计划**，承接 `notes/2026-07-27-设计决策问答记录.md` / `notes/2026-07-28-设计决策补充说明.md` 决策 1/5/7/9/10/11/13 及 Phase 2 阶段新增决策（见 §7.3 grill-me 记录）。Phase 1 平台基座已交付（统一 deepagent 工厂 + ToolRegistry + 记忆中间件 + 知识库 RAG + 推荐收敛），Phase 2 在此基座上交付**两个学生业务场景 + 主 agent 插件化**。
>
> 日期：2026-08-12
> 状态：待执行
> 门控属性：**非 go/no-go 门**——子项失败走降级回退（见 §6），不阻塞整体。

> **当前执行边界（2026-08-12）**：本阶段**完全不考虑 FastGPT**（需求.md 新增要求）；Java 数据服务**后置 Phase 3/4**（Phase 2 不动存储层，身份隔离维持 context user_id 临时口径）；前端 Phase 2 不做页面，只定接口契约与 SSE 消费规范（后续统一开发，MainPage/ReportPage/EvaluationPage 与 ImageGeneratePage/PPTGeneratePage 一并重构）；四个智能体 = chat（Phase 1 已交付，本阶段加插件能力 + **记忆机制实装**）/ recommend（已交付）/ report（新交付）/ evaluation（新交付）。

---

## 1. 目标与范围

### 1.1 目标（五个交付面 + 四条贯穿轴）

| 交付面 | 验证什么 | 对应决策/需求 |
|--------|---------|--------------|
| **A. report（教师端）** | 多科学科 Excel 批量入参 → 逐学生成绩单 PDF（HTML 兜底）+ LLM 综合评价 → 每学生独有下载链接 + 失败重试；纯确定性解析、零 LLM 数据参与 | 决策 5/7/9/13、需求.md、image-2/image-3（业务参考） |
| **B. evaluation（教师端生成 → 同步学生端）** | 以知识库 `document_chunks`（user 分区）成绩单为数据基准 → LLM 设计评价维度 + 确定性雷达数值 + 评语 → 落 `evaluation_records` → 学生端凭本人 user_id 读取；反幻觉工程化 | 决策 5/9/13、需求.md、image/image-1（业务参考） |
| **C. main agent 插件化 + MCP 实装** | web_search（tavily MCP）/ image_generate（即梦 MCP）/ code_interpreter（E2B MCP）/ image_recognize（视觉直连）/ writing_assistant（LLM）/ mindmap_generator（本地渲染）在 chat 内可用；mcp_client 实装 + 注册表 + 每服务器熔断 | 决策 7/8/16/17/18、需求.md（新增 Phase 2 提前项） |
| **D. chat 长期记忆实装** | 用户会话记录（消息历史）持久化可查询；跨会话长期记忆（增量摘要提取→按 user_id 隔离）；AGENTS.md 多租户隐私泄漏修复；写纪律（逐条落库/崩溃保守） | 需求.md"如何管理llm的上下文"、pi 记忆机制移植（subagent 调研 2026-08-12） |
| **E. 无状态智能体模式** | report/evaluation/recommend 不挂 checkpointer/不落会话树，一次性上下文注入、结果结构化回收，文档化为统一模式 | pi `--no-session`/in-memory 模式 |
| **轴 1 防信息丢失** | 六道闸（§3.2.3）：数据不过 LLM / 键合并+差集校验 / 两阶段渲染断言 / Journal 落盘 / 只留等级 / 幂等 | 需求.md"防止信息丢失" |
| **轴 2 防幻觉工程化** | evaluation 五层：快照（代码唯一事实源）→ 维度提案（schema 硬校验）→ 代码算值（metric 枚举）→ 评语数值引用核验硬闸 → 规则化兜底 | 需求.md"防止出现幻觉，增强回答准确性" |
| **轴 3 工具链路断裂兜底** | LLM 填表失败→Jinja2 降级→熔断全批降级；MinIO 失败→本地降级；MCP 熔断→直连/沙箱兜底；逐学生失败隔离 + 前端一键重试 | 决策 11/12、需求.md"调用失败如何进行兜底" |
| **轴 4 流式契约** | report/evaluation 均为 SSE，事件序 + 终结 `done` + 结构化 `error`，测试必须消费流断言 | AGENTS.md 前端 API 契约 |

### 1.2 范围（Phase 2 刻意不做的事）

- **不**做 FastGPT 相关（部署/客户端/拖拽/MCP）——需求.md 明确排除，Phase 3 起再评估
- **不**建 Java 数据服务/用户身份体系（`evaluation_records` 权限用 context user_id 强匹配临时口径）——Phase 3/4
- **不**做前端页面（只改后端契约：`ChatRequest.images`、report/evaluation SSE 事件协议）——后续统一开发
- **不**做 PPT 生成（`ppt_generate`）与独立图片生成页面——Phase 3
- **不**改 v1 推荐链路内部（`recommend_courses` tool 已包装，本阶段零改动）
- **不**做 RedisSaver/OpenTelemetry/harness 可视化——Phase 3/4
- **不**新建 LLM 配置组（HTML 填表/综合评语/维度提案均复用 `llm_model`，仅新增 `LLMTaskName` 枚举；`build_chat_openai` 扩展 model 覆盖参数但默认行为不变）
- **不**将计算交给 LLM（report 统计/雷达数值/合并/校验全部确定性代码）

### 1.3 贯穿原则

1. **agent 编排 vs 能力分离**：`agent/` 只做编排（report/evaluation 场景编排、决策节点），`tools/` 放原子能力（解析/合并/填充/渲染/快照/维度/评语/MCP 客户端），`skills/` 放 SKILL.md 技能文档。
2. **A-shell 模式**：report 以 deep agent 为壳（复用 `agent/main/factory.py` 的 AgentSpec，四决策点循环），重活收进确定性工具内部，LLM 只做决策与叙述，数值零幻觉。evaluation **端点走直接管线**（层①→⑤工具直调，不建 agent 壳——批量顺序确定、无 LLM 决策点），`EVALUATION_AGENT_SPEC` 保留仅为未来 chat 路由经 subagent 委派时使用（Phase 3 主 agent 对话内生成评价的场景）。
3. **LLM 提议 → 代码校验 → 规则兜底 → 可观测**（pi 思想）：每个 LLM 决策点都有 schema 校验 + 确定性回退 + trace 记录。
4. **流式契约**：所有新前端 API 默认 SSE，`done` 终结、`error` 结构化（AGENTS.md）。
5. **单一事实源**：`sql/init-db.sql` 唯一建表来源；模板目录即模板契约；`metadata_json` 是成绩单结构化数据唯一落点。

### 1.4 试金石（Definition of Done）

十条同时满足 = **Phase 2 GO**：

1. **report 端到端**：真实样本 `（道法）四7班2023-2024第二学期成绩.xlsx` 上传 → 正确解析（等级列 C/E/G/J/L，丢分数/备注）→ 四决策点循环跑通（分类=4-6 年级）→ 逐学生 PDF（WeasyPrint）+ HTML 兜底可用 → `report_artifacts` 落库 → token 下载端点返回文件；断网/断 MinIO 时本地兜底仍可下载
2. **report 防丢失**：多科文件学生顺序打乱后合并仍正确（按 学号 键）；缺科学生显式 `student_error` 不静默；Journal 断点续跑单测通过
3. **LLM 填表防线**：构造"LLM 故意填错/漏填/改模板"的 mock → 数值回填校验拦截 → 重试 → Jinja2 降级，全链单测通过；综合评语失败留空不阻塞
4. **evaluation 端到端**：成绩单摄入（metadata_json 结构化）→ 快照工具直查正确 → 维度提案 schema 校验（非法输出被拒并回灌）→ 雷达值=确定性计算 → 评语数值引用核验硬闸（注入幻觉数字被拦截→规则化兜底）
5. **evaluation 同步**：教师端生成落 `evaluation_records`；学生端 `GET /evaluation/me` 显式 `user_id` 参数（遵循 `/recommend/stream` 直接端点先例），请求其他用户返回空列表（无数据可越权），历史 append 保留
6. **MCP 实装**：`mcp_client` 配置注册表 + 三个 MCP 服务器 mock 测试（注册/发现/调用/熔断/降级链）；`web_search` 走 MCP 路径单测；`image_recognize` 视觉直连单测；`/chat/stream` 支持 `images` 字段
7. **SSE 契约**：report/evaluation 端点测试消费流并断言事件序 + `done` + 结构化 `error`（AGENTS.md 强制）
8. **回归**：`cd python; python -m pytest tests/ -m "not slow" -v` 全绿；`docker compose up -d --build` 构建通过（含 WeasyPrint 系统依赖）
9. **chat 记忆**：`/chat` 多轮后 `chat_messages` 可查询到完整消息历史（user/assistant/tool 逐条、seq 有序、tool_calls 可审计）；消息数达阈值后 `chat_memory_entries` 生成增量记忆且幂等（不重复提取、失败退避）；新会话**首轮**注入该 user 记忆（续轮不注入、他人 user_id 注入不到、匿名 user_id 不注入）；AGENTS.md 被 **FilesystemPermission 代码级禁写**（多租户隔离）
10. **无状态模式**：report/evaluation/recommend 三 spec `use_checkpointer=False`（工厂断言不建 checkpointer），运行后 `.checkpoint.db` 无新增行；单轮请求可用、重启后不恢复旧上下文
11. **评估方针骨架**：`eval_sets/` 首批 4 集就位（chat_intent/report_math/evaluation_comment/kb_retrieval）；`eval/runner.py` 断言式指标可跑（意图路由正确率/report 数值正确率/评语数值违规率/Recall@k/延迟 P50·P95）；LangSmith 数据集导入脚本可用

---

## 2. 风险与假设

### 2.1 已识别风险

| 风险 | 影响 | 暴露点 | 回退 |
|------|------|--------|------|
| WeasyPrint 在 Docker（python:3.12-slim）缺 libpango/libcairo | PDF 渲染失败 | Step 1 构建 + 冒烟 | Dockerfile 装系统包；仍失败 → HTML 兜底（本设计主兜底链），PDF 标记降级 |
| 多学科 Excel 表头结构与道法样本不一致（不同学校/科目维度不同） | 解析器漏列/错列 | Step 2 解析单测 + 真实样本 | 表头驱动解析（动态读 merged 表头而非写死列号）；新样本到达后补测试夹具；仍解析失败 → 结构化 `student_error` 不静默 |
| 即梦 MCP server URL/凭据未提供（外部依赖） | image_generate 无法端到端 | Step 7 | plan 留占位配置；`image_generate` 单测 mock MCP；真连放拿到凭据后冒烟 |
| E2B 国内可达性/无 key | code_interpreter 主路不可用 | Step 7 | 熔断 → 本地 Docker 受限沙箱兜底（超时+资源限制）；仍未就绪 → 结构化 error 不伪造执行结果 |
| tavily MCP 不可达 | web_search 失效 | Step 7 | MCP 熔断 → 直连 tavily SDK 兜底（非主路）→ 结构化 error |
| LLM 填表输出截断（模板+全量 HTML 超 max_tokens） | HTML 不完整 | Step 3 | max_tokens=8192 + 结构校验（标签闭合/锚点齐全）拦截 → 错误回灌重试 1 次 → Jinja2 降级 |
| 摄入管线改造（metadata_json）影响存量 RAG | query_knowledge 检索结果变化 | Step 5 | 重灌幂等（delete_by_dataset + replace_chunks）；单测断言 metadata_json 与正文一致性 |
| 分类 LLM 误判年级档 | 用错模板 | Step 4 | 规则兜底（道法列→4-6、必选/自选特征列→1-3、文件名年级词）；LLM 与规则冲突以规则为准并记录偏差 |
| 客户端中途断开 | 渲染任务悬挂 | Step 4 | 断开 → cancel agent 任务 → 工具内逐学生协作式取消；已生成 artifact 保留（Journal） |
| 多文件并发上传/大文件 | 内存/超时 | Step 4 | 单文件大小上限（默认 10MB）、文件数上限（默认 20）、逐文件流式读取 |

### 2.2 假设

- `python/.env` 已有可用 `LLM_*` / `EMBEDDING_*` / `MYSQL_*` / `MILVUS_*`（Phase 1 已验证）；`LLM_BASE_URL` 中转站可用
- openpyxl 已可解析真实样本（本计划开发时已实测：双层合并表头、多 sheet、数据行 7 起）
- 一年级（grade1-3）模板待用户提供，先以骨架占位；道法样本 + `1.html`（用户提供，四五六年级版）已就位
- 即梦 AI MCP、Tavily MCP、E2B MCP 均支持远端 streamable-http 接入（凭据/URL 由用户提供，plan 中留占位）
- `langchain-mcp-adapters>=0.1.0` 已入 requirements；`minio>=7.2.0` / `jinja2` / `weasyprint` 已入 requirements（`openpyxl` 需补）

---

## 3. 实施步骤

> 原则：**由内到外、逐层加变量**。先基建（settings/依赖/建表/LLM 扩展），再 report（解析→填充→编排→API），再 evaluation（数据基准→编排→API），再 MCP 插件，最后全量回归。每步跑 `compileall` + 聚焦测试，出错可回滚单步。

### Step 1：基建（settings / 依赖 / Dockerfile / 建表 / LLM 扩展 / MinIO 访问层）

**目标**：Phase 2 依赖的全部底座就绪：settings 配置组、`openpyxl` 入 requirements、Dockerfile WeasyPrint 系统依赖、`init-db.sql` 两张新表、`LLMTaskName` 四个新枚举、`build_chat_openai` model 覆盖扩展、`storage/minio/minio_repo.py` 实装、docker-compose minio 暴露与 env 注入。

**改动文件**：`python/config/settings.py`、`python/requirements.txt`、`python/Dockerfile`、`sql/init-db.sql`、`python/ai/llm_task_name.py`、`python/ai/llm_client.py`、`docker-compose.yml`、`.env.example`

**改动点**：

1. **settings.py 新增配置项**（详见 §5.1 代码块）：`minio_*`（endpoint/port/access_key/secret_key/secure/桶名）、`report_*`（下载 token 有效期、单文件大小上限、文件数上限、渲染并发、LLM 填充并发、学生超时秒数）、`mcp_servers`（注册表：name/transport/url/api_key_env/namespace）、`evaluation_*`（雷达轴数、metric 枚举不在此配置——代码常量）。
2. **requirements.txt**：`+openpyxl>=3.1`；确认 `minio`/`jinja2`/`weasyprint`/`langchain-mcp-adapters` 在位。
3. **Dockerfile**：`apt-get update && apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info fonts-noto-cjk`（WeasyPrint 运行时依赖 + **中文字体**，slim 镜像无 CJK 字体会渲染成豆腐块），放在 pip install 前。
4. **init-db.sql**：新增两表（见 §9 完整 DDL）：`report_artifacts`（batch_id/student_id/name/format/status/file_key/token_expires_at/created_at，索引 batch_id/student_id）+ `evaluation_records`（target_user_id/comment_type/radar_json/comment/status/generated_by/created_at/updated_at，索引 (target_user_id, created_at)）。
5. **llm_task_name.py**：新增 `REPORT_HTML_FILL = "report_html_fill"`（模板填充）、`REPORT_SUBJECTIVE_EVAL = "report_subjective_eval"`（综合评语）、`EVALUATION_DIMENSION_DESIGN = "evaluation_dimension_design"`（维度提案）、`VISION_ANALYZE = "vision_analyze"`（图片识别）、`MEMORY_EXTRACT = "memory_extract"`（记忆提取）；`EVALUATION_GENERATOR`/`TRANSCRIPT_PARSER` 已在。
6. **llm_client.py**：`_create_chat_openai` 增加可选覆盖参数 `model: str | None = None` / `base_url` / `api_key` / `enable_thinking: bool | None = None`，默认 None 时取 settings（**既有调用行为零变化**）；`build_chat_openai` 透传。填表/综合评语/维度/视觉调用经此入口 + 各自 `task_name`（AGENTS.md 硬约束）。
7. **storage/minio/minio_repo.py**（新）：`MinioRepository`——`ensure_bucket(bucket)`（幂等）/ `upload(bucket, object_key, data) -> object_key` / `download(bucket, key) -> bytes` / `exists(bucket, key) -> bool` / `delete(bucket, key)`；启动时 `ensure_bucket(report_bucket)`；**本地兜底**：初始化时探测 MinIO 可用性（3s 超时），不可用/后续异常 → 降级写入 `python/.documents/reports/<batch_id>/`，`exists/download` 统一寻址（先 MinIO 后本地）。可测：mock minio client。
8. **docker-compose.yml**：minio 服务暴露 `9002:9002`/`9002:9002`，python-api 环境注入 `MINIO_ENDPOINT/MINIO_ACCESS_KEY/MINIO_SECRET_KEY`（不写死凭据，从 `.env` 读）；`MYSQL_PORT` 宿主 3307 维持不变。
9. **.env.example**：补 `MINIO_*`、`TAVILY_API_KEY`、`JIMENG_API_KEY`、`JIMENG_MCP_URL`（占位）、`E2B_API_KEY`、`E2B_MCP_URL`（占位）。

**验证点**：
- `python -m compileall config/ ai/ storage/minio/` 通过
- `docker compose up -d --build` 构建成功（WeasyPrint 系统依赖安装成功）
- `cd python; python -m pytest tests/test_minio_repo.py -v`（mock 全绿）
- `python -c "from ai.llm_client import build_chat_openai; build_chat_openai(temperature=0.1, max_tokens=1024, task_name=None)"` 行为不变（默认路径回归）

**回退**：WeasyPrint 系统依赖装不上 → 保持 HTML 兜底主路，PDF 标记降级；MinIO 起不来 → 本地兜底自动生效，不阻塞后续步骤。

### Step 2：report 解析与合并（确定性管线核心）

**目标**：`parse_score_excels` 确定性工具——多科 Excel 表头驱动解析 → (学号,姓名,班级) 键合并 → 中间形态 JSON（§3.2.2 契约）→ 完整性校验 → Journal 落盘。**全程零 LLM**。

**新增文件**：`python/tools/report/__init__.py`、`python/tools/report/parse_score_excels.py`、`python/tools/report/merge_students.py`（可并入前者，独立便于单测）

**改动点**：

1. **表头驱动解析器**（`parse_score_excels`，`@tool` + Pydantic `args_schema`，输入 `file_keys: list[str]`）：
   - sheet 选择：遍历 sheet，命中"含 学号 + 姓名 表头（行内非空）+ 其后存在数据行"的 sheet 作为数据源（真实样本三 sheet 中正确选出数据 sheet，跳过 `Sheet3` 一年级模板表/`Sheet1` 空表）
   - 表头定位：找到含"姓名"单元格的行作为表头块首行；表头块 = 该行起 3 行（真实样本 row4 大类 / row5 合并延续 / row6 子类）
   - 列模型构建（合并单元格感知，`openpyxl` 非只读模式 `merged_cells.ranges`）：对每个数据列解析出 `(父维度名, 子维度名)`；子类为 `等级` 的列 = **等级列**（真实样本：C=过程性评价（无子类，自身即等级）、E=综合答辩·等级、G=学科实践·等级、J=考试性评价70分·等级、L=综合性评价100分·等级）
   - 元数据提取：行3 `班级：X  学科：Y  任课：Z`（A3:M3 合并）→ 班级/学科；行3 缺失 → 文件名解析兜底（`（道法）四7班…` → 学科=道法、班=四7班）
   - 逐数据行抽取：学号、姓名、各等级列值（空值保留为空串，**不推断**）；分数/原始/折算/备注列**直接丢弃**
   - 值域归一：等级值 NFKC + 去空白；学号规范化（数字字符串化）
2. **合并器**（`merge_students`）：
   - 主键 = `学号`（优先）；学号缺失/重复 → 回退 `(班级,姓名)`；键冲突 → 记告警不静默
   - 跨文件差集校验：每个文件的学号集合与主索引 diff → 多出/缺失 → 告警清单（进异常处置决策节点 ④ 输入）
   - 输出中间形态 JSON：
     ```json
     {
       "batch_id": "b_<uuid8>",
       "semester": "2023-2024第二学期",
       "students": [
         {"student_id": "1", "class": "四（7）班", "name": "陈烨",
          "score": [{"subject": "道法",
                     "过程性评价": "A", "综合答辩": "A", "学科实践": "A",
                     "考试性评价70分": "A", "综合性评价100分": "A"}]}
       ]
     }
     ```
     ——字段名与表中一致（动态，各科不同），只含等级值
3. **完整性断言**（渲染前置）：`len(students) == 期望`、每生 `len(score) == 科目数`；不满足 → 该批次不渲染，返回结构化错误 + 明细
4. **Journal 落盘**：每解析完一个文件即把合并中间态写入 `<batch_id>/intermediate/merged.json`（本地，MinIO 可用时同步）；渲染阶段逐学生完成标记 `students.json.status`
5. **错误模型**：解析失败按 `(file, sheet, row, reason)` 结构化返回，进 `student_error`/`batch_error`

**验证点**：
- 单测：真实样本 fixture（拷入 `tests/fixtures/`）解析 → 断言等级列值、分数列被丢、sheet 选择正确、行3 班级/学科提取正确
- 单测：两科文件（同一批学生、顺序打乱）合并 → 键合并正确、差集校验告警正确
- 单测：缺学号/键冲突/空表头 → 结构化错误

**回退**：新样本表头结构不兼容 → 解析器表头配置化（settings `report_header_profile`），样本驱动补配，不写死。

### Step 3：report 模板与填充（LLM 填充 + 确定性校验 + Jinja2 降级）

**目标**：两套模板（锚点规范）+ LLM 填充器 + 输出校验（结构 + 数值回填）+ Jinja2 确定性降级 + 综合评语生成器。

**新增文件**：`python/templates/report/grade4-6.html`（自用户 `1.html` 迁移 + 锚点 + 评语区）、`python/templates/report/grade1-3.html`（骨架占位，待用户提供）、`python/tools/report/fill_report_html.py`（LLM 填充 + 校验 + Jinja2 降级）、`python/tools/report/generate_subjective_eval.py`（综合评语）、`python/tools/report/prompts/fill_template.txt`、`python/tools/report/prompts/subjective_eval.txt`、`python/skills/report-generation/SKILL.md`（改写）

**改动点**：

1. **模板锚点规范**：每个可填空单元格 = `<span class="fill" data-slot="<subject>|<dimension>|grade"></span>`；班级/姓名 = `<span class="fill" data-slot="class|name"></span>`；评语区 = `<div class="comment-section" data-slot="comment"></div>`（默认留空）。**模板文件 = 契约**，两种填充器共用同一份文件。**学科/维度别名映射**（Excel 名 ↔ 模板名，如 道法↔道德与法治、考试性评价70分↔卷面成绩、综合性评价100分↔期末总评）定义在 `tools/report/contract.py`（`SUBJECT_ALIAS`/`DIMENSION_ALIAS`），数值回填校验与锚点匹配均以此归一（P0-5，缺失则校验无匹配依据）。
   - grade4-6 模板：迁移 `1.html`（12 学科块），班级/姓名 input 改为锚点 span，评语区追加在表格后
   - grade1-3 模板：骨架——按综合测评表结构（过程性/展示性·必选/自选/综合性评价），字段集待真实模板到达后替换文件即生效
2. **LLM 填充器**（`fill_report_html`）：**逐学生调用**（get single stu 语义），输入 = 模板全文 + 该学生 JSON + `fill_template.txt` 指令（复刻 FastGPT 提示词约束：模板不可删改、只填锚点、没给到的留空、评语区不动 + 本项目增强：只输出 HTML）；模型 = 复用 `llm_model`，`build_chat_openai(max_tokens=8192, temperature=0.1, task_name=REPORT_HTML_FILL)`
3. **输出校验（代码）**：
   - 结构校验：HTML 标签闭合（简单栈校验）+ 模板锚点全集 `data-slot` 都在输出中（一个不少）+ 评语区 `data-slot="comment"` 存在
   - **数值回填校验**：解析输出 HTML 提取每个 `data-slot` 文本 → 与源 JSON 该生该科该维度等级**逐字段比对**；不一致/漏填 → 错误回灌重试 1 次（把差异明细喂回 prompt）→ 仍不一致 → 该学生走 Jinja2 降级
4. **Jinja2 降级器**：同一模板 + `render_report_batch` 内直渲（锚点填值），输出同样过结构校验；失败 → `student_error`
5. **综合评语生成器**（`generate_subjective_eval`）：输入 = 该生全科等级 JSON（确定性）→ `subjective_eval.txt` 指令（基于给定等级、禁止编造科目/数字、30-80 字、语气规范）→ `build_chat_openai(task_name=REPORT_SUBJECTIVE_EVAL)`；失败/超时(60s) → 评语区留空（`data-slot="comment"` 保持空），**不阻塞交付**，错误进 trace + 结果摘要
6. **并发与超时**：WeasyPrint 渲染为同步 CPU 密集任务——`asyncio.to_thread` + `Semaphore(report_render_concurrency)` 限流（避免 gather 串行且阻塞 SSE 推送）；LLM 填充并发 `report_llm_fill_concurrency=4`（asyncio 原生），单生超时 60s；综合评语同并发池
7. **SKILL.md 改写**：`report-generation/SKILL.md` 按新契约（多文件上传 → 分类 → 生成链接列表；去掉旧 compute_weighted_grade 数值描述；注明 LLM 只填表不计算）

**验证点**：
- 单测（mock LLM 响应）：正确填充 → 校验通过；构造"改模板/漏填/填错等级/输出截断"四类坏响应 → 拦截 → 重试 → Jinja2 降级路径断言
- 单测：Jinja2 渲染与 LLM 填充产物同模板、同锚点、字段一致
- 单测：综合评语失败 → 评语区留空 + 学生仍交付

**回退**：LLM 填表连续失败 → CircuitBreaker 熔断（3 次）→ 全批转 Jinja2 确定性填充（交付不失败）。

### Step 4：report 编排与 API（A-shell + 四决策点循环 + SSE + 下载端点）

**目标**：`POST /api/v1/report`（SSE）——deep agent 壳内四决策点循环驱动 `render_report_batch` 工具；进度 channel 合流；`report_artifacts` 落库；token 下载端点。

**新增/改动文件**：`python/agent/report/service.py`（编排门面）、`python/agent/report/__init__.py`（docstring 更新）、`python/tools/report/render_report_batch.py`、`python/api/report.py`（重写 + 注册）、`python/agent/app.py`（include_router）、`python/agent/runtime.py`（注册工具）、`python/agent/main/specs.py`（REPORT_AGENT_SPEC 更新）、`python/storage/mysql/report_artifact_repo.py`、`python/skills/report-generation/SKILL.md`（已含 Step 3）

**改动点**：

1. **四决策点循环**（deep agent，`REPORT_AGENT_SPEC` 更新：skills=`/skills/report-generation/`，allowed_tools=`(inspect_score_excels, render_report_batch)`）：
   - **节点① 信息完备性（LLM）**：从用户消息提取年级/学期信息（NLP）；代码补闸——未传文件 → 直接澄清
   - **节点② `inspect_score_excels`（确定性工具）**：文件摘要（学科/班级/sheet 列表/是否含道法列/是否含必选-自选特征列/学生数）
   - **节点③ 年级分类（LLM）**：`category ∈ {1(一二三年级), 2(四五六年级), unknown}` + 置信度 + 理由；规则校验闸：摘要含道法 → 2；含必选/自选特征列 → 1；文件名含"一二三/四五六" → 对应档；LLM 与规则冲突 → 以规则为准 + 偏差记录；`unknown` → 反问用户（多轮澄清）
   - **节点④ 异常处置（LLM）**：输入 = 节点②告警清单 → 决策 全部渲染 / 跳过异常文件继续 / 中止；约束：不得静默吞告警（最终报告必须含 warning 清单）
   - **节点⑤ `render_report_batch`（确定性执行）**：Step 2 解析合并 + Step 3 填充渲染 + 存储上传 + `report_artifacts` 落库；进度经 channel 上报
   - **节点⑥ 交付汇总（LLM 叙述 + 确定性数据）**：成功/失败/警告清单 + 链接列表；`done` 负载**由工具结果装配，不采信 LLM 文本**
2. **`render_report_batch` 工具**：**必须声明为 `async def`**（进度 channel 与取消依赖事件循环内执行——sync `@tool` 会被 LangChain 丢进线程池，contextvar 不穿透线程、`asyncio.Queue` 非线程安全）。入参 `file_keys: list[str]`、`category: int`、`semester: str`（`user_message` 只进 agent prompt 供节点①/③使用，不进工具参数）；内部 = 完整确定性管线（调 Step 2/3 能力）；**进度 channel**：contextvar + `asyncio.Queue`，逐学生完成后 `put(("student_done", {...}))`；工具结果 = `{students: [{student_id, name, status, format, url}], failed_students: [...], warnings: [...]}`；**取消**：每学生循环前 `asyncio.current_task().cancelled()` 检查 + 整体 `try/except asyncio.CancelledError` 收敛（客户端断开 → `StreamingResponse` 取消 → 传播到工具内需兜住并清理中间产物），`RequestDisconnectError` → cancel
3. **`agent/report/service.py` 编排门面**：`async def stream_report(request, sse_queue)`——建 agent（`build_report_agent`）→ 并发消费 agent `astream_events`（`on_tool_start/on_tool_end` 外壳事件）+ 工具进度 queue → 归一为 SSE 事件流
4. **SSE 事件协议**（`api/report.py` 重写，`POST /api/v1/report`，multipart `files` + `semester` + 可选 `user_message`）：
   - `event: text` `{text}`（agent 节点①③④⑥ 的澄清提问与交付叙述——LLM 文本仅此通道可见，数值类内容仍以 `student_done`/`done` 确定性事件为准）
   - `event: progress` `{phase: "parsing"|"rendering"|"uploading", detail}`（节点级）
   - `event: student_done` `{student_id, name, status: "ok", format: "pdf"|"html", url}`
   - `event: student_error` `{student_id, name, code: "render_failed"|"fill_failed"|"parse_failed"|"upload_failed", reason}`
   - `event: done` `{batch_id, students: [...], failed_students: [...], warnings: [...]}`
   - `event: error` `{code, message}`（致命失败，结构化终止）
5. **`report_artifact_repo.py`**：`create_artifact(batch_id, student_id, name, format, status, file_key)` / `list_by_batch(batch_id)` / `get_by_batch_student(batch_id, student_id)` / `list_latest_by_student(student_id)`；下载端点读表校验存在性
6. **token 下载端点**：`GET /api/v1/report/download?file_key=...&token=...`——token = `HMAC(secret, f"{file_key}:{expires_at}")`，有效期 `report_download_ttl_hours=24`；校验失败 → `{code: "token_expired"|"invalid_token", retry_hint}`；文件寻址：MinIO → 本地兜底 → 不存在 `{code: "artifact_not_found", retry_hint: "重新生成"}`；命中 → 流式返回（`application/pdf` / `text/html`）
7. **runtime.py**：注册 `inspect_score_excels`/`render_report_batch`；`app.py` `include_router(report.router)`
8. **文件存储**：artifact 对象键 `<batch_id>/<student_id>.<format>`（MinIO `report-artifacts` 桶 / 本地 `<repo>/python/.documents/reports/<batch_id>/`）；`merged.json` 及渲染中间产物同目录

**验证点**：
- 单测（mock LLM）：四决策点各分支（分类冲突/unknown 反问/告警决策）断言
- API 测试（TestClient 消费 SSE 流）：真实样本文件 → 断言事件序 `progress...student_done...done`；断 MinIO（mock 抛错）→ 本地兜底仍 `student_done`；`error` 事件结构化
- 单测：token 过期/伪造/文件缺失 → 三类结构化错误
- `curl` 冒烟：上传道法样本 → 下载 PDF 打开为有效文件

**回退**：agent 循环 LLM 调用失败 → 循环降级为"规则直通"（分类走规则、告警走默认"跳过异常继续"、不反问），管线仍可交付。

### Step 5：evaluation 数据基准（摄入管线改造 + 快照工具）

**目标**：成绩单摄入时把结构化数据（课程/学分/成绩）写入 `document_chunks.metadata_json`（列已存在，零 schema 变更）；`get_academic_snapshot` 确定性直查工具。

**改动文件**：`python/tools/documents/desensitizer.py`（或新增结构化提取）、`python/scripts/ingest_transcript_desensitized.py`、`python/agent/documents/service.py`（摄入落 metadata_json）、`python/storage/mysql/document_repo.py`（`get_chunk_contents` 扩展返回 metadata_json）、`python/tools/evaluation/get_academic_snapshot.py`（新）

**改动点**：

1. **结构化提取**（摄入管线 B 方案）：成绩单解析后（脱敏正文之外）新增结构化提取步骤——从原始成绩单表格文本提取 `courses: [{course_name, course_nature, credits, score}]`（正则锚定课程行格式；提取失败 → 记 warning 不阻塞摄入，该用户快照降级为空 + 错误提示）；写入该 dataset 各 chunk 的 `metadata_json`（同构，每 chunk 存全量结构化数据，避免按 chunk 分片查询拼接）
2. **存量重灌**：`ingest_transcript_desensitized.py` 重跑（幂等，`delete_by_dataset` + `replace_chunks`）；验证 `metadata_json` 有值
3. **`get_academic_snapshot(user_id)` 工具**（`@tool`，user_id 从 `agent.main.context.get_current_user_id()` 注入，不暴露在 args_schema——AGENTS.md 约束；直接端点场景由 API 层显式传入）：
   - `document_repo.get_chunks_by_user(user_id)`（**新增方法**，按 `JSON_EXTRACT(metadata_json, '$.user_id')` 过滤，覆盖 ingest 脚本与 `/documents/upload` 两条摄入路径）→ 取 metadata_json → 结构化课程列表
   - 既有 `get_chunk_contents` **保持不动**（被 `query_knowledge` 消费，改结构有回归风险）
   - 派生统计（确定性）：课程数、总学分、均分、学分加权均分、方差、最高/最低分科目、及格率
   - 输出 `AcademicSnapshot` JSON：`{user_id, courses: [...], derived: {...}, sources: [chunk_ids]}`（sources 供溯源/引用）
   - 无数据 → 结构化错误 `{code: "no_transcript_data", hint: "请先上传成绩单"}`（SSE `error`，不空跑 LLM）
4. **查缺兜底**：metadata_json 缺失（存量未重灌）→ 回退正则解析该用户正文 chunk；仍无 → 错误如上

**验证点**：
- 单测：摄入管线 mock → metadata_json 结构断言
- 单测：快照工具（mock repo）→ 派生统计数值与手算一致；无数据 → 结构化错误
- 集成（有库环境）：重灌成绩单 → 快照返回课程/学分/成绩正确

**回退**：结构化提取对异常成绩单格式失败 → warning + 快照降级，evaluation 流程给出明确错误而非幻觉数据。

### Step 6：evaluation 编排与 API（反幻觉分层 + 教师端生成 + 学生端同步）

**目标**：`POST /api/v1/evaluation`（SSE 教师端流式生成，落库）+ `GET /api/v1/evaluation/me`（学生端读取）；反幻觉五层全链路。

**新增/改动文件**：`python/tools/evaluation/design_dimensions.py`、`python/tools/evaluation/compute_radar_values.py`、`python/tools/evaluation/generate_comment.py`、`python/agent/evaluation/service.py`（编排）、`python/agent/evaluation/__init__.py`（docstring 更新）、`python/api/evaluation.py`（重写 + 注册）、`python/storage/mysql/evaluation_repo.py`、`python/agent/main/specs.py`（EVALUATION_AGENT_SPEC 更新）、`python/skills/evaluation-writing/SKILL.md`（改写）、`python/tools/evaluation/prompts/dimension_design.txt`、`prompts/comment.txt`

**改动点**：

1. **五层反幻觉管线**（`agent/evaluation/service.py` 编排）：
   - **层① 快照**（Step 5 `get_academic_snapshot`，确定性唯一事实源）
   - **层② 维度提案（LLM）**：`design_dimensions`——输入快照 → `dimension_design.txt`（要求结构化 JSON）→ 输出 Pydantic 校验：`{"dimensions": [{"name"(≤8字), "weight"(≥0,合计≈1), "metric"(枚举), "rationale"(≤50字)}]}` + `"overall_theme"(≤20字)`；**维度数必须恰为 `evaluation_radar_axis_count`（默认 5）**，数量不符视为校验失败；校验失败 → 错误回灌重试 1 次 → 仍失败 → 默认维度集（代码内置 5 维 + 等权重）
   - **层③ 雷达数值（代码）**：`compute_radar_values`——metric 枚举实现：`weighted_gpa`（学分加权均分归一 0-100）/ `stability`（100 - 成绩方差）/ `top_subject`（最高分科目得分）/ `pass_rate`（及格率×100）/ `credit_load`（总学分归一）；未知 metric → 拒绝该维度并记偏差；输出 `RadarData` JSON（轴数=提案维度数，值全部代码计算）→ SSE `radar` 事件
   - **层④ 评语（LLM）**：`generate_comment`——输入 = 快照 + RadarData + 维度解读 + comment_type；`comment.txt` 指令（每个数字必须来自给定数据、语气按类型、篇幅 60-150 字）；输出经 **数值引用核验闸**：正则提取评语中数字 → 与快照/雷达数值集合逐一对账（容差 0.5）→ 不一致 → 错误回灌重试 1 次 → 仍失败 → 规则化评语（模板 + 真实数值填充）；评语流式 token 经 channel → SSE `comment_token`
   - **层⑤ 链路兜底**：每层 LLM 调用包 CircuitBreaker（独立实例）——**CircuitBreaker 需新增 `acall`（async 包装）**，现 `call()` 为同步实现，包 async 函数时异常发生在 await 点，失败计数/熔断完全失效；层②/④失败走各自确定性降级；整生失败 → `error` 事件 + 不落库
2. **comment_type**：**显式必选**，4 枚举 `semester_summary / encouragement / improvement_advice / recommendation`（与 SKILL.md 一致）；非法值 → 422 结构化错误
3. **教师端 API**（`POST /api/v1/evaluation`，JSON：`{target_user_id, comment_type, grade_hint?, generated_by?}`；SSE）：
   - `event: stage` `{stage: "snapshot"|"dimensions"|"radar"|"comment", detail}`（层间心跳，防中间件/反代空闲超时）
   - `event: radar` `{target_user_id, dimensions: [...], values: [...]}`
   - `event: comment_token` `{token}`（逐 token 流）
   - `event: done` `{evaluation_id, target_user_id, comment_type, radar, comment, created_at}`（生成完自动 INSERT `evaluation_records`）
   - `event: error` `{code, message}`（如 `no_transcript_data`）
4. **学生端 API**（`GET /api/v1/evaluation/me?user_id=...`）：**显式 `user_id` 查询参数**（遵循 AGENTS.md `/recommend/stream` 直接端点先例——直接端点显式收 user_id，不依赖 `user_context` 包裹；chat 场景由 `/chat` 的 context 注入后内部委派）。`evaluation_repo.list_by_user(user_id, limit=20)` → 最新一条 + 历史列表；无记录 → `{items: []}`；**越权防护**：无该用户数据即返回空（无数据可越权），请求他人生成记录无返回；真实身份绑定由 Phase 3/4 Java 身份体系替换
5. **EVALUATION_AGENT_SPEC 更新**：allowed_tools=`(get_academic_snapshot, design_dimensions, compute_radar_values, generate_comment)`；`evaluation-writing/SKILL.md` 改写（数据源=知识库成绩单、comment_type 必选、反幻觉规则、失败兜底）
6. **evaluation_repo.py**：`insert(...)` / `list_by_user(user_id, limit)` / `get(evaluation_id)`（回查校验 target_user_id）
7. **app.py** `include_router(evaluation.router)`；runtime 注册 4 个 evaluation 工具

**验证点**：
- 单测（mock LLM）：非法维度提案（超长/未知 metric/权重不归一）→ 拦截重试 → 默认维度；评语注入幻觉数字 → 核验拦截 → 重试 → 规则化兜底
- 单测：雷达数值 = 手算断言（确定性）
- API 测试：教师端 SSE 事件序 `radar → comment_token* → done`；无成绩单 → `error{no_transcript_data}`；学生端 `/me` 列表与越权隔离
- 回归：摄入重灌后 `query_knowledge` 检索成绩单仍正常（RAG 不破）

**回退**：任一 LLM 层熔断 → 确定性降级路径仍产出（默认维度 + 规则化评语），学生端可读但标记 `status="fallback"`。

### Step 7：main agent 插件化 + MCP 实装

**目标**：`mcp_client.py` 实装（配置注册表 + 懒连接 + langchain-mcp-adapters 转工具 + 每服务器 CircuitBreaker）；三 MCP 服务器接入；`image_recognize` 新工具（视觉直连）；写作/脑图实装；skill 与 tool 文档配套；`/chat/stream` 支持 `images`。

**新增/改动文件**：`python/tools/mcp_client.py`（实装）、`python/tools/chat/web_search.py`（MCP 化）、`python/tools/image/image_generate.py`（即梦 MCP）、`python/tools/image/image_recognize.py`（新，视觉直连）、`python/tools/code/code_interpreter.py`（E2B MCP + 本地沙箱兜底）、`python/tools/chat/writing_assistant.py`（实装）、`python/tools/mindmap/mindmap_generator.py`（实装）、`python/config/settings.py`（`mcp_servers`）、`python/agent/runtime.py`（MCP 注册 + 工具注册）、`python/api/chat.py`（ChatRequest.images）、`python/skills/image-generation/SKILL.md`（新）、`python/skills/web-search/SKILL.md`（改写）、`python/skills/writing/SKILL.md`（实装版）、`docs/v2.0.0/tools/*.md`（同步）

**改动点**：

1. **mcp_client.py 实装**：
   - 服务器注册表：`settings.mcp_servers` → `{server_name: {transport: "streamable_http"|"stdio", url, api_key_env, namespace}}`（默认三服务器占位：`tavily`/`jimeng`/`e2b`，url/key 从 `.env` 读，未配置则跳过）
   - `connect(server_name)`：懒连接 + 缓存；`list_tools(server_name) -> list[dict]`：经 `langchain-mcp-adapters`（`MultiServerMCPClient` 或 `StreamableHttpClient` 适配）转 LangChain `StructuredTool`；`call_tool(server_name, tool_name, args)`：工具名带 namespace 前缀（`search/*`、`image/*`、`code/*`）
   - **每服务器独立 CircuitBreaker**：`circuit_breaker.py` 复用（需先加 `acall` async 包装，见 Step 6 层⑤）；熔断 → 触发对应降级链
   - 生命周期：`runtime.init()` 注册（不连接）；首次工具调用触发懒连接；熔断半开后重连
   - 统一失败语义：连接失败/调用失败 → `isError` result（`{code, message}`），不抛异常（pi 模式）
2. **web_search（MCP 主路 + 直连兜底）**：`@tool` 签名不变（`query/max_results`）→ 内部调 MCP `search/web_search`（namespace `search/*`）→ 熔断 → 直连 `tavily-python`（兜底，非主路）→ 双失败 → 结构化 error；`web-search/SKILL.md` 改写为 MCP 版工作流
3. **image_generate（即梦 MCP）**：`@tool`（`prompt/ratio/style?/negative?`）→ MCP `jimeng`（namespace `image/*`）→ 产物 URL 下载存 MinIO/本地 → 返回可访问链接；无替代兜底 → 结构化 error（**不伪造图片**）；`skills/image-generation/SKILL.md`（新）：触发条件/参数规范/工作流（MCP client 配置、生成→存储→链接）/失败兜底
4. **image_recognize（新，视觉直连）**：`@tool`（`image_url: str, question: str = ""`）→ `build_chat_openai(model=settings.vision_model, task_name=VISION_ANALYZE)` → 分析文本；图片数据来源：`/chat/stream` 的 `images` 附件 → 存本地 → 转 data URL/路径入参；失败 → 结构化 error + 熔断
5. **code_interpreter（E2B MCP + 本地沙箱兜底）**：`@tool`（`language/code/timeout`）→ MCP `e2b`（namespace `code/*`）→ 熔断 → 本地 Docker 受限沙箱（单容器、CPU/内存/网络限制、超时 kill）→ 双失败 → 结构化 error
6. **writing_assistant / mindmap_generator 实装**：writing——`build_chat_openai(task_name=MAIN_AGENT_ROUTER 或新增 WRITING_ASSISTANT)` 多体裁生成（大纲→正文分段流式可选）；mindmap——LLM 生成 DSL（markdown 大纲）→ 本地 `markmap`/`mermaid-cli` 渲染为 HTML/SVG → 返回文件链接；失败 → 结构化 error
7. **ChatRequest.images 契约**：`api/chat.py` `ChatRequest` 增加 `images: list[str] = []`（URL 或 data URL，上限 4）；main agent 系统提示声明"用户消息含图片附件时可调 image_recognize"；`image_recognize` 加入 `MAIN_AGENT_SPEC.allowed_tools`（其余 5 个已在内）
8. **docs/v2.0.0/tools/*.md 同步**：web_search / image_generate / code_interpreter / mindmap_generator / writing_assistant 更新为实装版说明 + image_recognize.md 新增

**验证点**：
- 单测：mock MCP 三服务器（`tests/fake_mcp_server.py`）→ 注册/发现/调用/namespace 前缀断言
- 单测：web_search MCP 失败 → 直连兜底 → 双失败 error；image_generate MCP 失败 → 结构化 error（无伪造）
- 单测：image_recognize（mock vision LLM）→ 返回分析文本
- API 测试：`/chat/stream` 带 `images` 字段 → 正常流式（mock main agent 工具链）
- 真连冒烟（凭据就位后）：web_search 走 tavily MCP 返回结果

**回退**：外部 MCP 全部不可达 → 工具返回结构化 error，main agent 对话不受影响（聊天/推荐/知识库路径零依赖 MCP）。

### Step 8：全量回归与验收

**目标**：十条试金石全过。

**改动文件**：`python/tests/`（新增 19 个测试文件，含 5 个记忆测试）

**测试清单**：

| 测试文件 | 覆盖 |
|---------|------|
| `tests/test_report_parse_score_excels.py` | 真实样本解析、sheet 选择、等级列抽取、值域归一 |
| `tests/test_report_merge_students.py` | 键合并、顺序打乱、差集告警、键冲突 |
| `tests/test_report_fill_html.py` | 锚点校验、四类坏响应拦截、Jinja2 降级、结构校验 |
| `tests/test_report_subjective_eval.py` | 综合评语生成/失败留空 |
| `tests/test_report_service.py` | 四决策点循环分支（mock LLM） |
| `tests/test_report_api.py` | SSE 事件序 + done + error + token 下载三类错误（`@pytest.mark.api`） |
| `tests/test_report_artifact_repo.py` | report_artifacts CRUD |
| `tests/test_evaluation_snapshot.py` | metadata_json 结构化 + 派生统计手算断言 |
| `tests/test_evaluation_radar.py` | 维度提案校验、雷达数值确定性、默认维度降级 |
| `tests/test_evaluation_comment.py` | 评语核验硬闸、幻觉注入拦截、规则化兜底 |
| `tests/test_evaluation_api.py` | 教师端 SSE + 学生端 /me 越权隔离（`@pytest.mark.api`） |
| `tests/test_mcp_client.py` | 三服务器 mock 注册/发现/调用/熔断/降级 |
| `tests/test_main_agent_plugins.py` | web_search MCP 路径、image_recognize、writing、mindmap |
| `tests/test_chat_session_repo.py` | chat_sessions/chat_messages/chat_memory_entries CRUD + seq 唯一约束 + content_hash 去重 |
| `tests/test_chat_persistence.py` | 写纪律：/chat 与 /chat/stream 落库、崩溃保守、幂等、匿名跳过、并发锁 |
| `tests/test_memory_extractor.py` | 增量摘要提取、阈值触发、幂等、失败退避、oldest-first 分批、user_id 隔离 |
| `tests/test_memory_injector.py` | 注入时机（首轮/续轮/跨 user/匿名）与内容隔离 |
| `tests/test_stateless_specs.py` | 无状态 spec 不建 checkpointer、checkpoint 无新增行（tmp_path 隔离） |

**验证点**：
- `cd python; python -m pytest tests/ -m "not slow" -v` 全绿（含全部新测试）
- `python -m pytest tests/test_stream_recommend.py tests/test_documents_upload.py -v`（既有功能回归）
- `docker compose up -d --build && docker compose ps` 全 healthy
- 端到端冒烟（有库/凭据环境）：report 真实样本全链；evaluation 摄入→生成→读取；chat 插件工具；chat 多轮 → 查库验证消息落盘 + 记忆提取

### Step 9：记忆机制实装（chat 长期记忆 + 无状态智能体模式）

**目标**：交付面 D/E——chat 会话记录持久化（可查询消息历史）、跨会话长期记忆（增量摘要提取、按 user_id 隔离）、AGENTS.md 多租户泄漏修复、写纪律；report/evaluation/recommend 无状态模式落地。移植自 pi 记忆机制（subagent 调研 2026-08-12：append-only 条目树 / 增量摘要 `<previous-summary>` / 写纪律 / in-memory 无状态模式）。

**新增/改动文件**：`python/storage/mysql/chat_session_repo.py`（新）、`python/agent/memory/__init__.py`（新）、`python/agent/memory/persistence.py`（新）、`python/agent/memory/extractor.py`（新）、`python/agent/memory/injector.py`（新）、`python/agent/memory/prompts/memory_extract.txt`（新）、`python/agent/main/specs.py`（改）、`python/agent/main/factory.py`（改）、`python/agent/main/prompt.py`（改）、`python/api/chat.py`（改）、`python/memories/AGENTS.md`（改）、`python/config/settings.py`（改）、`python/ai/llm_task_name.py`（改）、`python/agent/runtime.py`（改）、`python/ai/llm_client.py`（改，`FilesystemPermission` deny 写回需要时）、`sql/init-db.sql`（改）

**改动点**：

1. **数据模型（init-db.sql 新增 3 表，见 §9）**：
   - `chat_sessions`（session_id PK / user_id / title / message_count / last_extracted_seq / status）
   - `chat_messages`（id / session_id / user_id / seq / role / content / tool_calls_json / usage_json，UNIQUE(session_id, seq)——**append-only 会话记录**，即"用户当前通话的 chat 会话记录进行存储"的直接落点；**本阶段只增不删**，水位只引用表内 seq，与 checkpoint 不对齐也不需对齐）
   - `chat_memory_entries`（id / user_id / kind=preference|fact|decision / content(TEXT) / content_hash / source_session_id / created_at / updated_at，UNIQUE(user_id, kind, content_hash)）——**跨会话长期记忆条目**，按 user_id 隔离
2. **双写职责声明**：checkpointer（SqliteSaver）管**运行态**（thread_id 恢复、compaction 上下文）；`chat_messages` 管**历史审计**（可查询全量、记忆提取源）。compaction 后 checkpoint 历史被压缩而 chat_messages 保留全量，属预期；`seq` 为表内自增，不与 checkpoint 对齐。
3. **写纪律（pi 移植）**：`persistence.py` 提供 `persist_turn(session_id, user_id, user_msg, assistant_msgs)`（逐条 INSERT chat_messages + 事务内原子自增 `UPDATE chat_sessions SET message_count=message_count+1` 分配 seq——**并发安全**，配 per-session `asyncio.Lock`；每条消息独立提交，中断不丢已落）；**匿名隔离**：`user_id` 为空时跳过持久化/提取/注入（会话仅走 checkpoint）；`get_or_create_session` 以 `(session_id, user_id)` 为复合键，不匹配则新开会话（防跨用户串会话）；`chat.py` 的 `/chat`（ainvoke 返回前）与 `/chat/stream`（`done` 事件前 + 生成器 `finally` 兜底）调用；**stream 路径 assistant 消息 = 完整 AIMessage 结构**（工具调用序列 + 文本，由 `on_tool_start` 事件捕获 name/args 填充 `tool_calls_json`，文本在 done 前取 agent 最终 state 而非仅 token 拼接）；`length` 截断的工具调用不重跑（既有语义，单测断言不重复落库）
4. **跨会话记忆提取**：`extractor.py`——触发：`chat_sessions.last_extracted_seq` 与 message_count 之差 ≥ `memory_extract_threshold_messages`（默认 20）；执行：取 `seq > last_extracted_seq` 的消息（**oldest-first，分批推进**，单批 ≤ `memory_extract_max_messages`）→ 增量摘要 prompt（`memory_extract.txt`，**`<previous-summary>` = 该 user 最近 N 条 entries 聚合文本**——无新表；输出条目 JSON `[{kind, content}]`，只保留用户偏好/事实/决定，禁止对话延续）→ 结果 Pydantic 校验 → upsert `chat_memory_entries`（**NFKC 归一后精确去重**，靠 `(user_id, kind, content_hash)` 唯一索引；近似去重留 Phase 4）→ **全部成功后才推进 `last_extracted_seq`**（幂等：水位推进后再失败不重复提取）；提取失败 → 记录失败时间戳，**退避 10 分钟重试**，不阻塞对话
5. **记忆注入**：**仅在会话首轮**（`chat_sessions`/`chat_messages` 均无该 (session_id,user_id) 历史，checkpoint `aget_tuple` 兜底判定）把该 user 最近 `memory_entries_per_user_limit` 条记忆（**总字符上限 2000**）作为**独立 context 消息**注入（role=user 前缀"用户记忆：…"或独立消息，**绝不改写 `req.message`**，`persist_turn` 不落此前缀）；读取经 `agent.main.context.get_current_user_id()`（无 user_id 参数可传）
6. **AGENTS.md 改造（多租户修复，代码级强制）**：`/memories/AGENTS.md` 只保留**系统级静态记忆**；**写回必须代码级禁止**——`MAIN_AGENT_SPEC` 装配 `FilesystemPermission(operations=["write"], paths=["/memories/AGENTS.md"], mode="deny")`（工具层拒绝 `edit_file` 写 AGENTS.md，而非仅靠 prompt 约束——deepagents 0.7.5 MemoryMiddleware 内置 `<memory_guidelines>` 会主动教唆写回，prompt 禁止语与框架指导并存时 LLM 行为不可控）；`agent/main/prompt.py` 的"长期记忆管理"整节同步改写（删除"记录重要用户信息到 AGENTS.md"语义）；MemoryMiddleware 读路径（`memory=["/memories/AGENTS.md"]`）保留，注入系统级静态记忆
7. **无状态智能体模式（交付面 E）**：`AgentSpec` 新增 `use_checkpointer: bool = True`；`REPORT_AGENT_SPEC`/`EVALUATION_AGENT_SPEC`/`RECOMMENDATION_AGENT_SPEC` 设 `False`（**main agent 与 PPT_AGENT_SPEC 保持 True**——checkpoint 恢复是既有 chat 功能，不得关闭）；`factory.py` 按 spec 决定是否 `build_checkpointer()`（False → `checkpointer=None`，deepagents 0.7.5 签名兼容）；单轮任务 = 一次性上下文注入 + 结果结构化返回；`skills-tools-architecture.md` 增补"无状态 vs 有状态智能体"章节
8. **settings**：`memory_extract_threshold_messages: int = 20`、`memory_entries_per_user_limit: int = 50`、`memory_extract_max_messages: int = 200`（单批上限）、`memory_extract_retry_after_seconds: int = 600`（失败退避）
9. **LLMTaskName**：+`MEMORY_EXTRACT = "memory_extract"`（复用 llm_model；提取输入含个人数据，**关闭/脱敏 LangSmith trace 记录**——P3 项，本阶段标注）
10. **runtime**：chat_session_repo 单例；chat 端点接入（`chat.py`）

**验证点**：
- 单测：`test_chat_session_repo.py`（CRUD + UNIQUE(session_id, seq) 冲突 + content_hash 去重）；`test_chat_persistence.py`（/chat 与 /chat/stream mock agent → 落库断言、崩溃中断不丢、幂等、匿名 user_id 跳过）；`test_memory_extractor.py`（阈值触发、增量幂等、user_id 隔离、坏输出重试、失败退避、oldest-first 分批）；`test_memory_injector.py`（**首轮注入/续轮不注入/跨 user 不注入/user_id 空不注入**）；`test_stateless_specs.py`（工厂断言 use_checkpointer=False 不建 checkpointer；invoke 后 checkpoint 无新增行——**tmp_path 隔离 checkpoint 路径**，mock settings 参照 test_main_agent_memory.py fixture 模式）
- 集成：chat 多轮 → SQL 查询 chat_messages 断言历史完整；构造 20+ 条消息 → 触发提取 → entries 生成 → 新会话首轮注入可见
- 回归：既有 chat 测试（`test_main_agent_memory.py` 的 prompt/AGENTS.md 字符串断言**同步更新**）、推荐/报告/评价测试全绿

**回退**：MySQL 不可用 → 写纪律降级为日志告警 + 会话仍正常对话（记忆为尽力而为）；提取失败 → 下轮重试，不阻塞对话。

### Step 10：评估方针骨架（Phase 2 首批 eval set）

**目标**：落地"LangSmith trace + eval set"评估体系的**第一批**（用户 2026-08-12 决策：Phase 2 只做首批，全量指标 Phase 4 在总 plan.md 记录）。覆盖四智能体关键断言式指标；LLM-as-judge / NDCG / monitor 看板留 Phase 4。

**新增文件**：`python/eval_sets/`（首批 4 集）、`python/eval/__init__.py`、`python/eval/runner.py`、`python/scripts/import_langsmith_dataset.py`、`python/tests/test_eval_runner.py`

**改动点**：

1. **eval_sets 格式**（JSONL，每行一个 case）：`{case_id, type, input, expected?: {intent?, tool_chain?}, assertions?: [{kind: "contains"|"not_contains"|"exact"|"numeric", field, value}], expected_chunk_ids?: []}`。首批 4 集：
   - `chat_intent.jsonl`：20 条主 agent 意图用例（推荐/报告/评价/知识库/闲聊/写作/图片），断言 = 期望路由工具链
   - `report_math.jsonl`：10 条加权/统计断言用例（输入科目等级 → 期望中间 JSON 数值，vs 手算）
   - `evaluation_comment.jsonl`：10 条评语用例，断言 = 评语中数值全部 ∈ 快照集合（复用数值引用核验闸逻辑做断言器）
   - `kb_retrieval.jsonl`：10 条检索用例（query → expected_chunk_ids 标注集 → Recall@k 断言）
2. **`eval/runner.py`**：读集 → 逐 case 调真实端点（`/api/v1/chat`、`/api/v1/report`、`/api/v1/evaluation`）或工具层函数（mock 模式可选）→ 收集 trace（LangSmith run_id）→ 断言器执行（contains/numeric/召回）→ 输出 `{case_id, pass, metrics, run_id, latency_ms}` 汇总 JSON + 终端表格。**断言式指标首批可跑**：意图路由正确率、report 数值正确率、评语数值引用违规率、检索 Recall@k、端到端延迟 P50/P95。
3. **LangSmith 关联**：`scripts/import_langsmith_dataset.py`——把 eval_sets JSONL 导入 LangSmith Dataset（`client.create_dataset(name="phase2-"+type)` + `create_examples`），trace 与 case 通过 run 输入匹配回链；Phase 4 的 LLM-as-judge 直接消费同一 Dataset。
4. **埋点契约**（与 Phase 4 的桥）：report 数值回填校验结果、evaluation 核验闸结果、LLMTaskName 全部已在 trace（Phase 2 已设计）；runner 输出的汇总 JSON 存 `python/eval/reports/<date>.json`（eval_runs 表 Phase 4 再建）。
5. **与 tests 的关系**：eval_sets 是数据驱动回归补充（`pytest` 不跑真实 LLM 的 eval 集；`runner.py` 独立运行，标记 `--smoke` 只跑断言式）；`run_kb_test.py` 保留，作为 kb_retrieval 集的前身。

**验证点**：
- `python eval/runner.py --set chat_intent --smoke`（mock 模式）→ 汇总 JSON 生成、断言器工作
- `python scripts/import_langsmith_dataset.py` → LangSmith 平台可见 Dataset（需 LANGCHAIN_API_KEY）
- 有库环境：`--live` 跑 report_math 真实链路 → 数值断言 100% 通过
- `pytest tests/test_eval_runner.py` 绿（runner 骨架 + 断言器单测）

**回退**：LangSmith 不可达 → runner 降级纯本地报告（无 run_id 关联）；eval_sets 断言失败 → 报告 FAIL 不阻塞业务交付。

---

## 4. 判定矩阵

| 试金石 | 通过条件 | 状态 |
|--------|---------|------|
| 轴 A report 端到端 | 真实样本 → 分类 4-6 → PDF/HTML 链接 + report_artifacts + token 下载 | ⏳ 待验证 |
| 轴 B report 防丢失 | 顺序打乱合并正确 + 缺科显式报错 + Journal 续跑单测 | ⏳ 待验证 |
| 轴 C LLM 填表防线 | 坏响应四类拦截 → 重试 → Jinja2 降级全链单测 | ⏳ 待验证 |
| 轴 D evaluation 端到端 | 摄入 → 快照 → 维度校验 → 雷达确定性 → 评语核验 | ⏳ 待验证 |
| 轴 E evaluation 同步 | 落库 + /me 只能读本人 + 历史 append | ⏳ 待验证 |
| 轴 F MCP 实装 | 注册表/发现/调用/熔断/降级 mock 全绿 + images 契约 | ⏳ 待验证 |
| 轴 G SSE 契约 | 两端点测试消费流断言事件序/done/error | ⏳ 待验证 |
| 轴 H 回归 | pytest `not slow` 全绿 + docker 构建通过 | ⏳ 待验证 |
| 轴 I chat 记忆 | 消息历史可查询 + 增量提取幂等 + user_id 隔离 + AGENTS.md 代码级禁写（FilesystemPermission deny）+ 注入仅首轮 | ⏳ 待验证 |
| 轴 J 无状态模式 | 三 spec 不建 checkpointer + .checkpoint.db 无新增行 + 单轮可用 | ⏳ 待验证 |
| 轴 K 评估骨架 | eval_sets 首批 4 集 + runner 断言式指标可跑 + LangSmith 导入脚本 | ⏳ 待验证 |

**判定**：十一条全过 → 本文件标 ✅，更新 `../plan.md` Phase 2 状态，进入 Phase 3（扩展/PPT/可靠性加固）。子项失败 → §6 降级回退。

---

## 5. 依赖与环境

### 5.1 settings.py 新增配置项

```python
# ── MinIO（report artifact 存储，Phase 2）──────────────
minio_endpoint: str = "localhost"
minio_port: int = 9002
minio_access_key: str = "minioadmin"
minio_secret_key: str = "minioadmin"
minio_secure: bool = False
minio_report_bucket: str = "report-artifacts"
minio_connect_timeout: float = 3.0        # 探测/超时，超时自动走本地兜底

# ── report（教师端批量成绩单）──────────────────────────
report_download_ttl_hours: int = 24        # token 下载链接有效期
report_download_secret: str = ""           # HMAC 签名密钥（.env 注入，空则启动告警并禁用下载端点）
report_max_file_mb: int = 10               # 单 Excel 上限
report_max_files: int = 20                 # 一次批量文件数上限
report_render_concurrency: int = 4         # 渲染并发（WeasyPrint 同步 CPU 密集：asyncio.to_thread + Semaphore）
report_llm_fill_concurrency: int = 4       # LLM 填表/综合评语并发
report_student_timeout_seconds: float = 60 # 单学生全链超时

# ── evaluation（教师端生成 → 学生端同步）──────────────
evaluation_radar_axis_count: int = 5        # 雷达轴数（硬约束：维度提案必须恰为 N 个，schema 校验）

# ── MCP 服务器注册表（Phase 2，三服务器占位）────────────
# 格式：{"server_name": {"transport": "streamable_http", "url": "...", "api_key_env": "...", "namespace": "search"}}
# pydantic-settings 从 .env 注入 dict 需 JSON 字符串（如 MCP_SERVERS='{"tavily":{...}}'）
mcp_servers: dict = {}

# ── 视觉模型────────
vision_model: str = "qwen3-vl-plus"

# ── chat 长期记忆（Phase 2 新增，pi 机制移植）───────────
memory_extract_threshold_messages: int = 20  # 消息数达阈值触发跨会话记忆提取
memory_extract_max_messages: int = 200       # 单批提取最大消息数（oldest-first 分批推进）
memory_extract_retry_after_seconds: int = 600 # 提取失败退避间隔
memory_entries_per_user_limit: int = 50      # 新会话注入的记忆条目上限（总字符 ≤2000）
```

`.env` 需新增：`MINIO_*`、`REPORT_DOWNLOAD_SECRET`、`TAVILY_API_KEY`、`TAVILY_MCP_URL`（占位）、`JIMENG_API_KEY`、`JIMENG_MCP_URL`（占位，用户提供）、`E2B_API_KEY`、`E2B_MCP_URL`（占位）、`MCP_SERVERS`（JSON 字符串，可选覆盖）。**凭据永不入库**（`.gitignore` 维持）。

### 5.2 requirements.txt

`+openpyxl>=3.1`；其余（`minio`/`jinja2`/`weasyprint`/`python-docx`/`langchain-mcp-adapters`/`pypdf`/`pymupdf`/`tavily-python`）已列，Step 1 验证 venv 装齐。

### 5.3 文件清单

| 路径 | 动作 | 说明 |
|------|------|------|
| `python/config/settings.py` | 改 | §5.1 配置组 |
| `python/requirements.txt` | 改 | +openpyxl |
| `python/Dockerfile` | 改 | WeasyPrint 系统依赖 |
| `sql/init-db.sql` | 改 | +report_artifacts +evaluation_records |
| `python/ai/llm_task_name.py` | 改 | +5 枚举（含 MEMORY_EXTRACT） |
| `python/ai/llm_client.py` | 改 | model/base_url/api_key/enable_thinking 覆盖参数（默认行为不变） |
| `python/storage/minio/minio_repo.py` | 新增 | MinIO 封装 + 本地兜底寻址 |
| `python/storage/mysql/report_artifact_repo.py` | 新增 | report_artifacts CRUD |
| `python/storage/mysql/evaluation_repo.py` | 新增 | evaluation_records CRUD |
| `docker-compose.yml` | 改 | minio 暴露端口 + python-api env 注入 |
| `python/tools/report/parse_score_excels.py` | 新增 | 表头驱动解析（合并单元格感知） |
| `python/tools/report/merge_students.py` | 新增 | 键合并 + 差集校验 + 中间形态 JSON |
| `python/tools/report/fill_report_html.py` | 新增 | LLM 填充 + 校验 + Jinja2 降级 |
| `python/tools/report/generate_subjective_eval.py` | 新增 | 综合评语生成器 |
| `python/tools/report/render_report_batch.py` | 新增 | A-shell 确定性执行工具 + 进度 channel + 取消 |
| `python/tools/report/inspect_score_excels.py` | 新增 | 文件摘要（分类节点输入） |
| `python/tools/report/prompts/{fill_template,subjective_eval}.txt` | 新增 | 提示词文件 |
| `python/templates/report/grade4-6.html` | 新增 | 自 `1.html` 迁移 + 锚点 + 评语区 |
| `python/templates/report/grade1-3.html` | 新增 | 骨架占位（待用户模板替换） |
| `python/agent/report/service.py` | 新增 | report 编排门面（四决策点循环） |
| `python/api/report.py` | 改 | SSE 实装 + 注册 + token 下载端点 |
| `python/tools/evaluation/get_academic_snapshot.py` | 新增 | 快照工具（确定性直查 metadata_json） |
| `python/tools/evaluation/design_dimensions.py` | 新增 | 维度提案（schema 硬校验） |
| `python/tools/evaluation/compute_radar_values.py` | 新增 | 雷达数值（metric 枚举代码实现） |
| `python/tools/evaluation/generate_comment.py` | 新增 | 评语生成 + 数值引用核验 |
| `python/tools/evaluation/prompts/{dimension_design,comment}.txt` | 新增 | 提示词文件 |
| `python/agent/evaluation/service.py` | 新增 | evaluation 编排门面（五层管线） |
| `python/api/evaluation.py` | 改 | SSE 教师端 + /me 学生端 + 注册 |
| `python/tools/mcp_client.py` | 改 | 实装（注册表/懒连接/适配器/每服务器熔断） |
| `python/tools/chat/web_search.py` | 改 | MCP 主路 + tavily 直连兜底 |
| `python/tools/image/image_generate.py` | 改 | 即梦 MCP 工作流 |
| `python/tools/image/image_recognize.py` | 新增 | 视觉直连（qwen3-vl-plus） |
| `python/tools/code/code_interpreter.py` | 改 | E2B MCP + 本地沙箱兜底 |
| `python/tools/chat/writing_assistant.py` | 改 | LLM 实装 |
| `python/tools/mindmap/mindmap_generator.py` | 改 | LLM DSL + 本地渲染 |
| `python/api/chat.py` | 改 | ChatRequest.images + 记忆写纪律接入（Step 9） |
| `python/agent/app.py` | 改 | include_router(report/evaluation) |
| `python/agent/runtime.py` | 改 | 注册新工具 + MCP + chat_session_repo 单例 |
| `python/agent/main/specs.py` | 改 | REPORT/EVALUATION_AGENT_SPEC 更新 + image_recognize 入 main allowlist + `use_checkpointer` 字段（无状态三 spec 设 False）；**从 MAIN_AGENT_SPEC.allowed_tools 移除 compute_weighted_grade**（stub 抛 NotImplementedError，避免 chat 埋雷） |
| `python/agent/main/factory.py` | 改 | 按 `spec.use_checkpointer` 决定是否 build_checkpointer（False → None）；`MAIN_AGENT_SPEC` 装配 FilesystemPermission deny write（AGENTS.md 代码级禁写） |
| `python/agent/main/prompt.py` | 改 | MAIN_AGENT_SYSTEM_PROMPT 增补"图片附件可调 image_recognize"声明 + "长期记忆管理"整节改写（删除用户级写回语义，与框架 `<memory_guidelines>` 去冲突） |
| `python/storage/mysql/chat_session_repo.py` | 新增 | chat_sessions/chat_messages/chat_memory_entries CRUD + per-session 并发锁 + content_hash 去重 |
| `python/agent/memory/persistence.py` | 新增 | 写纪律：persist_turn 逐条落库 + 原子自增 seq + 匿名跳过 |
| `python/agent/memory/extractor.py` | 新增 | 增量摘要记忆提取（阈值触发/oldest-first 分批/幂等水位/失败退避） |
| `python/agent/memory/injector.py` | 新增 | 记忆注入（仅首轮判定/独立 context 消息/字符上限） |
| `python/agent/memory/prompts/memory_extract.txt` | 新增 | 记忆提取提示词（`<previous-summary>` 更新式 + 条目 JSON 约束） |
| `python/memories/AGENTS.md` | 改 | 降级为系统级静态记忆（删除用户级写回语义，多租户修复） |
| `python/tools/documents/desensitizer.py` | 改 | 结构化提取（摄入管线 B 方案） |
| `python/scripts/ingest_transcript_desensitized.py` | 改 | 落 metadata_json + 重灌 |
| `python/agent/documents/service.py` | 改 | 摄入 metadata_json 写入 |
| `python/storage/mysql/document_repo.py` | 改 | 新增 `get_chunks_by_user`（JSON_EXTRACT user_id 过滤）；既有 `get_chunk_contents` 保持不动 |
| `python/skills/report-generation/SKILL.md` | 改 | 新契约改写 |
| `python/skills/evaluation-writing/SKILL.md` | 改 | 反幻觉规则改写 |
| `python/skills/image-generation/SKILL.md` | 新增 | 即梦 MCP 工作流 + client 配置 |
| `python/skills/web-search/SKILL.md` | 改 | MCP 版 |
| `python/skills/writing/SKILL.md` | 改 | 实装版 |
| `docs/v2.0.0/tools/*.md` | 改 | 6 个工具文档同步 + image_recognize.md 新增 |
| `python/tests/`（21 个新文件） | 新增 | §3 Step 8/9/10 清单 19 个 + `test_llm_client_defaults.py` + `test_report_contract.py` |
| `python/eval_sets/chat_intent.jsonl` 等 4 集 | 新增 | 首批 eval set（Step 10） |
| `python/eval/runner.py` + `__init__.py` | 新增 | 断言式指标运行器（Step 10） |
| `python/scripts/import_langsmith_dataset.py` | 新增 | eval_sets → LangSmith Dataset 导入（Step 10） |
| `python/tests/fixtures/` | 新增 | 道法样本拷贝（测试夹具） |
| `.env.example` | 改 | MINIO/MCP 占位 |

---

## 6. 回退策略（子项降级）

| 子项失败 | 回退方案 | 影响 |
|---------|---------|------|
| WeasyPrint 装不上/渲染失败 | HTML 兜底为主交付，PDF 标记降级（同模板锚点双渲染） | 下载格式降为 html |
| 多科 Excel 表头不兼容 | 表头配置化（`report_header_profile`）样本驱动补配 | 新样本需补配置 |
| LLM 填表连续失败 | CircuitBreaker 熔断 → 全批 Jinja2 确定性填充 | 交付不失败，评语区为空 |
| 综合评语失败 | 评语区留空 + trace 记录 | 单学生无评语 |
| 分类 LLM 失败/冲突 | 规则兜底（道法/特征列/文件名年级）直通 | 决策点降级为规则 |
| MinIO 不可用 | 本地 `python/.documents/reports/` 兜底，下载寻址透明 | 无影响（单机） |
| 即梦 MCP 不可达 | 结构化 error（不伪造图片） | image_generate 不可用 |
| tavily MCP 不可达 | 直连 tavily SDK 兜底 → error | web_search 降级 |
| E2B 不可达/无 key | 本地 Docker 受限沙箱 → error | code_interpreter 降级 |
| 摄入 metadata_json 缺失 | 正则回退解析正文 → error | evaluation 明确报错不空跑 |
| 维度/评语 LLM 层熔断 | 默认维度 + 规则化评语（status="fallback"） | 学生端仍可读 |

---

## 7. 与总 plan / 决策的衔接

- **本文件**：`docs/v2.0.0/plans/phase-2-report-evaluation.md`
- **总 plan 引用**：`../plan.md` 第 115 行 `plans/phase-2-report-evaluation.md（待生成）` 应更新为已生成 + 状态
- **决策衔接**：
  - 决策 5：成绩统计智能体（/report）+ 评价寄语（/evaluation）——本阶段交付（形态按 grill-me 修订：report=教师端批量、evaluation=教师端生成同步学生端）
  - 决策 7：skills/tools 分层——report/evaluation 工具与 SKILL.md 按原则落地
  - 决策 9：推荐共享 tool——不动
  - 决策 10：混合入口——前端后置，本阶段只定契约
  - 决策 11/12：可靠性——compaction 已在 Phase 1；本阶段补链路断裂兜底/幻觉兜底的工程实现（填表降级/核验硬闸/熔断），checkpoint 恢复演示留 Phase 4
  - 决策 13：API 端点——`/report`、`/evaluation` 本阶段注册
  - 决策 16/17/18：前端页面/能力边界——image 生成走 MCP（即梦）按决策 17 独立页语义，但页面本身 Phase 3；写作在 chat 内（决策 18）
  - 决策 8（跨语言）：Java 后置 Phase 3/4（本阶段不建）
- **需求.md 衔接**：新增需求 §1（tools/skills 公共抽取，Phase 1 已做，本阶段按契约改写 SKILL.md）、§3（通用 chat 插件体系——本阶段提前实装）、知识库 RAG 评估指标（本阶段为 Phase 4 埋点：report/evaluation 校验结果与 trace 字段即数据源）
- **pi 思想落点**（学习自 `E:\Agent\pi`，subagent 调研）：错误分类+双层重试（LLM 调用统一超时/熔断）、schema 校验失败回灌（维度提案/评语）、确定性计算与 LLM 分离（统计/雷达/合并）、部分结果保留（逐学生隔离 + Journal）、批量终止语义（render 工具整批返回、失败不误杀同批）、事件流协议（进度 channel 与 SSE 合流）、截断即拒绝（填表输出结构校验）。

### 7.1 Phase 2 范围切割决策（grill-me 沉淀，2026-08-12）

| # | 决策点 | 用户选择 |
|---|--------|---------|
| 1 | report/evaluation 场景分离 | report=教师端批量成绩单（image-2/3 业务参考）；evaluation=教师端生成→同步学生端（image/image-1 业务参考）；image 仅参考不照搬 |
| 2 | report 交付形态 | PDF 优先（WeasyPrint）+ HTML 兜底；链接失效报错=生成期 `student_error` + 访问期 token 端点结构化错误 |
| 3 | report LLM 参与度 | 纯确定性管线（解析/统计/合并/校验零 LLM）；LLM 仅 2 处：模板填充 + 综合评语 |
| 4 | report 执行模型 | **A-shell**：deep agent 壳 + `render_report_batch` 确定性工具 + 内部进度 channel；done 负载由工具结果装配不采信 LLM 文本 |
| 5 | 存储 | MinIO `report-artifacts`（新 `storage/minio/minio_repo.py`）+ 本地兜底；下载=自托管 HMAC token 端点（24h）；`report_artifacts` 专用表 |
| 6 | Excel 入参契约 | 多科一文件，表头与字段一致（双层合并表头动态解析，只取等级列丢分数/备注），openpyxl 确定性解析，中间形态 JSON `{students:[{class,name,score:[{subject,...}]}]}` |
| 7 | 防信息丢失 | 6 道闸：数据不过 LLM / (学号,姓名,班级) 键合并+差集校验 / 两阶段渲染断言 / Journal 落盘 / 只留等级 / 幂等 batch_id |
| 8 | 分类编排 | deep agent 四决策点循环（①完备性 ②确定性摘要 ③年级分类 LLM+规则兜底+unknown 反问 ④异常处置不得静默 ⑤执行 ⑥汇总）；LLM 重试类决策不交 LLM（规则+trace） |
| 9 | 模板来源 | 用户提供 `1.html`（4-6 年级版）迁移 + 锚点规范；grade1-3 骨架占位待用户提供 |
| 10 | 综合性评价 | 报告单尾部"学生综合评价"评语区，LLM 主观评语（`REPORT_SUBJECTIVE_EVAL`，skill+提示词规范，失败留空不阻塞） |
| 11 | HTML 填充 | **LLM 填模板**（FastGPT 同款提示词 + 锚点约束）为主，Jinja2 确定性降级；输出结构+数值回填双校验，错误回灌重试 1 次 |
| 12 | LLM 配置 | **复用现有 llm_model**（不新建配置组）；`build_chat_openai` 扩展覆盖参数；填表 `max_tokens=8192, temperature=0.1` |
| 13 | 年级信息来源 | 无独立 grade_hint 字段：文件名 regex + 行3 班级 + 用户消息（LLM 提取）；`/report` 留可选 `user_message` |
| 14 | evaluation 数据读取 | **改造摄入管线**：结构化数据落 `document_chunks.metadata_json`（列已存在零 schema 变更）+ 存量重灌；快照确定性直查 |
| 15 | 雷达维度 | **LLM 设计评价体系** + 反幻觉工程化五层；metric 枚举 5 个（weighted_gpa/stability/top_subject/pass_rate/credit_load）；评语核验硬闸；轴数 N=5 |
| 16 | comment_type | 显式必选 4 枚举（semester_summary/encouragement/improvement_advice/recommendation） |
| 17 | 同步机制 | `evaluation_records` 表（target_user_id/comment_type/radar_json/comment/status/generated_by）；教师端 POST 生成落库；学生端 GET /me（context user_id 强匹配只能读自己）；历史 append |
| 18 | 前端范围 | Phase 2 不做页面，只定契约（ChatRequest.images + 两端点 SSE 协议）；MainPage 等后续统一开发 |
| 19 | Java 数据服务 | **后置 Phase 3/4**（身份体系/业务数据 API/MQ）；Phase 2 不动存储层，身份隔离临时口径 |
| 20 | web_search | 提前到 Phase 2，**MCP 方式实装**（tavily 官方 MCP 主路 + 直连 SDK 兜底） |
| 21 | 图片生成 | **即梦 AI MCP**（`image/*` 命名空间，URL/凭据用户提供 plan 留占位）；tool + image-generation SKILL.md 指定工作流与 client 配置 |
| 22 | MCP 全景 | 三第三方 MCP（tavily/jimeng/e2b）+ image_recognize 直连 qwen3-vl-plus；mcp_client 实装（注册表/懒连接/适配器/每服务器熔断）；写作/脑图无 MCP |
| 23 | memory 现状诊断 | 用户确认"memory 约等于没做"：AGENTS.md 单文件共享（多租户泄漏）、写回靠 agent 自觉、SqliteSaver 不可查询、session_id 默认 default |
| 24 | chat 长期记忆形态 | 会话记录持久化 = `chat_sessions` + `chat_messages`（append-only、UNIQUE(session_id,seq)）+ 跨会话记忆 `chat_memory_entries`（user_id 隔离）；增量摘要提取（pi `<previous-summary>` 更新式 + 固定条目格式 + 幂等 last_extracted_seq） |
| 25 | 记忆注入与写纪律 | 新会话注入该 user 最近 N 条记忆；逐条落库 + turn 边界 flush + 崩溃保守（pi 写纪律）；提取失败下轮重试不阻塞 |
| 26 | AGENTS.md 定位 | 降级为系统级静态记忆（项目背景/技能索引）；用户级记忆全部走表；**写回由 FilesystemPermission deny 代码级禁止**（非仅 prompt 约束——框架 `<memory_guidelines>` 会主动教唆写回） |
| 27 | 无状态智能体模式 | AgentSpec 加 `use_checkpointer`；report/evaluation/recommend 设 False（main/PPT 保持 True）；一次性上下文注入 + 结果结构化回收（pi `--no-session`/in-memory 模式）；写进 skills-tools-architecture |
| 28 | 记忆注入时机与隔离 | 注入仅在会话首轮（chat 表无历史 + checkpoint 兜底）、独立 context 消息不改写 user_msg、persist 只落原始消息；匿名 user_id 跳过持久化/提取/注入；get_or_create_session 以 (session_id,user_id) 复合键防串会话 |
| 29 | 记忆提取闭环 | `<previous-summary>` = 该 user 最近 N 条 entries 聚合（无新表）；水位推进固化"校验→全部 upsert 成功→才推进"；NFKC 精确去重（content_hash 唯一索引）；oldest-first 分批；失败退避 600s |
| 30 | deepagents 版本锁定 | requirements 锁 `deepagents>=0.7.5,<0.8`（本阶段依赖 0.7.5 的 checkpointer=None/MemoryMiddleware/FilesystemPermission 语义，防升级漂移） |
| 31 | 评估方针范围切割 | Phase 2 只做**首批 eval set**（eval_sets 4 集 + runner 断言式指标 + LangSmith 导入）；全量指标（LLM-as-judge/NDCG/monitor 看板）在总 plan.md 记录为 Phase 4 |
| 32 | vision_model 选型 | `qwen3-vl-plus`（用户 2026-08-13 确认，替换 qwen3.7-plus；与文本模型同 base_url/api_key） |
| 33 | MinIO 凭据 | 共享实例密码统一 `123456`（与 mysql 一致）；milvus 同步配 MINIO_ACCESS_KEY/SECRET；宿主暴露 9002/9002；`.env` 注入 REPORT_DOWNLOAD_SECRET |

### 7.2 Phase 3 输入清单（本阶段推迟项）

| 项 | Phase 3 待做 |
|----|-------------|
| 前端统一开发 | MainPage（chat+recommend+report+evaluation 入口）、ReportPage（上传/进度/下载/重试）、EvaluationPage（雷达图 ECharts + 评语流）、ImageGeneratePage/PPTGeneratePage、导航重构 |
| Java 数据服务 | 用户身份体系+鉴权（身份隔离正式落点）、业务数据 API、MQ 异步任务、Redis 运维；桥接走 ToolRegistry+CircuitBreaker（`data_service` 工具类别） |
| FastGPT | 按需评估（需求.md 当前排除） |
| PPT 生成系统 | `ppt_generate`（OpenMAIC 参考） |
| 可靠性加固 | RedisSaver、OpenTelemetry、harness 可视化、链路断裂/幻觉兜底演示 |
| 插件市场 | MCP 动态发现接入外部插件（allowlist 门控） |

---

## 9. 数据库与建表（新增 DDL）

```sql
-- ------------------------------------------------------------ report_artifacts
-- report（教师端批量成绩单）产物元数据：一学生一行，支持失败重试/下载寻址/审计
CREATE TABLE IF NOT EXISTS report_artifacts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id VARCHAR(32) NOT NULL,
    student_id VARCHAR(64) NOT NULL,
    student_name VARCHAR(128) NOT NULL DEFAULT '',
    format VARCHAR(8) NOT NULL DEFAULT 'pdf',          -- pdf | html
    status VARCHAR(16) NOT NULL DEFAULT 'ok',           -- ok | failed
    file_key VARCHAR(512) NOT NULL DEFAULT '',          -- MinIO 对象键或本地相对路径
    token_expires_at DATETIME DEFAULT NULL,             -- 下载 token 过期时间（TTL 校验落点）
    error_code VARCHAR(64) DEFAULT '',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_report_artifacts_batch (batch_id),
    INDEX idx_report_artifacts_student (student_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------ evaluation_records
-- evaluation（教师端生成 → 学生端同步）评价档案：append 保留历史，学生端只读本人
CREATE TABLE IF NOT EXISTS evaluation_records (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    target_user_id VARCHAR(64) NOT NULL,
    comment_type VARCHAR(32) NOT NULL,                 -- semester_summary|encouragement|improvement_advice|recommendation
    radar_json JSON,                                   -- 维度提案 + 确定性雷达值
    comment TEXT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'generated',   -- generated | fallback
    generated_by VARCHAR(64) DEFAULT '',               -- 教师 user_id（临时口径，不校验）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_evaluation_user_time (target_user_id, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------ chat_sessions
-- chat 会话元数据：会话归属/统计/记忆提取水位（last_extracted_seq 幂等标记）
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL DEFAULT '',
    message_count INT NOT NULL DEFAULT 0,
    last_extracted_seq INT NOT NULL DEFAULT 0,          -- 记忆提取水位（增量幂等）
    status VARCHAR(16) NOT NULL DEFAULT 'active',        -- active | closed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_chat_sessions_user (user_id, updated_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------ chat_messages
-- chat 会话记录（append-only）：用户当前通话的消息历史，可查询/可审计/是记忆提取源
CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    seq INT NOT NULL,
    role VARCHAR(16) NOT NULL,                           -- user | assistant | tool
    content MEDIUMTEXT,
    tool_calls_json JSON,                                -- assistant 工具调用（审计）
    usage_json JSON,                                     -- token 统计（Phase 4 指标源）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_chat_messages_session_seq (session_id, seq),
    INDEX idx_chat_messages_user (user_id, seq),
    INDEX idx_chat_messages_session (session_id, seq)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------ chat_memory_entries
-- 跨会话长期记忆：按 user_id 隔离，新会话首轮注入；AGENTS.md 不再承载用户级内容
CREATE TABLE IF NOT EXISTS chat_memory_entries (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    kind VARCHAR(16) NOT NULL DEFAULT 'fact',            -- preference | fact | decision
    content TEXT NOT NULL,
    content_hash CHAR(32) NOT NULL,                      -- NFKC 归一后 md5（精确去重键）
    source_session_id VARCHAR(64) NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_memory_dedup (user_id, kind, content_hash),
    INDEX idx_memory_entries_user (user_id, updated_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

## 10. 外部依赖（待用户提供）

1. **即梦 AI MCP**：server URL + `JIMENG_API_KEY`
2. **E2B**：账号/`E2B_API_KEY`（或确认本地 Docker 沙箱为主）
3. **Tavily MCP**：server URL（或确认官方 streamable-http 地址）+ `TAVILY_API_KEY`
4. **一年级模板**（grade1-3 样式，综合测评表）——未到则骨架占位
5. **更多学科 Excel 样本**（验证动态表头解析通用性，当前仅道法 1 份）
6. **成绩单重灌授权**：`ingest_transcript_desensitized.py --user-id <id> --name <姓名>` 重跑（覆盖存量数据）
