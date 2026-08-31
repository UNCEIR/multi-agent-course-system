# 简历模板（v2.0.0 重写，三个方向）

> v1 时代模板基于 v1 supervisor / 4 个 ReAct agent / 硬约束锁死。v2 已升级到 **main_agent（deepagents）路由 + 4 业务模块 + 5 MCP 工具**。本模板按 v2 业务重写，三个方向各给 5-6 条 bullet 模板 + 项目标题 + 60 秒口播。所有 bullet 都有真实 eval report / 复盘笔记作为证据。

## 0. 项目标题（按方向）

| 方向 | 标题（推荐） |
| --- | --- |
| AI Agent | **大学校园多智能体平台 v2**（main_agent 深度路由 + 5 MCP 工具桥接） |
| 后端工程 | **大学校园多智能体平台 v2**（deepagents 工厂 + SSE 续传 + 4 业务模块解耦） |
| 推荐系统 | **大学校园多智能体平台 v2**（5 agent 流水线 + RAG + 反幻觉五层管线） |

## 1. AI Agent 方向

### 项目概述（150 字内）
> 大学校园多智能体平台 v2：main_agent（deepagents 框架）统一入口 + 4 个业务模块解耦（recommend_courses 工具 / report / evaluation / 知识库问答），LLM 路由意图到 dispatch_module 4 种 intent（report/evaluation/ppt/image_generate）。3 个 MCP server 桥接外部能力（tavily / 即梦 / e2b），zod schema 给 SSE 事件做运行时校验。

### Bullet 模板（5-6 条）

1. **设计 main_agent 路由 + dispatch_module 工具**：升级到 deepagents 框架后**教师端 4 个 chat_intent case 全部失败**——LLM 识别到"出报告"反而去查知识库。设计 `dispatch_module(intent: Literal["report","evaluation","ppt","image_generate"])` 路由工具，在 system prompt 顶部加"教师端意图关键词路由表"显式禁止退回 query_knowledge；**4/4 修复后通过**，20 个 prompt 契约测试锁死关键词 + 模块映射。
2. **设计 v1 supervisor → v2 main_agent 的包装关系**：v1 supervisor（5 agent 流水线 + pipeline/react 双模式）已通过 v1 历史 39 单测，不重写；用 `recommend_courses` tool 包装（决策 4），main_agent 享受 deepagents 框架能力，recommend 享受 v1 双模式灵活性。**smoke 20 case + live 真实端测均通过**。
3. **设计 SSE 续传协议（路 2）**：后端 `EventBuffer` 用 Redis `INCR` 全局自增 + `LPUSH+LTRIM` 环形缓冲（max 100 条 + TTL 30min）；客户端 `consumeSSEWithRetry` 指数退避 500ms→1s→2s（max 3），自动 `Last-Event-ID` header 透传。**16 个 EventBuffer 单测 + 11 个前端 retry 单测**；容器实测：53 events 后断线重连，从 id=54 续传。
4. **设计评价反幻觉五层直接管线（决策 5 修订）**：快照（MySQL）→ 雷达方案（5 维）→ LLM 评语 → 反幻觉核验（reference.assertion 评语引用数值必须来自 snapshot）→ 落库。**6/6 live eval 通过**，学生 3123003252 真实成绩单（71 门课 / 144.5 学分 / 加权 85.85）评语无幻觉。
5. **设计 5 个 MCP 工具桥接外部能力（决策 8+21）**：tavily（网页搜索）/ jimeng（即梦图像，两段式 submit→轮询 get→落库）/ e2b（Python 沙箱）；其中 jimeng 因火山无官方 MCP 自建 stdio server。`eval/web_search 5/5 + image_generate 5/5`。
6. **设计 zod schema 统一错误反馈层（路 3）**：前端 3 套散落（`message.error` / `<Text type="danger">` / StreamView 红 panel）→ 2 套统一（`useNotify().toast.*` + `useNotify().inline.*`），加 zod schema 给 SSE 事件做运行时校验。**6 个 page + 1 个 login 全替换**，26 个新单测（safeCall 12 + useNotify 6 + useApi 8 + sse 11）。

### 60 秒口播
> v2 大学校园多智能体平台：main_agent（deepagents）统一入口，4 业务模块解耦。教师端 4 个 chat_intent 失败——我设计 dispatch_module 工具 + 教师端意图关键词路由表，4/4 修复通过。SSE 用 EventBuffer + Last-Event-ID 续传，指数退避 500ms→1s→2s。评价反幻觉五层管线，6/6 live 通过。

## 2. 后端工程方向

### 项目概述
> 大学校园多智能体平台 v2 后端：deepagents 工厂统一创建业务 Agent + 4 业务模块（recommend_courses 工具 / report / evaluation / 知识库问答）解耦为独立服务 + 5 MCP 工具桥接。SSE 流式响应带 id 字段 + Redis EventBuffer 环形缓冲支持断点续传。335 后端单测 + 17 份 eval report。

### Bullet 模板

