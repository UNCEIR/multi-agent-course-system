<!-- markdownlint-disable MD013 MD033 -->

# 大学校园多智能体平台（v2.0.0）— 架构设计文档

> v1 时代沉淀的架构文档已不再准确（v1 supervisor 仍是核心，但被 deepagents 包装为子 agent；新增 main_agent 路由 + 4 个业务模块 + 知识库 RAG + MCP 工具 + 评测体系）。本文件按 v2 现状重写，配套 `docs/v2.0.0/plan.md` + `notes/` 复盘笔记 + `docs/v2.0.0/eval-system.md` 评测总述。

## 1. 业务问题

大学校园场景三类核心痛点：

1. **信息过载 + 隐性约束难判断**：500 门公选课 + 校区/时间/考核/容量/年级优先权等硬约束，单靠关键词搜索无法解决
2. **学生手册 + 个人成绩单 知识分散**：政策查询、成绩分析、报告生成、评价寄语——每件事都要跑不同窗口
3. **重复劳动**：教师端每学期要批量出成绩单报告 / 寄语；学生端每次选课要重复描述偏好

v2 方案：**主智能体（main_agent，deepagents 框架）+ 4 个业务模块（recommend / report / evaluation / 知识库问答）+ 5 个 MCP 工具（tavily 搜索 / 即梦图像 / e2b 代码 / 自建 stdio 桥接 / 内部 ToolRegistry）**。

## 2. 系统边界

| 边界 | 当前职责 | 关键文件 |
| --- | --- | --- |
| API 层 | 8 个端点：auth / chat/stream / recommend/stream / report / evaluation / documents/upload / health-metrics-experiments | `python/api/` |
| 编排层 | `main_agent` (deepagents 工厂) + 4 业务模块 service（`report/service.py` / `evaluation/service.py` / `recommend/supervisor.py` / `documents/service.py`） | `python/agent/main/` + `python/agent/recommend/` + `python/agent/{report,evaluation,documents}/` |
| Agent 工具层 | 5 个 MCP（tavily / jimeng / e2b / 内置 stdio 桥接）+ 4 个直接 @tool（query_knowledge / recommend_courses / dispatch_module / writing_assistant 等） | `python/tools/` |
| Skill 层 | 11 个 `SKILL.md`（recommend-courses / knowledge-query / report-generation / evaluation-writing / writing / image-generation / ppt-generation / web-search / document-ingestion / deep-thinking / 公共 _shared） | `python/skills/` |
| 存储层 | MySQL（事实/会话/记忆/评价）+ Milvus（向量，user_id 分区）+ Redis（候选 ID 缓存 + SSE 续传环形缓冲）+ MinIO（报告 PDF） | `python/storage/` |

## 3. 总体架构（v2 现状）

