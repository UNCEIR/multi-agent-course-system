# Phase 2 编码实施计划 — report / evaluation / 主 Agent 插件 MCP

> 本文档是 `plans/phase-2-report-evaluation.md`（业务与技术栈详细计划）的**编码执行清单**：按工作流拆解为可落地的编码任务（文件级），带依赖顺序与验证命令。编码时以本文件为任务主索引，设计细节（契约/事件协议/防线机制）回查详细计划。
>
> 日期：2026-08-12
> 状态：✅ 编码完成（2026-08-13）——W-A~W-J 全部落地，`pytest -m "not slow"` = 235 passed；docker 重建验收 + 端到端冒烟待执行（见 §十二）
> 验收：八条试金石（详细计划 §1.4 / §4），全绿 = Phase 2 GO

## 一、概览

### 1.1 工作流划分与依赖

```
W-A 基建 ──┬─→ W-B report 解析合并 ─→ W-C 模板与填充 ─→ W-D report 编排与 API
           ├─→ W-E evaluation 数据基准 ─→ W-F evaluation 编排与 API
           ├─→ W-G MCP 插件（独立可并行）
           └─→ W-I 记忆机制（chat 长期记忆 + 无状态模式，依赖 W-A）
                           └─→ W-H 全量回归与验收（全部前置）
```

| 工作流 | 内容 | 依赖 | 阶段产物 |
|--------|------|------|---------|
| W-A | settings/依赖/Dockerfile/建表/LLM 扩展/MinIO/compose | 无 | 底座可用 |
| W-B | 表头驱动解析 + 键合并 + Journal（零 LLM） | W-A | 中间形态 JSON 工具 |
| W-C | 模板锚点 + LLM 填充 + 校验 + Jinja2 降级 + 综合评语 | W-B | 渲染工具 |
| W-D | 四决策点循环 + render_report_batch + SSE + 下载端点 | W-A/B/C | `/api/v1/report` |
| W-E | 摄入管线 metadata_json + 快照工具 | W-A | evaluation 数据基准 |
| W-F | 五层反幻觉管线 + 落库 + 学生端读取 | W-A/E | `/api/v1/evaluation` + `/me` |
| W-G | mcp_client 实装 + 三 MCP + 五插件工具 | W-A | main agent 插件 |
| W-I | chat 会话记录持久化 + 跨会话记忆提取 + 无状态智能体模式 | W-A | 记忆机制（交付面 D/E） |
| W-J | 评估方针骨架：eval_sets 首批 4 集 + runner + LangSmith 导入 | W-A | 评估体系起点（交付面 F） |
| W-H | 21 个新测试文件 + 全量回归 + docker 验收 | 全部 | 十一条试金石 |

### 1.2 编码纪律

- 所有 ChatOpenAI 构造走 `ai.llm_client.build_chat_openai`（AGENTS.md 硬约束），新 LLM 调用必须带 `LLMTaskName`
- 工具错误返回 `isError` 结构化结果（`{code, message}`），不抛异常
- 新前端 API 必须 SSE：`done` 终结 + 结构化 `error`
- 测试 marker 只用既有 `unit/integration/slow/agent/api`
- 每工作流结束跑 `cd python; python -m pytest tests/ -m "not slow" -q`，保持全绿再进下一工作流

---

## 二、工作流 A：基建

**目标**：Phase 2 全部底座，8 个子任务。

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| A1 | settings 配置组 | `python/config/settings.py` | 见详细计划 §5.1：`minio_*` / `report_*`（含 `report_download_secret`）/ `evaluation_radar_axis_count` / `mcp_servers`（dict 默认 `{}`，env 注入用 JSON 字符串）/ `vision_model`（默认 `qwen3-vl-plus`，与文本模型同 base_url/api_key；开工冒烟验证多模态输入，不兼容则退 `qwen3-vl-plus-2025-12-19`）；`report_header_profile`（表头配置化兜底位，先空） |
| A2 | requirements | `python/requirements.txt` | `+openpyxl>=3.1`；核对 minio/jinja2/weasyprint/langchain-mcp-adapters |
| A3 | Dockerfile | `python/Dockerfile` | pip install 前 `apt-get update && apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info fonts-noto-cjk`（**fonts-noto-cjk 必须**：slim 镜像无中文字体 → PDF 豆腐块，试金石 1 直接失败） |
| A4 | 建表 | `sql/init-db.sql` | 追加 `report_artifacts` + `evaluation_records`（详细计划 §9 DDL 原样）；文件头表清单注释同步 |
| A5 | LLMTaskName | `python/ai/llm_task_name.py` | +`REPORT_HTML_FILL`/`REPORT_SUBJECTIVE_EVAL`/`EVALUATION_DIMENSION_DESIGN`/`VISION_ANALYZE` |
| A6 | llm_client 扩展 | `python/ai/llm_client.py` | `_create_chat_openai` 加 `model/base_url/api_key/enable_thinking` 可选覆盖（None=取 settings）；`build_chat_openai` 透传；**默认行为零变化**（写回归测试断言） |
| A7 | MinIO 访问层 | `python/storage/minio/__init__.py` + `minio_repo.py` | `ensure_bucket/upload/download/exists/delete`；连接探测 3s 超时；本地兜底 `python/.documents/reports/<batch_id>/`（统一寻址函数 `locate(key)`） |
| A8 | docker-compose + env | `docker-compose.yml`、`.env.example` | minio 暴露 9000/9001；python-api env 注入 `MINIO_*`（从 .env 读）；`.env.example` 补 MINIO/TAVILY/JIMENG/E2B 占位 |

