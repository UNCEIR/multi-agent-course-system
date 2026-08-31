# 大学校园多智能体平台（v2.0.0）：面试准备主入口

> v1 文档已按 v2 现状重写。**v1 时代主叙事"双模式 Pipeline/ReAct"已不再是核心**——v2 升级到 main_agent（deepagents 框架）统一入口，4 个业务模块解耦（recommend / report / evaluation / 知识库问答），5 个 MCP 工具桥接外部能力。本文档据此更新。

## 1. 项目介绍（v2）

面向大学生校园场景的多智能体平台：

- **学生端**：自然语言选课推荐（`recommend_courses` tool，5 agent 流水线），知识库问答（学生手册 + 个人成绩单）
- **教师端**：批量成绩单报告（`report` 模块，5 决策点 + WeasyPrint PDF），评价寄语生成（`evaluation` 模块，5 层反幻觉）
- **通用**：论文写作（`writing_assistant`）、网页搜索（tavily MCP）、图像生成（即梦 MCP）、代码执行（e2b MCP）、PPT 生成

**核心思路**：deepagents 框架 + 业务模块解耦 + 知识库 RAG + MCP 工具桥接。

## 2. 文档阅读顺序

| 目标 | 先读 | 读完应该能回答 |
| --- | --- | --- |
| 快速了解项目主线 | `docs/INDEX.md` | 当前有哪些文档、各自定位（v1 历史归档在 `docs/v1.0.0/`） |
| 准备 60 秒和 3 分钟口播 | `docs/interview-star-stories.md` | 8 个 v2 故事（main_agent 路由 / 评价反幻觉 / SSE 续传 / dispatch_module / zod 错误层 / CourseFields 抽取 / live eval 兑现 / dev proxy 502） |
| 写简历 bullet | `docs/resume-template.md` | 三个方向各能写什么、不能写什么（按 v2 业务重写） |
| 讲系统设计 | `docs/architecture.md` | v2 总体架构：main_agent + 4 业务模块 + 5 MCP 工具 + 数据架构 |
| 讲代码证据 | `docs/code-walkthrough.md` | 从 chat/stream → main_agent → 4 业务模块代码 |
| 讲流式编排细节 | `docs/supervisor-main-orchestration.md` | v1 supervisor 在 v2 中包装为 recommend_courses tool + pipeline/react 双模式 + SSE 协议升级 |
| 练追问 | `docs/interview-question-bank.md` | 28 题追问的结论-证据-边界（v2 业务 + 跨语言/MCP 工具） |

## 3. 面试主叙事

### 3.1 开场顺序

1. **先讲场景**：学生选公选课不是搜索关键词，而是同时考虑兴趣、校区、时间、考核、容量；教师端每学期要批量出成绩单 + 评语。
2. **再讲核心思路**：v2 用 **main_agent（deepagents 框架）统一入口**——4 个业务模块（recommend / report / evaluation / 知识库问答）解耦为独立服务 + 工具或路由。
3. **再讲编排**：
   - **main_agent 路由**（决策 17）：LLM 识别意图 → 调 `recommend_courses` tool（推荐）/ `dispatch_module`（报告/评价/PPT/图片）
   - **`recommend_courses` 内部**：v1 supervisor 5 agent 流水线（画像 → 召回 → 硬约束 → 语义初筛 → 重排 → 可行性 → 理由）
   - **`report` / `evaluation`**：直接管线（不用 ReAct），五层反幻觉
4. **最后讲验证**：**335 后端单测 + 127 前端单测 + 17 份 eval report（6 个集 live 通过）**。

### 3.2 必须讲清的取舍

- **为什么用 deepagents 而不是 LangGraph 裸用**：deepagents 内置 SkillsMiddleware（渐进式 skill 披露）、SummarizationMiddleware（compaction 五字段摘要）、SqliteSaver（thread_id 跨会话恢复）、FilesystemPermission（禁写 /memories/AGENTS.md）；这些 LangGraph 全要手写。Phase 0 POC 验证 deepagents 0.6.12 + 中转站 tool-calling 双向兼容 → GO。
- **为什么 main_agent + 4 业务模块解耦**：图片生成 / PPT 生成是深度交互场景（需要画布/参数配置），不适合嵌入对话流；recommend/report/evaluation 是对话式查询，适合在对话中路由到独立模块（决策 16+17）。
- **为什么 hard_constraint 锁死不可跳过**（决策 4 修订）：用户说"只要西校区"时推荐东校区是不可接受的——硬约束过滤在 react 模式中也是唯一不可跳过的工具，编排器强制补调。
- **为什么 v1 supervisor 仍保留**（决策 4）：v1 已有 39 单测 + 双模式 A/B，包装为 subgraph 暴露为 tool，避免重写；main_agent 享受 deepagents 框架能力，recommend 享受 v1 双模式灵活性。
- **为什么 SSE 用 EventBuffer + Last-Event-ID**：docker desktop 偶发 502 + LLM 长生成 + 客户端断网——环形缓冲 + INCR 全局自增 + 客户端指数退避重连，三层冗余。

### 3.3 与 v1 的关键差异