```
┌─────────────────────────────────────────────────────────────────────┐
│  Frontend (Next.js 16 App Router)                                    │
│  ─────────────────────────────────────────────────────────────────  │
│  (main) 路由组: chat / recommend / report / evaluation / documents /  │
│             experiments / monitor  + Hub + 8 页面                    │
│  login 独立路由: /login (无 main layout)                              │
│  shared: CourseFields (路 7 抽取) + useNotify/useApi (路 3)           │
│         + consumeSSEWithRetry + zod schema                            │
└────────────────────────┬────────────────────────────────────────────┘
                         │ SSE / JSON
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  python-api (FastAPI + lifespan → agent.runtime)                     │
│  ─────────────────────────────────────────────────────────────────  │
│  POST /api/v1/chat/stream        → main_agent.astream_events         │
│  POST /api/v1/recommend/stream   → recommend_courses tool            │
│                                    (包装 v1 supervisor)            │
│  POST /api/v1/report             → report.service.stream_report     │
│  POST /api/v1/evaluation         → evaluation.service (5 层管线)    │
│  POST /api/v1/documents/upload   → documents.service                │
│                                                                       │
│  统一 SSE 协议 (路 2 升级):                                          │
│    每条事件: id: N\nevent: <name>\ndata: {...}                       │
│    重连: Last-Event-ID header → EventBuffer.replay_from()            │
│    客户端 retry: 指数退避 500ms→1s→2s (max 3)                        │
└────────────────────────┬────────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
│ main_agent   │ │  v1 supervisor │ │ 业务模块 service │
│ (deepagents)  │ │ (包装为        │ │  (report/eval/   │
│               │ │  recommend_    │ │   documents)     │
│ 路由：        │ │  courses tool) │ │                  │
│ - chat → 自身 │ │               │ │ 五层反幻觉管线：  │
│ - recommend → │ │ 双模式：      │ │ 1. 快照          │
│   dispatch_   │ │  - pipeline   │ │ 2. 雷达方案提案   │
│   module      │ │  - react      │ │ 3. LLM 评语生成  │
│ - report →    │ │               │ │ 4. 反幻觉核验    │
│   dispatch_   │ │ 5 Agent:     │ │ 5. 落库          │
│   module      │ │  画像/召回/  │ │                  │
│ - evaluation  │ │  重排/可行性 │ │ 公式：            │
│   → dispatch_ │ │  /理由       │ │ 加权=0.3×display  │
│   module      │ │               │ │  + 0.7×exam     │
│ - kb → query_ │ │ 8 tool 锁死： │ │  + bonus        │
│   knowledge   │ │  硬约束不可跳 │ │ (85.85 = 71 门) │
│ - image/PPT → │ │  LLM 兜底     │ │                  │
│   dispatch_   │ │               │ │                  │
│   module      │ │               │ │                  │
└──────────────┘ └──────────────┘ └──────────────────┘
        │                │                │
        ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  工具 / MCP                                                            │
│  ─────────────────────────────────────────────────────────────────  │
│  @tool (8 个): recommend_courses / query_knowledge / writing_assistant│
│               / dispatch_module / parse_document / chunk_document     │
│               / code_interpreter / mindmap_generator / image_* 等     │
│  MCP (3 个 + 1 stdio): tavily (web search) / jimeng (火山即梦图像)    │
│                       / e2b (Python 沙箱) / 自建 stdio 桥接           │
│  ToolRegistry: 注册 + allowlist 门控 + CircuitBreaker (失败 3 次熔断) │
└────────────────────────┬────────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
│ MySQL 8.0    │ │ Milvus 2.4.6 │ │ Redis 7 (缓存/    │
│ (3307)       │ │ (19530)      │ │  SSE 续传环形缓冲)│
│              │ │              │ │ (6379)           │
│ 事实/会话/   │ │ 向量,        │ │                  │
│ 记忆/评价/   │ │ user_id 分区 │ │ 候选 course_id   │
│ 报告元数据   │ │              │ │ EventBuffer      │
│ report_artifact│ │ (public/user) │ │ (lpush + ltrim)  │
│ evaluation_  │ │              │ │ (INCR 自增)      │
│ records      │ │              │ │                  │
└──────────────┘ └──────────────┘ └──────────────────┘
        ┌────────────────┘
        ▼
┌──────────────────────────┐
│ MinIO (9002)              │
│ 报告 PDF 存储             │
│ 文档源                    │
└──────────────────────────┘
```

## 4. 智能体业务链

### 4.1 main_agent（deepagents 工厂，决策 2/3/17）

**职责**：聊天统一入口，识别用户意图并路由到对应模块/工具。

**业务链**：

```
用户消息 → astream_events → LLM 决策 →
  ├─ 知识库问答 → query_knowledge (Milvus 检索 public+user 分区)
  ├─ 网页搜索 → tavily MCP (中转站 400 字符限制 + 锚点 prompt)
  ├─ 论文写作 → writing_assistant tool
  ├─ 课程推荐 → recommend_courses tool (即 v1 supervisor)
  ├─ 报告生成 → dispatch_module(intent="report") → /report 页面
  ├─ 评价寄语 → dispatch_module(intent="evaluation") → /evaluation 页面
  ├─ PPT 生成 → dispatch_module(intent="ppt") → /ppt 页面
  └─ 图片生成 → dispatch_module(intent="image_generate") → /image-generate 页面
```