**验证**：
```bash
cd python && python -m compileall config/ ai/ storage/minio/
cd python && python -m pytest tests/ -m "not slow" -q        # 回归不破
docker compose up -d --build && docker compose ps            # 构建含 WeasyPrint 依赖
python -c "from ai.llm_client import build_chat_openai; build_chat_openai(temperature=0.1, max_tokens=128)"
```

**风险卡点**：WeasyPrint 系统依赖装不上 → 记录降级（HTML 主交付），不阻塞。

---

## 三、工作流 B：report 解析与合并（零 LLM 核心）

**目标**：真实样本可解析、可合并、可校验、可续跑。

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| B1 | 子包骨架 | `python/tools/report/__init__.py` | **改**（已存在，现导出 compute_weighted_grade）：追加导出 parse_score_excels/merge_students/contract（后续步骤补 render 相关） |
| B2 | 样本夹具 | `python/tests/fixtures/道法四7班.xlsx` | 从仓库根拷贝真实样本（二进制；含真实学生姓名，入库隐私按 P3-7 处理：fixtures 目录加入 `.gitignore` 说明或使用脱敏副本） |
| B3 | 表头驱动解析 | `python/tools/report/parse_score_excels.py` | `@tool(args_schema=ParseScoreExcelsInput{file_keys})`；`parse_workbook(path) -> ParsedFile{subject, class_name, semester, grade_columns, students:[{student_id,name,grades:{dim:val}}]}`；sheet 选择规则（学号+姓名表头 + 有数据行）；merged_cells 列模型；行3 班级/学科提取 + 文件名兜底；只取 `等级` 子列；NFKC 归一；错误按 `(file,sheet,row,reason)` 结构化 |
| B4 | 合并器 | `python/tools/report/merge_students.py` | `merge_files(parsed_files) -> MergedStudents{batch_id, semester, students:[{student_id,class,name,score:[{subject,...}]}], warnings:[...]}`；主键 学号 → 回退 (班级,姓名)；跨文件差集告警 |
| B5 | 校验与 Journal | `merge_students.py`（同文件） | `assert_integrity(merged, file_count)`（学生数/每生科目数）；`journal_save(batch_dir, merged)` / `journal_load(batch_dir)`；逐文件合并即写盘 |
| B6 | 中间形态契约常量 | `python/tools/report/contract.py`（新） | JSON 字段名/值域/错误码枚举常量（`render_failed/fill_failed/parse_failed/upload_failed/grade_invalid/merge_conflict`）；**学科/维度别名映射**：`SUBJECT_ALIAS`（道法↔道德与法治、语文↔语文…按 1.html 学科名建全表）、`DIMENSION_ALIAS`（考试性评价70分↔卷面成绩、综合性评价100分↔期末总评、综合答辩↔综合答辩、学科实践↔学科实践…）——**数值回填校验与模板锚点的匹配依据**（P0-5），供 B/C/D 共用并配单测 |

**验证**：
```bash
cd python && python -m pytest tests/test_report_parse_score_excels.py tests/test_report_merge_students.py -v
```
断言：道法样本等级列 C/E/G/J/L 值正确、分数/备注丢弃、sheet 选对、行3=四（7）班/道法；两科文件顺序打乱合并正确；缺学号/键冲突结构化错误。

---

## 四、工作流 C：模板与填充

**目标**：两模板 + LLM 填充器 + 双校验 + Jinja2 降级 + 综合评语。

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| C1 | 模板目录 | `python/templates/report/` | 目录 + `__init__.py`（无内容，仅标记） |
| C2 | grade4-6 模板 | `python/templates/report/grade4-6.html` | 自仓库根 `1.html` 迁移；班级/姓名 input → `<span class="fill" data-slot="class|name"></span>`；12 学科块可填格 → `data-slot="<subject>|<dimension>|grade"`（**subject/dimension 用 1.html 的学科名与子维度名**——如 `道德与法治|期末总评|grade`，与 B6 别名映射配对，Excel 侧名经 `SUBJECT_ALIAS`/`DIMENSION_ALIAS` 归一后匹配）；表格后追加 `<div class="comment-section" data-slot="comment"></div>` |
| C3 | grade1-3 骨架 | `python/templates/report/grade1-3.html` | 按综合测评表结构骨架（过程性/展示性必选+自选/综合性评价），锚点同规范；待真实模板替换 |
| C4 | 填充提示词 | `python/tools/report/prompts/fill_template.txt` | 复刻 FastGPT 约束（模板不可删改/只填锚点/没给到留空/评语区不动/只输出 HTML）+ 锚点填写规则说明 |
| C5 | LLM 填充器 | `python/tools/report/fill_report_html.py` | `fill_one(template_html, student_json, llm) -> html`；`build_chat_openai(max_tokens=8192, temperature=0.1, task_name=REPORT_HTML_FILL)`；错误回灌重试 1 次（差异明细回填 prompt） |
| C6 | 输出校验 | `fill_report_html.py` | `validate_structure(html, template)`：标签闭合栈校验 + 锚点全集存在性 + comment 槽存在；`validate_backfill(html, student_json)`：提取各 data-slot 文本与源 JSON 逐字段比对 |
| C7 | Jinja2 降级器 | `fill_report_html.py` | `fill_with_jinja2(template_html, student_json) -> html`（确定性锚点替换）；同过结构校验 |
| C8 | 综合评语 | `python/tools/report/generate_subjective_eval.py` | `generate(subject_grades_json) -> str`；prompt `subjective_eval.txt`（只基于给定等级/禁止编造科目数字/30-80字/语气规范）；60s 超时；失败返回 `""`（留空不阻塞） |
| C9 | SKILL.md 改写 | `python/skills/report-generation/SKILL.md` | 新契约：多文件上传→分类→生成链接列表；LLM 只填表不计算；失败兜底链 |