1. **设计 main_agent 统一 deepagents 工厂**：`build_deep_agent(spec)` 接收 AgentSpec（system_prompt + skills + memory + allowed_tools + checkpointer），工具白名单 + CircuitBreaker 熔断，SqliteSaver 单实例持久（决策 20）。**335 后端单测 + 0 errors 0 warnings**。
2. **设计 SSE 续传协议（路 2）**：后端 `EventBuffer`（Redis `INCR` + `LPUSH+LTRIM` 环形 100 条 + TTL 30min）；客户端 `consumeSSEWithRetry` 指数退避 500ms→1s→2s（max 3），自动 `Last-Event-ID` header 透传。**16 个 EventBuffer 单测 + 11 个前端 retry 单测**；容器实测 53 events 断线重连从 id=54 续传。
3. **设计 v1 supervisor 5 agent 流水线**：画像（LLM 抽 8 维）→ 召回（Redis 候选 → MySQL+Milvus 合并 143 候选）→ 硬约束（纯规则）→ [optional] 语义初筛（LLM）→ 重排（规则+LLM）→ 可行性（LLM+规则）→ 流式理由。pipeline 模式 8-15s，react 模式 15-30s（异常恢复）。**39 单测通过（v1）**。
4. **设计评价反幻觉五层直接管线**：快照（MySQL）→ 雷达方案（5 维）→ LLM 评语 → 反幻觉核验（reference.assertion 评语引用数值必须来自 snapshot）→ 落库。**6/6 live eval 通过**，学生 71 门课 / 144.5 学分 / 加权 85.85 评语无幻觉。
5. **设计 4 业务模块 SSE 端点 + Last-Event-ID 续传**：`/api/v1/{chat,recommend,report,evaluation,documents}` 5 端点统一 SSE 协议，每条事件带 id 字段 + `Last-Event-ID` header 续传；`/api/v1/chat` 入口 lifespan 启动 `agent.runtime` 单例（supervisor / 仓储 / ToolRegistry / main_agent）。
6. **设计 docker dev proxy 502 修复（路 5）**：`next.config.ts` `localhost:8000` → `127.0.0.1:8000`（强制 IPv4）+ 新增 `frontend/Dockerfile` + `docker-compose.yml` `frontend` 服务（`profiles: ["frontend"]` + `API_PROXY_TARGET=http://python-api:8000`）容器内直连绕开转发层。**`docker compose --profile frontend up -d` 启动后无 502**。

### 60 秒口播
> v2 后端：deepagents 工厂统一创建 Agent，4 业务模块解耦。SSE 用 EventBuffer 环形缓冲 + Last-Event-ID 续传。v1 supervisor 5 agent 流水线，pipeline/react 双模式。评价反幻觉五层管线，6/6 live 通过。docker 502 修复走 127.0.0.1 + 容器化直连。

## 3. 推荐系统 / RAG 方向

### 项目概述
> 大学校园多智能体平台 v2 推荐 + 知识库 RAG：5 agent 流水线（画像/召回/硬约束/重排/可行性）从 500 门公选课中召回 + 排序 + 选课风险检查；RAG 走 Milvus `user_id` 分区（public 手册 + user 成绩单）+ Redis 双层缓存（exact + semantic）。评价反幻觉五层管线 live 6/6 通过，71 门课真实数据。

### Bullet 模板

1. **设计 5 agent 推荐流水线**：v1 supervisor（画像 → 召回 → 硬约束 → 语义初筛 → 重排 → 可行性 → 理由），pipeline 模式 8-15s，react 模式 15-30s（异常恢复）。`hard_constraint_filter` 在 react 模式中锁死不可跳过（决策 4 修订），硬约束违反 = 推荐失败。**39 单测通过**。
2. **设计 Redis 双层候选 ID 缓存**：exact_key + semantic_key 双层（threshold 0.95），防并发短锁 5s TTL；**只缓存 course_id 不缓存完整对象**（避免与 MySQL 不一致）。召回 143 候选多数来自 cache。
3. **设计三层数据架构**：MySQL（事实/会话/记忆/评价）+ Milvus（向量，1024 维，user_id 分区）+ Redis（缓存 + SSE 续传环形缓冲）+ MinIO（报告 PDF）。智能体隔离 = checkpoint 独立 + 工具白名单 + ContextVar user_id 注入 + 存储分区。
4. **设计评价反幻觉五层直接管线（决策 5 修订）**：快照（MySQL 拉真实成绩单）→ 雷达方案（5 维：3 维固定 + 2 维 LLM）→ LLM 评语（4 种 comment_type 驱动）→ 反幻觉核验（reference.assertion 评语引用数值必须来自 snapshot）→ 落库。**6/6 live eval 通过**，学生 71 门课 / 144.5 学分 / 加权 85.85 评语无幻觉；tokens 110K / latency p50=67.7s。
5. **设计 RAG 知识库分区与脱敏**：学生手册 `user_id=public` + 个人成绩单 `user_id=user_*` 互不干扰；脱敏（姓名 → `[姓名]`，学号 mask，班级 → 年级，日期 → 年，但**课程名/学分/成绩保留供本人查询**）。摄入幂等（`delete_by_dataset + replace_chunks`）——重跑即清理旧版本。
6. **设计 query_knowledge 工具 + ContextVar 注入**：用 `get_current_user_id()` 注入（**不**放 args_schema 里），让 LLM **不**猜 user_id。检索 `public + current_user` 双分区，LLM 回答**必引来源** `[来源: 学生手册 第X页]`；检索为空时**不**编造（说知识边界）。