**数据指标**（eval/reports/chat_intent-2026-08-18.json）：
- **意图路由通过率**：4/4 case `intent_04/05/06/07` 全部通过教师端 dispatch_module 路由（路 1 修复后）
- **延迟分布**：p50=14.5s, p95=25.7s, TTFT p50=10.5s
- **混合意图**：intent_20（先查已选课 + 再推荐新课）通过

### 4.2 recommend_courses tool（v1 supervisor 包装，决策 4）

**职责**：从 500 门公选课中召回、硬约束过滤、LLM 语义初筛、LLM 重排、可行性检查、生成可解释理由。

**业务链**：

```
user_id + prompt
  → student_profile (LLM 抽取软偏好 + 硬约束)
  → course_recall (Redis 候选 ID 缓存 → MySQL 结构化 + Milvus 语义)
  → hard_constraint_filter (纯规则: 校区/时间/考试/教师/类别)
  → [optional] LLM 语义初筛 (候选 >40 且有画像)
  → course_rerank (规则预筛 + LLM 精排)
  → course_feasibility (LLM priority_advice + 规则兜底)
  → recommendation_reason (流式 token 输出: course_start/text/course_end)
  → done
```

**关键业务指标**（eval_system.md §2 + v1 supervisor 代码）：
- **5 Agent** 流水线（v1 supervisor）：student_profile / course_recall / course_rerank / course_feasibility / recommendation_reason
- **8 tool** 锁死（ReAct 模式）：硬约束过滤不可跳过
- **A/B 分组**：pipeline（control/treatment_llm）vs react（手动注册）；metrics 走 LangSmith

### 4.3 report.service（Phase 2 实装，决策 16）

**职责**：批量 Excel → 加权计算 → 1.html 模板 → WeasyPrint PDF → MinIO 下载链接。

**业务链**：

```
multipart files + semester
  → 并行 5 决策点（A-shell）:
     1. inspect_score_excels (openpyxl 解析 → subject + grades JSON)
     2. merge_students (多科 → 学生级 JSON)
     3. fill_report_html (1.html Jinja2 填表)
     4. compute_weighted_grade (0.3×display + 0.7×exam + bonus)
     5. render_pdf (WeasyPrint) + MinIO 上传 → token 下载 URL
  → SSE: progress / student_done / student_error / done / error
```

**关键业务指标**（eval/reports/report_math_live-2026-08-18.json）：
- **真实端到端通过率**：2/2 case（37 学生 PDF 全成；`failed_students=0`）
- **加权公式**：`weighted = 0.3 × display + 0.7 × exam + bonus`（路 3 实装在 `tools/report/compute_weighted_grade.py`）
- **单 PDF 延迟**：910s/722s（37 学生批处理）
- **PDF 输出**：MinIO bucket `report-artifacts`，HMAC token 24h 有效

### 4.4 evaluation.service（Phase 2 实装）

**职责**：教师端为学生生成学业评价（雷达图数据 + 评语）。

**业务链**（五层反幻觉直接管线，**无 ReAct**）：

```
target_user_id + comment_type (4 种) + teacher_subjective
  → 五层顺序执行:
     1. 快照: 拉取学生成绩单 + 学籍 (MySQL)
     2. 雷达方案: design_dimensions (5 维度提案, 3 维固定 + 2 维 LLM)
     3. LLM 评语: generate_comment (按 comment_type 4 种驱动)
     4. 反幻觉核验: 数值必须来自快照 (reference.assertion 拦截)
     5. 落库: evaluation_records (MySQL)
  → SSE: stage / radar / comment_token / done / error
```