**验证**：
```bash
cd python && python -m pytest tests/test_report_fill_html.py tests/test_report_subjective_eval.py -v
```
坏响应四类（改模板/漏填/填错等级/截断）→ 拦截 → 重试 → Jinja2 降级；Jinja2 产物与 LLM 产物同锚点同值；评语失败留空且不抛。

---

## 五、工作流 D：report 编排与 API

**目标**：`POST /api/v1/report`（SSE 四决策点循环）+ token 下载端点 + 落库。

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| D1 | 摘要工具 | `python/tools/report/inspect_score_excels.py` | `@tool`：只读文件元信息（不解析数据）→ `{files:[{subject,class_name,has_daofa,has_required_optional,student_count}], semester}`；行3/文件名/特征列（道法列、必选-自选列）判定 |
| D2 | 批量执行工具 | `python/tools/report/render_report_batch.py` | **`async def render_report_batch(...)`**（必须显式 async：进度 channel 依赖事件循环内执行，sync @tool 会被 LangChain 丢线程池 → contextvar 不穿透、Queue 非线程安全）；`args_schema={file_keys, category, semester}`（**无 user_message**，它只进 agent prompt）；调 B3-B5 解析合并 → 断言 → C5-C8 逐学生（LLM 填充并发 4；**WeasyPrint 渲染用 `asyncio.to_thread` + `Semaphore(4)`**；单生 60s 超时）→ 存储上传（A7）→ 落 `report_artifacts`（含 `token_expires_at`）→ 返回 `{students:[{student_id,name,status,format,url}], failed_students, warnings}`；**进度 channel**：contextvar + asyncio.Queue，每学生 `put(("student_done"|"student_error", {...}))`；**取消**：每学生循环前 `current_task().cancelled()` 检查 + 整体 `try/except asyncio.CancelledError` 收敛（清理中间产物） |
| D3 | 编排门面 | `python/agent/report/service.py` | `async def stream_report(req, out_queue)`：`build_report_agent()`（specs 更新见 D6）→ 并发消费 `astream_events`（on_tool_start/end）+ 工具进度 queue（**`asyncio.wait` 双流合流，任一终止即整体收敛**）→ 归一 SSE 事件；`done` 负载从工具结果装配（不采信 LLM 文本）；**CancelledError 兜住**：客户端断开 → 取消传播到 agent 运行与工具内，异常收敛不泄漏 |
| D4 | 分类决策辅助 | `service.py` | 节点①/③/④ prompt 片段：分类枚举 `{1,2,unknown}` + 理由；规则兜底函数 `classify_by_rules(summary) -> int|None`（道法→2/必选自选→1/文件名年级词）；冲突以规则为准记偏差 |
| D5 | API 路由 | `python/api/report.py` | 重写：`POST /api/v1/report`（multipart `files`+`semester`+可选 `user_message`）SSE `text/progress/student_done/student_error/done/error`（**text 事件承载节点①③④⑥ 澄清提问与交付叙述**）；`GET /api/v1/report/download?file_key&token&expires_at`（HMAC `report_download_secret`，24h；`token_expired/invalid_token/artifact_not_found` 三类结构化错误）；`app.py` include_router |
| D6 | specs 更新 | `python/agent/main/specs.py` | `REPORT_AGENT_SPEC`：skills=`/skills/report-generation/`，allowed_tools=`(inspect_score_excels, render_report_batch)`，system_prompt 增补"只填表不计算/异常不得静默" |
| D7 | 仓库层 | `python/storage/mysql/report_artifact_repo.py` | `create_artifact/list_by_batch/get_by_batch_student/list_latest_by_student` |
| D8 | runtime 注册 | `python/agent/runtime.py` | 注册 `inspect_score_excels`/`render_report_batch`；minio_repo 单例；桶 ensure |

**验证**：
```bash
cd python && python -m pytest tests/test_report_service.py tests/test_report_api.py tests/test_report_artifact_repo.py -v
```
API 测试（TestClient 消费流）：真实样本 → `progress...student_done...done` 序断言；断 MinIO mock → 本地兜底 `student_done`；token 过期/伪造/文件缺失三类错误；四决策点各分支（分类冲突/unknown 反问/告警决策）。