| 维度 | v1 | v2 |
| --- | --- | --- |
| 入口 | `POST /api/v1/recommend/stream` 单接口 | `POST /api/v1/chat/stream` 主入口 + 4 业务模块独立端点 |
| 编排 | SupervisorOrchestrator（pipeline/react） | main_agent（deepagents）路由 + recommend_courses tool（内部仍走 v1 supervisor） |
| 业务范围 | 仅推荐 | 推荐 + 报告 + 评价 + 知识库 + 论文 + 网页搜索 + 图像 + PPT + 代码 |
| 知识库 | 仅有 KB 雏形 | 完整 RAG（学生手册 public + 个人成绩单 user 分区） |
| SSE | 单向无续传 | id: 字段 + Last-Event-ID 续传 + 客户端指数退避（路 2） |
| 工具桥接 | 全部进程内 tool | 3 个 MCP server（tavily / jimeng / e2b）+ 1 个自建 stdio |
| 评估 | 无 | 6 个集 + 17 份 reports（路 0~4 沉淀） |
| 记忆 | 仅 AGENTS.md | AGENTS.md 全局共享 + `chat_memory_entries` 表用户（决策 19） |

## 4. 按岗位切换侧重点

### AI Agent 方向
- 重点讲：deepagents 工厂 + 4 业务模块解耦 + main_agent 路由 + dispatch_module + zod schema 校验 + useNotify/useApi 统一反馈层
- 推荐 story：main_agent 路由（教师端 dispatch_module 修复）/ 评价反幻觉 / SSE 续传

### 后端工程方向
- 重点讲：asyncio 并行调度（5 agent pipeline）/ Redis 双层缓存（exact + semantic）/ EventBuffer 续传 / MySQL+Milvus+Redis+MinIO 数据架构
- 推荐 story：SSE 续传 / dev proxy 502 修复 / 评价反幻觉五层管线

### 推荐系统 / RAG 方向
- 重点讲：5 agent 流水线（画像/召回/硬约束/重排/可行性）/ query_knowledge 工具 / 三层召回 / RAGAS 指标框架
- 推荐 story：recommend 推荐业务 / 知识库问答

## 5. 训练路径

### 第一轮：讲顺
- 用 `docs/interview-star-stories.md` 的前 3 个故事练 60 秒口播（**注意：v2 故事用 main_agent 路由，不要讲 v1 的双模式作为主入口**）
- 要求：不超过 90 秒，不连续堆 3 个技术名词，每 20 秒都能听到"为什么"或"我做了什么"

### 第二轮：讲细
- 用 `docs/code-walkthrough.md` 练代码证据链
- 要求：能从 `chat/stream` 入口讲到 main_agent，再讲到 4 业务模块（recommend_courses / report / evaluation / query_knowledge）
- 能画出 main_agent → 4 模块 → 5 MCP 工具的依赖关系

### 第三轮：被追问
- 用 `docs/interview-question-bank.md` 练追问
- 要求：每题先给一句结论，再给一个代码或验证证据（必须链接 eval report 或复盘笔记），最后承认一个真实边界

## 6. 不要这样讲

- ❌ 不要说"实现了高并发推荐系统"，当前没有压测数据
- ❌ 不要说"CTR 提升 15%"，没有真实用户实验结果
- ❌ 不要把 Redis 说成"实时学生画像"，当前是候选 course_id 缓存 + SSE 续传环形缓冲
- ❌ 不要说"全量生产可用"，A/B 的 react 组还没在生产自动分流，metrics 进程内
- ❌ 不要说"Agent 之间有对话协商"，当前是 main_agent 调度 + dispatch_module 路由，Agent 间没有直接通信
- ❌ 不要把 v1 supervisor 说成"v2 核心"——它是 v2 main_agent 内部子 agent（决策 4 包装）
- ❌ 不要隐瞒 LLM 参与度：核心召回、硬约束、加权公式是工程代码，LLM 参与画像/排序/理由/评语
- ❌ 不要说"5 个业务模块"——v2 是 **4 个业务模块 + 5 个 MCP 工具**（recommend_courses 是工具不是模块）

## 7. v2 真实数据背书（每条都有 eval report）

| 量化 | 数值 | 报告 |
| --- | --- | --- |
| 后端单测 | 335 passed | `python -m pytest tests/ -m "not slow"` |
| 前端单测 | 127 passed | `frontend npm test` |
| chat_intent 真实端测 | 4/4 case 修复后通过 | `eval/reports/chat_intent-2026-08-18.json` |
| evaluation_comment_live | 6/6（71 门课 / 144.5 学分 / 加权 85.85） | `eval/reports/evaluation_comment_live-2026-08-17.json` |
| report_math_live | 2/2（37 学生 PDF 全成） | `eval/reports/report_math_live-2026-08-18.json` |
| web_search | 5/5（tavily 闭环） | `eval/reports/web_search-2026-08-16.json` |
| image_generate | 5/5（即梦两段式） | `eval/reports/image_generate-2026-08-16.json` |
| SSE 续传 | EventBuffer 16 单测 + 客户端 11 单测 | `tests/test_sse_event_buffer.py` + `frontend/tests/lib/sse.spec.ts` |
| chat_intent 路由表 prompt 契约 | 20 单测 | `tests/test_chat_intent_prompt.py` |

## 8. 面试前自查

- [ ] 30 秒内能讲清"学生选课为什么难 + 教师批量出报告/评语为什么难"
- [ ] 能说清"main_agent 路由 + 4 业务模块解耦 + deepagents 框架"
- [ ] 能解释 main_agent → dispatch_module → 业务模块的路由链
- [ ] 能解释 v1 supervisor 与 v2 main_agent 的关系（包装为子 agent）
- [ ] 能解释 MySQL、Milvus、Redis、MinIO 分别解决什么问题
- [ ] 能说出至少 3 个真实验证数据（chat_intent 4/4、evaluation 6/6、report 2/2）
- [ ] 能拿出至少 1 个 eval report + 1 个复盘笔记作为追问证据
- [ ] 对真实未知数据使用"待补充"，不编造指标
- [ ] 能按岗位切换侧重点（AI Agent / 后端工程 / 推荐系统 / RAG）