**关键业务指标**（eval/reports/evaluation_comment_live-2026-08-17.json）：
- **真实端到端通过率**：6/6（5 类 comment_type + 无数据返回 `no_transcript_data` 兜底）
- **加权公式引用**：5 case 评语均包含 "71 门课 / 144.5 学分 / 加权均分 85.85 / 优势科目为社会心理学"（**评语引用了 compute_weighted_grade 算出的真实数值**——反幻觉闸放行）
- **延迟分布**：p50=67.7s, p95=77.0s（5 个中等 case 65-77s + 1 个 easy case 0.17s `no_transcript_data` 快速返回）
- **Token 消耗**：input=90K + output=20K = 110K（4 类 comment_type × 学生真实成绩单）

### 4.5 query_knowledge tool（Phase 1 RAG）

**职责**：检索 Milvus `document_chunks`，合并 public + current user 分区。

**业务链**：

```
query
  → embedding_client.embed_text (text-embedding-v4, 1024 维)
  → Milvus.search (user_id in [public, current_user])
  → DocumentRepository.get_chunk_contents (回填正文)
  → chunks[] (含 rank + chunk_id + source_doc_name + page_number + section)
  → LLM 回答 + 强制引用来源 [来源: 学生手册 第X页]
```

**关键业务指标**（eval/reports/kb_retrieval-2026-08-17.json）：
- **当前通过率**：0/3（标注为虚拟 handbook_chunk_*，与真实 chunk_id 体系 handbook_2025_acff6de8:N 不匹配；待 Phase 4 重写标注）
- **context_recall** = 0.285（标注不匹配导致偏低；context_precision = 0.933 反向证明检索精度高）
- **延迟**：p50=178.7ms（小查询），p95=18.9s（首次冷启动含 Milvus 索引加载）

### 4.6 工具 / MCP（5 个 + 3 MCP server）

| 工具 | 业务用途 | 关键指标 |
| --- | --- | --- |
| `writing_assistant` | 论文写作（多体裁 / 多风格） | 决策 18：对话内嵌式 |
| `parse_document` / `chunk_document` | 文档解析 + 分块（heading-aware + 中文分隔） | recursive 分块；脱敏（姓名 → `[姓名]`，学号 mask，班级 → 年级，日期 → 年） |
| `code_interpreter`（e2b MCP） | 沙箱 Python 执行 | 决策 21：cross-language tool calling |
| `mindmap_generator` | 脑图 | 决策 21 |
| `tavily` MCP（web_search） | 实时网页搜索 | eval/web_search 5/5（0.8-8.9s/用例） |
| `jimeng` MCP（image_generate） | 火山即梦图像生成 | eval/image_generate 5/5（30-130s/用例）；两段式 submit→轮询 get→落库 |
| `dispatch_module` | 意图路由（report/evaluation/ppt/image_generate） | 决策 16+17：main_agent 识别后调用，前端跳独立页面 |

## 5. 数据架构

| 存储 | 类型 | 关键数据 | v2 升级点 |
| --- | --- | --- | --- |
| MySQL 8.0 | 关系型 | `users / chat_sessions / chat_messages / chat_memory_entries / report_artifacts / evaluation_records / document_records / document_chunks` | 新增 `chat_memory_entries`（用户级长期记忆）；`evaluation_records`（评价档案）；`report_artifacts`（报告 PDF 元数据） |
| Milvus 2.4.6 | 向量 | `document_chunks`（handbook 768 维；course_chunks 1024 维） | user_id 分区（public 手册 / user 个人成绩单） |
| Redis 7 | 缓存 | 候选 course_id 列表（`recall_cache`）；SSE 续传环形缓冲（`sse:counter:*` + `sse:events:*`） | 路 2 新增：EventBuffer（INCR 全局自增 + LPUSH+LTRIM 环形 100 条 + TTL 30min） |
| MinIO | 对象 | 报告 PDF（`report-artifacts` bucket）；源文档 | HMAC token 24h 有效 |

## 6. 关键决策（v2 决策索引，详见 `plan.md`）