---

## 六、工作流 E：evaluation 数据基准

**目标**：摄入管线落 `metadata_json` + 快照工具（确定性直查）。

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| E1 | 结构化提取 | `python/tools/documents/desensitizer.py` | +`extract_transcript_courses(text) -> list[{course_name, course_nature, credits, score}]`（正则锚定课程行；失败→warning 不阻塞）；单测用成绩单文本 fixture |
| E2 | 摄入管线 | `python/scripts/ingest_transcript_desensitized.py` + `python/agent/documents/service.py` | 摄入时调用 E1 → 写每 chunk `metadata_json`（全量结构化副本）；幂等不变 |
| E3 | repo 扩展 | `python/storage/mysql/document_repo.py` | 新增 `get_chunks_by_user(user_id)`：**按 `JSON_EXTRACT(metadata_json, '$.user_id')` 过滤**（覆盖 ingest 脚本与 `/documents/upload` 两条路径——upload 的 dataset_name 是用户任意传的，不能用 LIKE 匹配）→ 返回 chunk + metadata_json；**既有 `get_chunk_contents` 保持不动**（query_knowledge 消费，改结构有回归风险） |
| E4 | 快照工具 | `python/tools/evaluation/get_academic_snapshot.py` | `@tool`（**user_id 从 `agent.main.context.get_current_user_id()` 注入，不进 args_schema**）；直查 metadata_json → `AcademicSnapshot{courses, derived{count, total_credits, avg, weighted_avg, variance, top_subject, weak_subject, pass_rate}, sources:[chunk_ids]}`；无数据 → `{code:"no_transcript_data", hint}`；metadata_json 缺失 → 正文正则回退 |

**验证**：
```bash
cd python && python -m pytest tests/test_evaluation_snapshot.py -v
```
派生统计手算断言；无数据结构化错误；回退路径。集成（有库环境）：重灌后快照正确 + `query_knowledge` 成绩单检索仍正常（RAG 不破）。

---

## 七、工作流 F：evaluation 编排与 API

**目标**：五层反幻觉管线 + 教师端 SSE 落库 + 学生端读取。

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| F1 | 维度提案 | `python/tools/evaluation/design_dimensions.py` | `@tool`：输入快照 → prompt `dimension_design.txt`（结构化 JSON）→ Pydantic 校验 `{dimensions:[{name(≤8),weight,metric,rationale(≤50)}], overall_theme(≤20)}` + metric 枚举（5 个）校验；失败回灌重试 1 次 → 默认维度集（代码内置 5 维等权重）；`build_chat_openai(task_name=EVALUATION_DIMENSION_DESIGN)` |
| F2 | 雷达数值 | `python/tools/evaluation/compute_radar_values.py` | `@tool`：metric→值（weighted_gpa 学分加权均分归一/stability=100-方差/top_subject 最高分/pass_rate×100/credit_load 归一）；未知 metric 拒绝该维记偏差；输出 `RadarData{dimensions:[{name,value,rationale}]}` |
| F3 | 评语生成 | `python/tools/evaluation/generate_comment.py` | `@tool`：输入快照+RadarData+comment_type → prompt `comment.txt`（每个数字必须来自给定数据/语气按类型/60-150字）→ 输出；**数值引用核验**：正则提取数字 vs 快照/雷达数值集（容差 0.5）→ 不一致回灌重试 1 次 → 规则化评语（模板+真实数值）；流式 token 经 channel 上报 |
| F4 | 五层编排 | `python/agent/evaluation/service.py` | `async def stream_evaluation(req, out_queue)`：层①快照→②提案→③雷达→④评语→⑤熔断（**CircuitBreaker 先加 `acall` async 包装**——现 `call()` 同步实现无法保护 async 调用，异常在 await 点熔断计数失效）；每层间发 `stage` 心跳事件；SSE 事件 `stage/radar/comment_token/done/error`；完成自动 INSERT `evaluation_records`（status=generated\|fallback）；**端点直接管线，不建 agent 壳**（EVALUATION_AGENT_SPEC 仅 Phase 3 chat 路由预留） |
| F5 | API | `python/api/evaluation.py` | 重写：`POST /api/v1/evaluation`（`{target_user_id, comment_type, grade_hint?, generated_by?}`；comment_type 枚举校验 422）；`GET /api/v1/evaluation/me?user_id=...`（**显式 user_id 查询参数**，遵循 `/recommend/stream` 直接端点先例；`list_by_user(limit=20)`；无数据返回 `{items:[]}`）；`app.py` include_router |
| F6 | repo | `python/storage/mysql/evaluation_repo.py` | `insert/list_by_user/get` |
| F7 | specs/skill | `python/agent/main/specs.py` + `python/skills/evaluation-writing/SKILL.md` | EVALUATION_AGENT_SPEC allowed_tools=`(get_academic_snapshot, design_dimensions, compute_radar_values, generate_comment)`；SKILL.md：数据源=知识库成绩单、comment_type 必选、反幻觉规则、兜底 |
| F8 | runtime | `python/agent/runtime.py` | 注册 F1-F3 工具 |