### 60 秒口播
> v2 推荐 + RAG：5 agent 流水线（画像/召回/硬约束/重排/可行性）从 500 门公选课召回 + 排序。三层数据架构 MySQL+Milvus+Redis+MinIO。评价反幻觉五层管线，6/6 live 通过，71 门课真实数据。query_knowledge 用 ContextVar 注入 user_id 防 LLM 猜，公共手册+个人成绩单 user_id 分区隔离。

## 4. 三个方向的真实数据（每条都有 eval report 支撑）

| 量化 | 数值 | 报告 / 证据 |
| --- | --- | --- |
| 后端单测 | 335 passed | `python -m pytest tests/ -m "not slow"` |
| 前端单测 | 127 passed | `frontend npm test` |
| chat_intent 真实端测 | 4/4（教师端 dispatch_module） | `eval/reports/chat_intent-2026-08-18.json` |
| chat_intent prompt 契约 | 20 passed | `tests/test_chat_intent_prompt.py` |
| evaluation_comment_live | **6/6**（71 门课 / 144.5 学分 / 加权 85.85） | `eval/reports/evaluation_comment_live-2026-08-17.json` |
| report_math_live | 2/2（37 学生 PDF 全成） | `eval/reports/report_math_live-2026-08-18.json` |
| web_search | 5/5（tavily 闭环） | `eval/reports/web_search-2026-08-16.json` |
| image_generate | 5/5（即梦两段式） | `eval/reports/image_generate-2026-08-16.json` |
| kb_retrieval | 0/3（标注待重写；precision 0.933） | `eval/reports/kb_retrieval-2026-08-17.json` |
| SSE 续传 | EventBuffer 16 单测 + 客户端 11 单测 | `tests/test_sse_event_buffer.py` + `tests/lib/sse.spec.ts` |
| CourseFields 抽取 | 18 单测 | `tests/components/CourseFields.spec.tsx` |

## 5. 真实边界（不能写简历的）

- ❌ **"实现高并发推荐系统"**：无压测数据
- ❌ **"CTR 提升 15%"**：无真实用户实验结果
- ❌ **"实时学生画像"**：当前 Redis 是候选 course_id 缓存 + SSE 续传
- ❌ **"全量生产可用"**：A/B react 组还没在生产自动分流
- ❌ **"Agent 之间有对话协商"**：当前 main_agent 调度 + dispatch_module 路由，Agent 间无直接通信
- ❌ **"5 个业务模块"**：v2 是 4 个业务模块 + 5 个 MCP 工具
- ❌ **"RedisSaver 多实例 checkpoint"**：当前单实例 SqliteSaver（决策 20）

## 6. 项目经历段（3-4 行，项目写在简历上的"项目描述"位置）

```
项目：大学校园多智能体平台 v2.0    时间：2026.06 - 2026.08
- main_agent（deepagents 框架）统一入口 + 4 业务模块解耦（recommend_courses 工具 / report / evaluation / 知识库问答）
- 3 个 MCP server 桥接外部能力（tavily / jimeng / e2b），zod schema 给 SSE 事件做运行时校验
- 评价反幻觉五层管线（6/6 live eval 通过），SSE 续传协议（EventBuffer + Last-Event-ID + 指数退避）
- 335 后端单测 + 127 前端单测 + 17 份 eval report（6 个集）
```

## 7. 自我检查清单（写完 bullet 后逐条验证）

- [ ] 每个量化数字（335 / 127 / 6/6 / 2/2 / 4/4）都有 eval report 或单测报告链接
- [ ] 每个技术名词（dispatch_module / EventBuffer / ContextVar / Literal 枚举）都能在 `docs/code-walkthrough.md` 找到代码证据
- [ ] 没有"实现 / 提升 / 全量"等无法验证的词
- [ ] 没有"5 个业务模块 / 实时画像 / 高并发"等错误说法（v2 是 4 模块 + 5 MCP）
- [ ] 没有 v1 supervisor 双模式作为 v2 核心的描述（它是 v2 main_agent 的子 agent）
- [ ] 3-5 条 bullet 涵盖"问题 + 解法 + 量化结果 + 边界"四要素
- [ ] 项目描述段（3-4 行）让 HR / 面试官 30 秒内明白"是什么 / 解决什么问题 / 用了什么 / 量化结果"

## 8. 投递前准备

1. 选方向 → 选 5-6 条 bullet → 选 2-3 个故事练口播
2. 练追问：每条 bullet 准备 1 个"证据链接"+ 1 个"真实边界"
3. 投递时附 1 个 `eval/reports/chat_intent-2026-08-18.json` + 1 个 `notes/2026-08-18-phase3-sse-resumability-and-cancellation.md` 作为"项目深度"佐证