| # | 决策 | 选择 | v2 落地 |
| --- | --- | --- | --- |
| 2 | 编排基座 | deepagents | `python/agent/main/factory.py` |
| 3 | 框架 | deepagents | 统一工厂 + ToolRegistry + 5 个 AgentSpec |
| 4 | v1 共存 | 包装为 subgraph 暴露为 tool | `recommend_courses` 工具包装 v1 supervisor |
| 5 | 报告 | Excel → 1.html → WeasyPrint PDF | `report/service.py` |
| 8 | 跨语言 TS | MCP 桥接 | 3 个 MCP server（tavily / jimeng / e2b）+ 自建 stdio |
| 16 | 前端架构 | 统一对话框 + 独立模块页 | 决策 16+17 落地：`(main)` 路由组 + dispatch_module 路由 |
| 17 | main_agent 能力边界 | 路由到模块，不内嵌 | `dispatch_module` 工具，4 个 intent |
| 19 | 长期记忆分级 | AGENTS.md 全局 / `chat_memory_entries` 表用户 | `agent/memory/` 实现 |
| 20 | checkpoint | 单实例 SqliteSaver | `langgraph-checkpoint-sqlite`；`langgraph-checkpoint-redis` 留待多实例 |
| 21 | 跨语言通信 | REST / RabbitMQ / SSE / MCP | 当前 SSE + REST + MCP；RabbitMQ 留待任务并发 |
| 22 | BFF 预留 | `app/api/` 目录 | 当前空，决策 22 备注未来 Java 数据服务 |

## 7. 验证记录

| 维度 | 状态 | 证据 |
| --- | --- | --- |
| **后端单测** | ✅ 335 passed | `pytest -m "not slow"`（含 16 个 SSE EventBuffer 单测 + 20 个 chat_intent prompt 单测） |
| **前端单测** | ✅ 127 passed | `npm test`（vitest + RTL；路 7 抽 CourseFields 共享字段层 + 14 个 spec 文件） |
| **eval 数据集** | ✅ 6 个集 + 24 case live 集 | `python/eval_sets/` + 17 份 reports |
| **chat_intent 真实端测** | ✅ 4/4 | intent_04/05/06/07 修复后通过；20 case 已增 4 边界（路 4） |
| **evaluation_comment live** | ✅ 6/6 | 71 门课/144.5 学分/85.85 加权公式 0.3+0.7+bonus 真实评语 |
| **report_math live** | ✅ 2/2 | 37 学生 PDF 全成；failed=0 |
| **kb_retrieval live** | ⚠️ 0/3 | 标注不匹配，Phase 4 重写；precision 0.933 反证检索质量 |
| **web_search / image_generate** | ✅ 5/5 | tavily + 即梦两段式闭环 |
| **docker build / rebuild** | ✅ 镜像源 = `docker.m.daocloud.io/library/python:3.12-slim`（registry-1.docker.io 不可达） | `--build-arg` 必传 |

## 8. 不在范围

- Phase 4 全量 LLM-as-judge 评测（faithfulness / answer_relevancy / NDCG 全套）—— 等 LLM 额度恢复后跑
- Java 数据服务（BFF 后端）+ RabbitMQ 异步任务队列（决策 21+22 后置）
- FastGPT 二次开发桥接（决策 6 修订后置）
- RedisSaver 实际迁移（决策 20 条件：多实例部署）

## 9. 推荐阅读

- `docs/v2.0.0/plan.md` — v2 总计划（Phase 0~4 概要）
- `docs/v2.0.0/eval-system.md` — 评测体系总述（6 个集 + 17 份 reports + 字段契约）
- `docs/v2.0.0/frontend-architecture.md` — 前端 App Router 挂载链路 + SSE 消费
- `docs/notes/v2.0.0/` — 各阶段复盘笔记（路 1~7 + Phase 3 live eval 兑现）
- `docs/architecture.md`（本文件）— 智能体业务链 + 数据架构 + 决策索引
- `docs/code-walkthrough.md` — 从入口到 Agent 的代码证据链