**验证**：
```bash
cd python && python -m pytest tests/test_evaluation_radar.py tests/test_evaluation_comment.py tests/test_evaluation_api.py -v
```
非法提案/未知 metric/权重不归一 → 拦截重试 → 默认维度；评语注入幻觉数字 → 核验拦截 → 规则化兜底；雷达数值手算断言；教师端 SSE 事件序 + 无成绩单 `error`；`/me` 列表与越权隔离。

---

## 八、工作流 G：main agent 插件 + MCP

**目标**：mcp_client 实装 + 三 MCP + 五插件工具 + images 契约。

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| G1 | MCP 客户端 | `python/tools/mcp_client.py` | 实装 `MultiServerMCPClient`：注册表（settings.mcp_servers）/懒连接缓存/`list_tools`（langchain-mcp-adapters 转 StructuredTool，namespace 前缀）/`call_tool`/`disconnect`；**每服务器独立 CircuitBreaker（先给 `circuit_breaker.py` 加 `acall` async 包装，同步 `call()` 无法保护 async 调用）**；失败 → `isError {code,message}` 不抛；同时 `tools/circuit_breaker.py` 新增 `acall` + 单测（async 函数熔断/复位） |
| G2 | 假 MCP 服务器 | `python/tests/fake_mcp_server.py` | 三服务器 mock（search/image/code 各 2 工具），供 G 全组单测 |
| G3 | web_search | `python/tools/chat/web_search.py` | 签名不变；MCP `search/*` 主路 → 熔断 → tavily SDK 直连兜底 → 双失败 error |
| G4 | image_generate | `python/tools/image/image_generate.py` | 即梦 MCP `image/*`：参数规范（prompt/ratio/style/negative）→ 产物 URL → 存 MinIO/本地 → 返回链接；无兜底 → 结构化 error（不伪造） |
| G5 | image_recognize | `python/tools/image/image_recognize.py`（新） | `@tool(image_url, question)`；`build_chat_openai(model=settings.vision_model, task_name=VISION_ANALYZE)`；图片附件先落本地转路径 |
| G6 | code_interpreter | `python/tools/code/code_interpreter.py` | E2B MCP `code/*` → 熔断 → 本地 Docker 受限沙箱（CPU/内存/超时 kill）→ error |
| G7 | writing_assistant | `python/tools/chat/writing_assistant.py` | LLM 实装（多体裁）；`build_chat_openai(task_name=MAIN_AGENT_ROUTER)` |
| G8 | mindmap_generator | `python/tools/mindmap/mindmap_generator.py` | LLM 大纲 DSL → **Python 渲染**（自写 SVG/HTML DSL 渲染器或纯 Python 库如 markdown-it + 自绘 SVG——**不能用 markmap/mermaid-cli**：Docker 是 `python:3.12-slim` 无 Node，装 node 体积/攻击面代价高）→ 文件链接 |
| G9 | images 契约 | `python/api/chat.py` + `python/agent/main/prompt.py` | `ChatRequest.images: list[str] = []`（URL/data URL，上限 4）；`MAIN_AGENT_SPEC.allowed_tools` + `image_recognize`；`MAIN_AGENT_SYSTEM_PROMPT` 增补"图片附件可调 image_recognize"声明；**同时从 MAIN_AGENT_SPEC.allowed_tools 移除 `compute_weighted_grade`**（stub 抛 NotImplementedError，chat 触发即报错——本阶段不实装则摘除） |
| G10 | skills | `python/skills/image-generation/SKILL.md`（新）、`web-search/SKILL.md`、`writing/SKILL.md`（改） | image-generation：触发/参数/工作流（MCP client 配置）/兜底；web-search 改 MCP 版 |
| G11 | 文档 | `docs/v2.0.0/tools/{web_search,image_generate,code_interpreter,mindmap_generator,writing_assistant}.md`（改）+ `image_recognize.md`（新） | 实装版说明同步 |

**验证**：
```bash
cd python && python -m pytest tests/test_mcp_client.py tests/test_main_agent_plugins.py -v
```
三服务器注册/发现/调用/namespace 断言；熔断→降级链；web_search MCP 失败→直连兜底→双失败；image_generate MCP 失败→error 不伪造；image_recognize（mock vision）返回分析；`/chat/stream` 带 images 正常流式。

---

## 九、工作流 I：记忆机制（chat 长期记忆 + 无状态智能体模式）

**目标**：交付面 D/E——chat 会话记录持久化（可查询消息历史）、跨会话长期记忆（增量摘要提取、user_id 隔离）、AGENTS.md 多租户修复、写纪律；report/evaluation/recommend 无状态模式。设计依据：详细计划 §3 Step 9 + pi 记忆机制移植（append-only 条目树 / `<previous-summary>` 增量摘要 / 写纪律 / in-memory 无状态）。

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| I1 | 表结构 | `sql/init-db.sql` | 追加 `chat_sessions`（含 last_extracted_seq 水位）/ `chat_messages`（UNIQUE(session_id,seq)，append-only，只增不删）/ `chat_memory_entries`（content TEXT + content_hash + UNIQUE(user_id,kind,content_hash)）（详细计划 §9 DDL 原样） |
| I2 | 仓储层 | `python/storage/mysql/chat_session_repo.py`（新） | `get_or_create_session`（**(session_id,user_id) 复合键**，不匹配新开会话）/ `append_message`（**事务内 `UPDATE chat_sessions SET message_count=message_count+1` 原子自增分配 seq** + per-session `asyncio.Lock` 串行）/ `list_messages(session_id, after_seq)` / `update_extracted_seq` / `upsert_memory_entry`（content_hash 唯一索引去重）/ `list_memory_entries(user_id, limit, max_chars)` / `count_unextracted(session_id)` / `get_last_extract_failure(session_id)` / `mark_extract_failure` |
| I3 | 写纪律 | `python/agent/memory/persistence.py`（新） | `persist_turn(session_id, user_id, user_msg, assistant_msgs)`：逐条 append（每条独立提交，中断不丢已落；**user_id 为空 → 直接跳过**）；MySQL 不可用 → structlog 告警不阻塞（尽力而为）；`flush_before_done` 钩子供 chat 端点调用 |
| I4 | 记忆提取 | `python/agent/memory/extractor.py`（新） | `maybe_extract(session_id, user_id)`：匿名/无锁获取失败跳过；`count_unextracted >= threshold` 且距上次失败 ≥ 600s 触发；取 `seq > last_extracted_seq` **oldest-first**（单批 ≤ max_messages）→ 增量摘要 prompt（`memory_extract.txt`：**`<previous-summary>` = 该 user 最近 N 条 entries 聚合文本**，输出条目 JSON `[{kind, content}]`，kind∈preference/fact/decision，禁止对话延续）→ Pydantic 校验（失败回灌重试 1 次 → 记录失败时间戳退避，不阻塞）→ **全部 upsert 成功后才推进 last_extracted_seq**（幂等）；提取与 persist 共用 per-session 锁串行 |
| I5 | 提取提示词 | `python/agent/memory/prompts/memory_extract.txt`（新） | pi `UPDATE_SUMMARIZATION_PROMPT` 移植：只保留用户偏好/事实/决策，丢弃寒暄与工具噪音，输出严格 JSON；输入含个人数据，LangSmith trace 标注脱敏策略 |
| I6 | 记忆注入 | `python/agent/memory/injector.py`（新） | `inject_memory_entries(user_id, session_id) -> list[dict] | None`：**仅会话首轮**（chat_sessions/chat_messages 无该 (session,user) 历史 + checkpoint `aget_tuple` 兜底）→ 最近 N 条（**总字符 ≤2000**）→ 返回独立 context 消息（role=user，"用户记忆：…"前缀，**绝不改写 req.message**，persist 不落此前缀）；非首轮/匿名 → None |
| I7 | AGENTS.md 改造 | `python/memories/AGENTS.md` | 降级为系统级静态记忆（项目背景/技能索引/记忆使用指导）；删除用户偏好/个人数据写入语义 |
| I8 | 无状态模式 | `python/agent/main/specs.py` + `factory.py` | `AgentSpec` + `use_checkpointer: bool = True`；REPORT/EVALUATION/RECOMMENDATION 三 spec 设 `False`（**main/PPT 保持 True**）；factory 按 spec 决定 `checkpointer`（False → None）；**main agent 装配 `FilesystemPermission(operations=["write"], paths=["/memories/AGENTS.md"], mode="deny")` 代码级禁写** |
| I9 | chat 端点接入 | `python/api/chat.py` | `/chat`：ainvoke 返回前同步 `persist_turn` + 提取用 Starlette `BackgroundTasks`；`/chat/stream`：`done` 前同步 persist + 生成器 `finally` 兜底（客户端断开也尽力落库）；assistant 消息 = **完整 AIMessage 结构**（`on_tool_start` 捕获 name/args 填 tool_calls_json，文本 done 前取最终 state）；提取用 `asyncio.create_task` + 模块级 set 跟踪 + done callback 吞异常（同会话任务在跑则跳过） |
| I10 | settings/枚举/runtime | `config/settings.py` + `ai/llm_task_name.py` + `agent/runtime.py` | `memory_extract_threshold_messages=20` / `memory_extract_max_messages=200` / `memory_extract_retry_after_seconds=600` / `memory_entries_per_user_limit=50`；`LLMTaskName.MEMORY_EXTRACT`；chat_session_repo 单例 |
| I11 | 文档 | `docs/v2.0.0/skills-tools-architecture.md` | 增补"有状态 vs 无状态智能体"章节（pi `--no-session`/in-memory 对应说明：无状态=memory()空+不挂 checkpointer+一次性上下文注入+结果结构化回收） |
| I12 | prompt 改写 + 版本锁定 | `python/agent/main/prompt.py` + `python/requirements.txt` + `python/tests/test_main_agent_memory.py` | prompt "长期记忆管理"整节改写（删除用户级写回语义，与框架 `<memory_guidelines>` 去冲突）；requirements 锁 `deepagents>=0.7.5,<0.8`；`test_main_agent_memory.py` 的 prompt/AGENTS.md 字符串断言同步更新 |

**验证**：
```bash
cd python && python -m pytest tests/test_chat_session_repo.py tests/test_chat_persistence.py tests/test_memory_extractor.py tests/test_memory_injector.py tests/test_stateless_specs.py -v
```
断言：消息落库 seq 有序/并发锁防冲突/中断不丢/幂等/匿名跳过；阈值触发 + oldest-first 分批 + 水位幂等 + 失败退避 + user_id 隔离；**注入仅首轮/续轮不注入/跨 user 不注入**；工厂 use_checkpointer=False 不建 checkpointer（checkpoint 无新增行，tmp_path 隔离）；AGENTS.md 写回被 FilesystemPermission 拒绝（edit_file 返回权限错误）；既有 chat 测试（含 test_main_agent_memory.py 同步更新）不破。

**回退**：MySQL 不可用 → 写纪律降级日志告警，对话正常；提取失败 → 退避重试；AGENTS.md 改造后对话功能零依赖其用户级内容。

---

## 十、工作流 J：评估方针骨架（Phase 2 首批 eval set）

**目标**：交付面 F——eval_sets 首批 4 集 + `eval/runner.py` 断言式指标 + LangSmith Dataset 导入。设计依据：详细计划 §3 Step 10（全量指标 Phase 4，总 plan.md 已记录）。

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| J1 | eval_sets 目录与格式 | `python/eval_sets/`（新） | JSONL 格式（见详细计划 Step 10.1）；`README.md` 说明格式与指标映射 |
| J2 | chat_intent 集 | `python/eval_sets/chat_intent.jsonl` | 20 条：推荐/报告/评价/知识库/闲聊/写作/图片意图，断言=期望路由工具链 |
| J3 | report_math 集 | `python/eval_sets/report_math.jsonl` | 10 条：输入科目等级 → 期望中间 JSON 数值（vs 手算） |
| J4 | evaluation_comment 集 | `python/eval_sets/evaluation_comment.jsonl` | 10 条：断言=评语数值全部 ∈ 快照集合（复用数值引用核验闸做断言器） |
| J5 | kb_retrieval 集 | `python/eval_sets/kb_retrieval.jsonl` | 10 条：query → expected_chunk_ids 标注 → Recall@k 断言（run_kb_test 前身） |
| J6 | runner | `python/eval/__init__.py` + `python/eval/runner.py` | 读集 → 逐 case 调真实端点（`--live`）或工具层（`--smoke` mock）→ 断言器（contains/not_contains/exact/numeric/recall）→ 输出 `python/eval/reports/<date>.json` 汇总 + 终端表格；收集 LangSmith run_id 回链 |
| J7 | LangSmith 导入 | `python/scripts/import_langsmith_dataset.py` | eval_sets JSONL → `client.create_dataset("phase2-"+type)` + `create_examples`（Phase 4 LLM-as-judge 消费同一 Dataset） |
| J8 | runner 单测 | `python/tests/test_eval_runner.py` | 断言器单测（四类断言 + recall 计算）+ 汇总 JSON 结构 |

**验证**：
```bash
cd python && python eval/runner.py --set chat_intent --smoke     # mock 模式，汇总 JSON 生成
cd python && python scripts/import_langsmith_dataset.py           # LangSmith Dataset 可见（需 key）
cd python && python -m pytest tests/test_eval_runner.py -v        # 断言器单测绿
```
有库环境 `--live` 跑 report_math → 数值断言 100%。

**回退**：LangSmith 不可达 → runner 降级纯本地报告；断言失败 → 报告 FAIL 不阻塞业务交付。

---

## 十一、工作流 H：全量回归与验收

**目标**：十一条试金石全绿。

| # | 任务 | 内容 |
|---|------|------|
| H1 | 补测试 | 详细计划 §3 Step 8/9/10 的 19 个测试文件随各工作流验证命令逐一落齐（W-B×2 / W-C×2 / W-D×3 / W-E×1 / W-F×3 / W-G×2 / W-I×5 / W-J×1）；另有 `tests/test_llm_client_defaults.py`（A6 默认行为回归）与 `tests/test_report_contract.py`（B6 别名映射）各工作流未覆盖、单独补建（合计 21） |
| H2 | 全量回归 | `cd python; python -m pytest tests/ -m "not slow" -v` 全绿 |
| H3 | 既有功能回归 | `test_stream_recommend.py`/`test_documents_upload.py`/`test_agent_factory.py` 全绿 |
| H4 | Docker 验收 | `docker compose up -d --build` 全 healthy（minio 9000/9001 可访问、milvus 带凭据起） |
| H5 | 端到端冒烟（有库/凭据环境） | report 真实样本全链（分类→PDF/HTML→下载）；evaluation（摄入→生成→`/me` 读取）；chat 插件（web_search MCP 真连、image_recognize 真图冒烟验证 qwen3-vl-plus多模态）；chat 多轮 → 查库验证消息落盘 + 记忆提取；`eval/runner.py --live` 首批断言通过 |
| H6 | 文档收尾 | 更新 `docs/v2.0.0/plan.md`（Phase 2 状态 ✅ + 本文件索引）；`CLAUDE.md` 核心文件表同步；本文件状态改 ✅ |

---

## 十二、执行顺序与风险卡点

**建议提交切分**（每提交保持测试绿）：
1. `feat(phase2): 基建` — A1-A8 + H1 的 llm_client 回归测试
2. `feat(phase2): report 解析合并` — B1-B6
3. `feat(phase2): report 模板填充` — C1-C9
4. `feat(phase2): report 编排 API` — D1-D8
5. `feat(phase2): evaluation 数据基准` — E1-E4
6. `feat(phase2): evaluation 编排 API` — F1-F8
7. `feat(phase2): main agent 插件 MCP` — G1-G11
8. `feat(phase2): 记忆机制` — I1-I12（chat 会话记录 + 记忆提取 + 无状态模式 + AGENTS.md 代码级禁写）
9. `feat(phase2): 评估方针骨架` — J1-J8（eval_sets 首批 4 集 + runner + LangSmith 导入）
10. `feat(phase2): 回归验收` — H1-H6

**风险卡点**（阻塞时先看详细计划 §6 回退）：
- 即梦/E2B/tavily MCP 凭据未到位 → G 组先用假 MCP 服务器全绿，真连冒烟（H5）延后
- 一年级模板未到 → C3 骨架交付，替换模板即生效
- 新学科 Excel 样本结构不同 → B3 表头配置化（A1 预留 `report_header_profile`）补配
- 成绩单重灌需数据 → E2 改造后待用户重跑 `ingest_transcript_desensitized.py`
- 记忆提取 LLM 输出不稳定 → I4 校验回灌 + 失败退避重试，不阻塞对话；MySQL 不可用 → 写纪律降级日志
- deepagents 升级漂移 → I12 锁 `>=0.7.5,<0.8`（checkpointer=None / FilesystemPermission / MemoryMiddleware 语义依赖 0.7.5）

---

## 十一、验收映射

| 试金石 | 对应工作流任务 | 验证 |
|--------|---------------|------|
| report 端到端 | D1-D8 + H5 | 真实样本 → 链接 + 下载 |
| report 防丢失 | B4-B5 + D2 | 顺序打乱/缺科/Journal 单测 |
| LLM 填表防线 | C5-C7 | 四类坏响应 → 降级链 |
| evaluation 端到端 | F1-F4 | 五层 + 手算断言 |
| evaluation 同步 | F5-F6 | 落库 + /me 越权隔离 |
| MCP 实装 | G1-G6 + G9 | 三服务器 mock + images 契约 |
| SSE 契约 | D5 + F5 | 消费流断言事件序/done/error |
| chat 记忆 | I2-I6 + I9 + I12 | 消息历史可查询 + 增量幂等 + 注入仅首轮 + user_id 隔离 + AGENTS.md 禁写 |
| 无状态模式 | I8 | 三 spec 不建 checkpointer + 行数不变 |
| 评估骨架 | J1-J7 | 首批 4 集 + runner 断言指标 + LangSmith 导入 |
| 回归 | H2-H4 | pytest 全绿 + docker 构建 |

---

## 十二、验收记录（2026-08-13 编码完成）

| 试金石 | 状态 | 证据 |
|--------|------|------|
| 轴 A report 端到端 | ⏳ 待 docker 验收 | 真实样本解析/合并/填表单测全绿（test_report_* = 20 passed） |
| 轴 B report 防丢失 | ✅ | 键合并/差集告警/完整性断言/Journal 单测绿 |
| 轴 C LLM 填表防线 | ✅ | 四类坏响应拦截 → 重试 → Jinja2 降级单测绿 |
| 轴 D evaluation 端到端 | ✅（管线侧） | 维度校验/雷达确定性/评语核验 25 passed |
| 轴 E evaluation 同步 | ✅（API 侧） | 教师端 SSE 事件序 + /me 隔离测试绿 |
| 轴 F MCP 实装 | ✅（假 MCP） | 三服务器注册/发现/熔断/降级 14 passed；真连待凭据 |
| 轴 G SSE 契约 | ✅ | report/evaluation/chat 消费流断言事件序/done/error |
| 轴 H 回归 | ✅ | pytest -m "not slow" = **235 passed, 4 deselected**；compileall 干净；app 17 路由可导入 |
| 轴 I chat 记忆 | ✅（逻辑侧） | repo 原子 seq/复合键/去重 + 提取幂等/退避 + 注入仅首轮 + AGENTS.md 禁写权限 15 passed |
| 轴 J 无状态模式 | ✅ | 三 spec use_checkpointer=False + 工厂断言 + checkpoint 不写入 |
| 轴 K 评估骨架 | ✅ | eval_sets 4 集 + runner smoke 8/8 + LangSmith 导入脚本 |

**待执行（需用户环境）**：
1. docker compose down -v && docker compose up -d --build（minio 密码 123456 + WeasyPrint 系统依赖 + 中文字体）
2. 重灌：ingest_course_dataset.py / ingest_student_handbook.py / ingest_transcript_desensitized.py --user-id 3123003252 --name 黄信烨（metadata_json 结构化落库）
3. 端到端冒烟：report 真实样本全链；evaluation 摄入→生成→/me；chat 记忆多轮；eval/runner.py --live
4. 外部凭据到位后：即梦/E2B/tavily MCP 真连冒烟 + qwen3-vl-plus多模态验证
