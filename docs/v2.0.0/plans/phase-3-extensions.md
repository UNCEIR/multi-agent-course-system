# Phase 3 详细计划：扩展收尾 + 前端统一开发 + 记忆管理深化

> 本文件是 `../plan.md` Phase 3 的**详细实施计划（设计阶段）**。承接：
> - `notes/2026-07-27-设计决策问答记录.md` / `notes/2026-07-28-设计决策补充说明.md` 决策 1/10/11/13/16/17/18
> - `plan.md` 新增决策 19/20/21（2026-08-14 定稿：记忆分区 / checkpoint 切换条件 / 跨语言通信决策树）
> - `plans/phase-1-platform-base.md` §7.2 与 `plans/phase-2-report-evaluation.md` §7.2 累积的 Phase 3 推迟项清单
>
> 日期：2026-08-16
> 状态：待执行
> 门控属性：**非 go/no-go 门**——子项失败走降级回退，不阻塞整体。

> **当前执行边界（2026-08-16）**：Phase 2 已收官（merge `feature-v2.0.0-phase2`，243 passed，Docker 验收 + E2E 9/9，tavily/即梦/E2B 三 MCP 真连）。本 Phase 3 聚焦三块：**A. 修复调研发现的既有缺口**（image_generate_get 未注册、compute_weighted_grade stub、前端 404 端点、eval oracle 未对齐、evaluation 三函数未工具化）、**B. 前端四 Page 统一开发**（MainPage/ReportPage/EvaluationPage/DocumentsPage，消费后端已就绪的 SSE 端点）、**C. 记忆管理深化**（summary_prompt 五字段 / forked subagent 提取 / consolidation / RedisSaver 按决策 20 条件）。
> **刻意不做（后续 phase 再评估）**：PPT 生成系统（`ppt_generate`）、FastGPT 二次开发桥接、Java 数据服务/真实身份体系（维持 context user_id 临时口径）。图片生成独立 Page 与 PPT Page 一并推迟（`image_generate` 工具已闭环，前端对话内已可调用）。

---

## 1. 目标与范围

### 1.1 目标（三个交付面 + 三条贯穿轴）

| 交付面 | 验证什么 | 对应决策/依据 |
|--------|---------|--------------|
| **A. 既有缺口修复（地基）** | 注册中心与 spec 白名单一致、无 stub 残留在注册表、前端不再调用已删除端点、eval oracle 与真实数据对齐、evaluation 具备 subagent 委派前置条件 | 调研（2026-08-16）发现的 5 类缺口；AGENTS.md 前端 API 契约 |
| **B. 前端架构迁移 + 四 Page 统一开发** | 前端从 Vite SPA 迁移到 **Next.js（App Router，React+TSX）**：现有 RecommendPage/MonitorPage 零重写迁移、SSE 客户端层（chat/report/evaluation/documents/recommend 统一消费器）、MainPage 消费 `/chat/stream` 四事件、ReportPage 上传/进度/下载/重试、EvaluationPage 教师端 echarts 雷达+评语流与学生端 `/me`、DocumentsPage 上传；失效端点清理；为未来 Java 数据服务（REST/OpenAPI）与管理平台（独立项目，同 React 栈）预留 BFF 代理层 | 决策 13/16/17/18；`plans/phase-2-report-evaluation.md` §7.2 前端统一开发；选型调研（2026-08-16：Next.js vs Nuxt vs Vite） |
| **C. 记忆管理深化** | compaction 摘要对齐决策 11 五字段、记忆提取走隔离子任务、跨会话记忆 consolidation、RedisSaver 切换条件文档化（按决策 20 单实例不迁移） | 决策 11/19/20；`plan.md` Phase 3 记忆管理待办 ①~④⑥ |

| 贯穿轴 | 内容 |
|--------|------|
| **轴 1 注册一致性** | 工具注册表 ↔ AgentSpec 白名单 ↔ 前端可用能力三处对齐，用测试锁死（防 `image_generate_get` 类静默缺失再犯） |
| **轴 2 前端流式契约** | 新增前端调用全部消费 SSE 流（text/tool/done/error 或 stage/radar/progress/student_done/…/done/error），终结 `done` + 结构化 `error`，测试必须消费流断言（AGENTS.md 强制）；SSE 消费在 Next.js **Client Component**（`"use client"`）内完成，服务端不做流式拉取 |
| **轴 3 记忆隐私边界** | 决策 19 硬约束：AGENTS.md 只承载全局共享记忆且代码级禁写；用户级记忆一律 `chat_memory_entries` 表按 user_id 分区；consolidation/提取不得把用户数据写回文件 |

### 1.2 范围（Phase 3 刻意不做的事）

- **不**做 PPT 生成系统（`ppt_generate` DSL→PPTX、独立 PPTGeneratePage、skills/ppt-generation 填充）——后续 phase；`PPT_AGENT_SPEC`/`agent/ppt/` 保持骨架不动
- **不**接 FastGPT（mcp_server 二次开发 / FastGPT KB 主链路 / 插件市场）——与 2026-08-08 执行边界一致，后续 phase 重新评估
- **不**建 Java 数据服务 / 用户身份体系——后续 phase；`evaluation_records` 权限继续用 context user_id 强匹配临时口径
- **不**做图片生成独立 Page / ImageGeneratePage——`image_generate` 工具已闭环且已注册给主 agent，对话内可用；独立页后续 phase
- **不**实现管理平台（两套独立项目）——本阶段仅将前端架构与 Java/REST 兼容性纳入设计（BFF 代理层预留），管理平台立项后独立仓库独立开发
- **不**做 RedisSaver 实际迁移——决策 20 条件（实例数 > 1）不满足（docker 单副本），只做配置预留 + 切换文档化
- **不**做 OpenTelemetry / harness 可视化 / 插件市场 / LLM-as-judge 全量指标——Phase 4
- **不**改 v1 推荐链路内部逻辑（仅前端与 `RecommendationRequest` 补 `mode` 字段透传，后端编排零改动）
- **不**动 `sql/init-db.sql` 既有表结构（本阶段无需新表；记忆相关复用 `chat_memory_entries`）

### 1.3 贯穿原则

1. **agent 编排 vs 能力分离**：`agent/` 只做编排与场景装配，`tools/` 放原子能力（@tool + Pydantic args_schema + isError result），`skills/` 放 SKILL.md。新增能力（evaluation 三函数工具化）按此落位。
2. **注册一致性测试锁死**：新增"spec 白名单 ⊆ 注册表"断言测试，任何未来白名单引用未注册工具立即红灯（当前 `image_generate_get` 即此类缺陷）。
3. **确定性优先**：eval oracle 对齐 / consolidation 去重 / 雷达数值 / 加权成绩等一律代码实现，LLM 只做叙述与合并提案（并校验）。
4. **流式契约**：所有前端新调用默认消费 SSE（AGENTS.md），`done` 终结、`error` 结构化。
5. **记忆边界**：决策 19 全局/用户数据分区；决策 20 单实例维持 SqliteSaver；决策 21 跨语言通信决策树不变。

### 1.4 试金石（Definition of Done）

同时满足 = **Phase 3 GO**：

> **验收策略（2026-08-16，LLM 算力受限）**：本阶段**不实际跑真实 LLM 端测**（live eval、真实对话/报告/评价端到端）。以下试金石按两级执行：标注 ⏳ 的项以**确定性单测 + 构建 + mock 路径**为验收替代（数据正确性、结构正确性），真实 LLM 端测在算力允许时补跑；标注 ✅ 的项为必做。
> **未来承诺**：上游资源充足后必须严格跑真实端测并 eval 评估（`eval/runner.py --live` 跑真实结果、回填 `eval/reports/`、核对各集通过率），作为 Phase 3 正式验收依据。

1. **注册一致性**：`image_generate_get` 已注册；`compute_weighted_grade` 已实装（总评 = display×0.3 + exam×0.7 + bonus，含边界校验）；新增测试断言 `MAIN_AGENT_SPEC.allowed_tools ⊆ ToolRegistry 注册表` 全绿；`design_dimensions/compute_radar_values/generate_comment` 提升为 @tool 并注册，`EVALUATION_AGENT_SPEC` 白名单可被 `registry.get_all` 全量命中（✅）
2. **前端失效端点清理**：`api.ts` 不再调用 `/recommend`、`/recommend/react`、`/recommend/graph`、`/recommend/react/stream`（grep 零命中）；`RecommendationRequest` 后端/前端均含 `mode` 字段，`/recommend/stream` 支持 `mode="react"` 走 ReAct（复验 `stream_recommend_unified` 既有逻辑）（✅）
3. **前端四 Page（Next.js 架构下）**：前端已迁移到 Next.js（`npm run build` 通过）；四 Page 代码就位，chat 流式渲染以 mock 事件源单测覆盖 text/tool/done/error 事件序；DocumentsPage 上传端点以单测/接口验证（✅）；真实对话 / report PDF 下载 / evaluation 生成 / 推荐流 ⏳ 延后
4. **前端导航重构**：App Router 真路由（`app/(main)/chat/page.tsx` 等目录约定 + 顶部导航），菜单含 推荐 / 智能对话 / 报告 / 评价 / 知识库 / 系统监控；废弃 `Layout.tsx` 的 `display:none` 假路由（✅ build + dev 路由冒烟）
5. **eval oracle 对齐**：`kb_retrieval` 的 `expected.chunk_ids` 改为真实 chunk_id 体系（`handbook_2025_<hash>:<N>`）；`evaluation_comment` 新增真实数据版集（用户 3123003252 成绩单真实数字）；`report_math` live 断言改为映射真实输出字段（batch_id/students）——**oracle 数据正确性 ✅（采集脚本产出 + runner smoke）；⏳ live 通过率 > 0 延后**
6. **summary_prompt 五字段**：`factory.py` 的 `SummarizationMiddleware` 传入自定义 `summary_prompt`（含决策 11 五字段：Goal / Progress / Key Decisions / Next Steps / Critical Context）；单测断言 prompt 注入（✅ mock）
7. **forked subagent 提取**：`extractor.py` 提取在独立隔离上下文执行（不共享主 agent checkpointer/状态），失败退避幂等保持；新增/更新单测覆盖（✅ mock LLM）
8. **consolidation**：记忆条目超限时按 kind 去重合并（确定性 + 可选 LLM 合并提案）；单测覆盖"同内容不重复、相似条目合并"（✅ mock LLM）
9. **RedisSaver 文档化**：`checkpoint_backend` 配置预留（默认 `sqlite`），`build_checkpointer` 支持按配置分支（redis 路径 import 探测，未装依赖时明确报错）；`docs/v2.0.0/` 决策 20 切换条件记录同步；单实例运行 `pytest` 全绿且 `.checkpoint.db` 使用不变（✅ 单测）
10. **回归**：`cd python; python -m pytest tests/ -m "not slow" -v` 全绿（新代码含前端契约流式断言）；`cd frontend; npm ci; npm run build`（tsc + **next build**，Vite 已废弃）通过；`python eval/runner.py --set chat_intent` 以 smoke 模式不回归（✅；⏳ live/真实 LLM 不跑）
11. **文档同步**：本 plan §7 后续 phase 输入清单更新到 `plan.md`；AGENTS.md 若涉及新配置（checkpoint_backend）保持准确（✅）

---

## 2. 风险与假设

### 2.1 已识别风险

| 风险 | 影响 | 暴露点 | 回退 |
|------|------|--------|------|
| eval oracle 对齐需要真实检索结果（chunk_id 体系、成绩单真实数字），而 live 检索依赖已摄入数据（手册 221 chunks / 成绩单 3 chunks 已在库） | 若数据未摄入则无法回填真实 chunk_id | §3.4 步骤 | 先用 `run_kb_test.py` 确认 KB 可用；chunk_id 从 MySQL `document_chunks` 按章节关键词映射采集，不依赖在线检索 |
| 前端依赖 echarts（雷达图）未在 package.json | 构建失败 | §4.6 | `npm install echarts`（或改用 antd 自带 Progress/描述列表降级展示雷达值） |
| deepagents 0.7.5 的 SummarizationMiddleware `summary_prompt` 参数与中文五字段 prompt 兼容性 | compaction 摘要格式异常 | §5.1 | 已核验 `__init__` 签名含 `summary_prompt`；单测 mock 断言注入；异常 → 回退默认 prompt |
| RedisSaver 分支引入未装依赖导致 import 错误 | 启动失败 | §5.4 | `checkpoint_backend=redis` 时 import 探测失败 → 显式 RuntimeError 且文档化；默认 sqlite 不受影响 |
| 前端四 Page 工作量大、与既有 RecommendPage 视觉风格不一致 | 工期/风格漂移 | §4 | 复用 antd 6 + Tailwind 既有 token；RecommendPage 仅迁移不重写；每 Page 独立验收 |
| **Vite→Next.js 迁移风险**：SSR 下 `window`/`document` 未定义、zustand 跨请求状态污染、antd 与 React 19/Next 兼容、`react-router` 路由废弃改 App Router 目录约定 | 构建/运行错误 | §4.0 | Client Component（`"use client"`）包裹交互页；SSE/本地状态只在客户端；zustand store 按页面实例化避免 SSR 水合污染；迁移后跑 `npm run build` + dev 冒烟 |
| **Next.js 服务端水合（hydration）差异**：echarts/StreamView 依赖 DOM | 水合告警 | §4.6 | 图表组件 `dynamic(..., { ssr: false })` 或客户端挂载后渲染；SSR 阶段渲染占位 |
| evaluation 三函数提升为 @tool 后行为变化（原先 service 直调） | 回归 | §3.5 | @tool 包装为薄壳（内部复用既有函数体），service 直调路径不变；单测双路径覆盖 |
| `compute_weighted_grade` 业务口径与真实算法不符（docstring 公式为展示 30% + 考试 70%） | 计算结果偏差 | §3.2 | 按 docstring 既定公式实现 + 单元测试锁定；口径变更属业务决策后续再调 |
| ReportPage 并发上传大文件 | 内存/超时 | §4.5 | 沿用后端既有限制（单文件 ≤10MB、≤20 文件）；前端展示结构错误不静默 |

### 2.2 假设

- `python/.env` 已有可用 `LLM_*`/`EMBEDDING_*`/`MYSQL_*`/`MILVUS_*`（Phase 1/2 已验证）；知识库已摄入（手册 public 分区 + 成绩单 user 分区，见 `notes/2026-08-09-kb-ingestion-audit.md`）
- 前端开发可连本地后端（`docker compose up -d` + vite proxy 到 8000）
- 后端 `POST /api/v1/report`、`/evaluation`、`/chat/stream`、`/documents/upload` 契约不变（Phase 2 已交付，本阶段仅前端消费 + 极小后端配套）
- echarts 可经 npm 正常安装（国内镜像可配）

---

## 3. 交付面 A：既有缺口修复（地基）

> 调研结论（2026-08-16 子 agent 审计）：后端主链路健康，但存在 5 类一致性缺口，均为"将来必然踩坑"项。

### 3.1 A1：`image_generate_get` 注册进 ToolRegistry

- **现状**：`python/tools/image/image_generate.py:126` 已定义 `@tool image_generate_get`，`tools/__init__.py` 已导出，`MAIN_AGENT_SPEC.allowed_tools` 已引用（`specs.py:50`），但 `agent/runtime.py` 的 `register_many` 清单遗漏 → `registry.get_all(allowed=...)` 静默跳过，主 agent 实际拿不到该工具。
- **改动**：`agent/runtime.py` 注册清单补 `image_generate_get`（import 自 `tools`，加入 `register_many` 列表）。
- **配套测试**（轴 1 注册一致性锁死）：新增 `tests/test_tool_registry_consistency.py`：
  1. 断言每个 AgentSpec 的 `allowed_tools` 均 ⊆ 注册中心可获取集合（构造：mock registry 或运行时 init 后读取）；
  2. 断言所有已注册工具名非空、args_schema 存在。
- **验证**：`python -m pytest tests/test_tool_registry_consistency.py -v` 全绿。

### 3.2 A2：`compute_weighted_grade` 从 stub 实装

- **现状**：`python/tools/report/compute_weighted_grade.py:42` 为 `NotImplementedError` stub，却仍被注册进 registry（`runtime.py:140`），`tools/__init__.py` 也导出——属于"注册表里的残缺能力"。
- **改动**：按 docstring 既定公式实装（纯确定性，零 LLM）：
  - `total = round(display_eval * 0.3 + exam_eval * 0.7 + bonus, 2)`，返回 `{total, display_weighted, exam_weighted, bonus}`（display_weighted = round(display*0.3,2) 等）；
  - 输入已在 `args_schema` 约束（0–100 / 0–20），实现内再 `clamp` 兜底防 NaN。
- **测试**：新增 `tests/test_compute_weighted_grade.py`：边界（0,0,0→0）、常规（60,80,5→**79.0** 即 18+56+5）、上限（100,100,20→120 即 display 30 + exam 70 + bonus 20）、非法输入（负值由 schema 拦截，函数内 assert 防御）。
- **验证**：`python -m pytest tests/test_compute_weighted_grade.py -v` 全绿。

### 3.3 A3：前端失效端点清理 + `RecommendationRequest.mode`

- **现状**：`frontend/src/services/api.ts` 仍导出 `recommend`/`recommendReact`/`recommendGraph`/`recommendReactStream`，指向后端已删除的 `/recommend`、`/recommend/react`、`/recommend/graph`、`/recommend/react/stream`（Phase 2 收敛统一为 `/recommend/stream`）。RecommendPage 的"经典模式/ReAct/批量对比"调用即 404。后端 `models/schemas.py` 的 `RecommendationRequest` 无 `mode` 字段，而 `supervisor.stream_recommend_unified` 支持 `mode="pipeline"/"react"`。
- **改动**：
  1. **后端** `python/models/schemas.py`：`RecommendationRequest` 增加 `mode: str = "pipeline"`（`pattern="^(pipeline|react)$"`）；`python/api/recommend.py` 的 `/recommend/stream` 透传 `req.mode`（`mode="react"` 时走 `stream_recommend_unified(mode="react")`，失败自动兜底 pipeline——既有逻辑，零编排改动）。顺手修正 `api/recommend.py:3` 模块 docstring（"默认走 ReAct"与代码默认 `mode="pipeline"` 矛盾）。
  2. **前端** `frontend/src/services/api.ts`：删除 `recommend`/`recommendReact`/`recommendGraph`/`recommendReactStream` 四个封装；`recommendStream` 的 `RecommendationRequest` body 支持 `mode`。`frontend/src/types/index.ts`：`RecommendationRequest` 加 `mode?: 'pipeline' | 'react'`。
  3. **前端 RecommendPage**：清理"经典模式/批量对比/ReAct"入口，统一为流式（pipeline 默认，可选 react 切换）。
- **验证**：`grep -r "recommend/react\|recommend/graph\|'/recommend'" frontend/src` 零命中；`python -m pytest tests/ -m "not slow"` 不回归（`test_stream_recommend.py` 已覆盖统一入口）；前端 build 通过。

### 3.4 A4：eval oracle 与真实数据对齐

- **现状**（`docs/v2.0.0/eval-system.md` §7 + `eval/reports/` 实测）：`kb_retrieval` 的 `expected.chunk_ids` 是虚构标注（`handbook_chunk_finance_aid` 等），真实检索返回 `handbook_2025_<hash>:<N>` 体系 → live 0/10；`evaluation_comment` 断言数字（90.5/8/2/100）为虚构，真实输出是 71 门课/148.5 学分 → 0/10；`report_math` live 断言映射不到真实输出字段 → 1/10。**框架本身健康**（断言器/聚合/报告管道有单测），问题在 oracle 数据。
- **改动**：
  1. **`kb_retrieval`**：写一次性采集脚本 `python scripts/refresh_kb_retrieval_oracle.py`（运行后保留为维护脚本）：先从 MySQL `document_chunks`（`dataset_id LIKE '%handbook%'`，缺数据则脚本**显式提示并跳过而非写假值**）取真实 chunk_id，按章节关键词（奖学金/转专业/宿舍/学分/请假/处分…）映射到具体 chunk，回填 `python/eval_sets/kb_retrieval.jsonl` 的 `expected.chunk_ids`。`assertions[].field="hit_chunk_ids"` 的 value 同步替换。若某主题无精确 chunk，改用 `count_ge` 断言（命中该主题真实 chunk 数 ≥ 1）——**不用 `contains` 子串**（`_live_kb` 输出是 chunk_id 列表，子串断言落到 str(list) 不可靠）。
  2. **`evaluation_comment`**：新增真实数据版 `python/eval_sets/evaluation_comment_live.jsonl`（target_user_id=3123003252，断言数字改用真实成绩单统计：课程数 71、总学分 148.5、平均分等，从 `document_chunks` metadata_json 提取）。**断言用 `kind:"reference"`（数字白名单容差，runner 内置）而非 `contains`**——LLM 措辞不固定，contains 具体数字会 flake。原 `evaluation_comment.jsonl` 保留为 smoke 反例验证集（`--live` 时 runner 识别到字段不匹配则跳过或按新集跑）。
  3. **`report_math`**：live 分派**重写**——`_live_report_math` 从"工具层直调"改为**消费 `/api/v1/report` SSE**（上传真实样本 → 解析 `done` 事件 → 断言 `batch_id`/`students[]` 结构/`failed_students` 为空），与 `eval-system.md` 的"report_math → /api/v1/report 端到端"口径对齐；原"单元级"断言（fill/Journal/merge）保留在 smoke/单测（不用于 live）。新建 `python/eval_sets/report_math_live.jsonl` 声明 live 断言。
  4. **runner**：`python/eval/runner.py` 支持集级 `live` 注解（如 `evaluation_comment_live`、`report_math_live`），未对齐集在 live 模式下提示跳过而非误报 0/10。
- **验证**：`cd python; python eval/runner.py --set kb_retrieval --live`（需 API + 已摄入手册）通过率 > 0；`python eval/runner.py --set evaluation_comment_live --live` 通过率 > 0；smoke 模式 `python eval/runner.py --set evaluation_comment` 不回归。

### 3.5 A5：evaluation 三函数工具化（chat 委派前置）

- **现状**：`EVALUATION_AGENT_SPEC.allowed_tools`（`specs.py:92`）引用 `design_dimensions`/`compute_radar_values`/`generate_comment`，但三者是普通 async 函数（非 @tool、未注册）→ 若 chat 经 subagent 委派会静默缺工具（同 A1 类缺陷）。当前 evaluation 端点走 `agent/evaluation/service.py` 直调（`service.py:20-23`），不经过 registry。
- **改动**（决策 13/原则 1，为 Phase 3 chat 对话内生成评价铺路）：
  1. `python/tools/evaluation/design_dimensions.py`、`compute_radar_values.py`、`generate_comment.py` 各加 `@tool(args_schema=...)` 薄壳（**只包数据入参**：design_dimensions 的 snapshot / compute_radar_values 的 dimensions+snapshot / generate_comment 的 snapshot+radar+comment_type；**llm/on_token/timeout_seconds 等运行时注入参数不进 Pydantic schema**——薄壳内部构造对应 LLM 并经 `LLMTaskName` 命名，generate_comment 薄壳透传 `on_token=None`（不支撑流式回调），保证函数体复用、service 直调路径不变）。
  2. `python/tools/evaluation/__init__.py` 与 `python/tools/__init__.py` 导出三个工具；`agent/runtime.py` 注册。
  3. `agent/evaluation/service.py` 保持直调路径不变（service 调普通函数或工具 `func` 皆可，以不破坏现有调用为准）。
  4. 注册一致性测试（A1 的 `test_tool_registry_consistency.py`）覆盖 `EVALUATION_AGENT_SPEC` 白名单全部命中；补一条"薄壳直调 vs service 直调行为等价"单测。
- **验证**：`python -m pytest tests/test_evaluation_radar.py tests/test_evaluation_snapshot.py -v` 全绿（行为不变）；新注册测试全绿。

### 3.6 A6：skill 小修

- **现状**：`skills/image-generation/SKILL.md:18` 引用子模块 `submit-task.md`，实际文件名为 `generate-deliver.md`（调研发现）。
- **改动**：`python/skills/image-generation/SKILL.md` 引用改为 `commands/generate-deliver.md`。其余骨架 skill（knowledge-query/document-ingestion/deep-thinking）调研确认内容已填齐，仅 README 标注滞后——更新 `python/skills/README.md` 状态标注即可，不改内容；`ppt-generation` 保持骨架（PPT 后续 phase）。
- **验证**：`python/skills/` 下所有 SKILL.md 引用的子文件路径存在（脚本或人工核对）。

---

## 4. 交付面 B：前端架构迁移 + 四 Page 统一开发

> 后端契约已就绪（Phase 2 交付，`api/chat.py` / `api/report.py` / `api/evaluation.py` / `api/documents.py`），本交付面**前端架构迁移 + 纯前端消费 + 极小后端配套**。后端配套仅 §3.3 的 mode 字段（已在交付面 A）。

### 4.0 B0：前端架构迁移（Vite SPA → Next.js App Router）

- **动机**（选型调研 2026-08-16）：① 现有前端为 React19+antd6+zustand+tsx 纯 SPA，迁移到 React 生态 SSR 框架（Next.js）**零重写**；② 未来部分数据 CRUD 转 Java 数据服务（REST/OpenAPI），Next.js App Router **Route Handlers 可做 BFF**统一代理 Python(SSE)/Java(REST) 双后端；③ 未来独立管理平台走同 React 栈，两套项目共享设计体系。Nuxt 需 Vue 重写且与 tsx/antd 冲突，故不选。
- **改动**：
  1. 以 **`create-next-app@16`（锁定，node ≥ 20.9）** 初始化 `frontend/`（App Router + TypeScript + Tailwind），迁移 `package.json` 依赖（antd 6 / zustand / echarts 新增），废弃 `react-router-dom`、`vite`；**engines 收紧为 `^20.9.0 || >=22.0.0`**（Node 18.18 不满足 Next 16，需同步更新 AGENTS.md 前端 Node 说明）。
  2. 页面目录约定：`app/(main)/page.tsx`（推荐）/ `app/(main)/chat/page.tsx` / `app/(main)/report/page.tsx` / `app/(main)/evaluation/page.tsx` / `app/(main)/documents/page.tsx` / `app/(main)/monitor/page.tsx`；`app/layout.tsx` 承载顶部导航 + API 健康徽标。
  3. 现有 `RecommendPage.tsx` / `MonitorPage.tsx` / `StreamView.tsx` / `CourseInlineCard.tsx` / `stores/` 迁移为 `"use client"` 组件（目录 `components/`、`lib/`、`stores/`），业务逻辑零重写，仅适配路由与 Next 组件模型；**注意删除失效端点时会改动 StreamView.tsx 内 `mode==='react'` 分支与 stores 死代码**（§4.1 B1/E4），迁移时一并收敛。
  4. **SSE 只在 Client Component 消费**；zustand store 页面级实例化（避免 SSR 水合状态污染）；echarts 组件 `dynamic(..., { ssr: false })`。
  5. dev 代理：`next.config.ts` `rewrites()` 将 `/api`、`/health` 代理到 `http://localhost:8000`（等价原 vite proxy；`VITE_API_PROXY_TARGET` 语义保留为 `API_PROXY_TARGET` env）。
  6. **BFF 预留**：`app/api/` 下 Route Handlers 结构预留（本阶段不实现代理逻辑，仅建目录 + 文档化"Python SSE 直连、Java REST 走 BFF"的未来分线）。
- **验证**：`npm run dev` 起服务，六页面路由可达；`npm run build`（tsc + next build）通过；RecommendPage 推荐流式功能等价可用。

### 4.1 B1：SSE 客户端层 + 失效端点清理（迁移中完成）

- **现状**：`frontend/src/services/api.ts` 两份 SSE 解析重复；且仍导出指向后端已删除端点的 `recommend`/`recommendReact`/`recommendGraph`/`recommendReactStream`（§3.3 A3 处理）。迁移后目录为 `frontend/src/lib/`。
- **改动**：
  1. 抽取共享 `async function* consumeSSE(url, init, signal)`（fetch POST + reader 解析 `event:`/`data:` → yield `{event, data}`，支持 `AbortSignal`）。
  2. `recommendStream` 复用 `consumeSSE` 且 body 支持 `mode`；新增 `chat` / `chatStream` / `reportUpload`（下载直用事件 `url` 字段，无需拼接）/ `evaluation` / `evaluationMe` / `documentsUpload`（契约见 §4.2~4.5）。
  3. 删除四个失效端点封装（A3 前端部分在此落地）；**同步改写 `StreamView.tsx` 的 `mode==='react' ? api.recommendReactStream : api.recommendStream` 分支为统一 `recommendStream`（react 经 body.mode 切换）**，避免编译悬空引用。
- **验证**：`npm run build` 通过；`grep -r "recommend/react\|recommend/graph" frontend/src` 零命中。

### 4.2 B2：`types` 事件类型扩展

- **新增类型**（对齐后端 SSE 契约）：
  - chat：`ChatEvent = text{token,session_id} | tool{tool,status} | done{reply,messages_count,usage,latency_ms,ttft_ms} | error{code,message}`；
  - report：`ReportEvent = text | tool | progress{...} | student_done{student_id,name,status,format,url} | student_error{...} | done{batch_id,students,failed_students,warnings,summary} | error`；
  - evaluation：`EvaluationEvent = stage{stage,detail} | radar{target_user_id,dimensions,rejected,overall_theme} | comment_token{token} | done{...} | error`；
  - documents：`UploadResult{dataset_id,chunks_count,status}`；report 下载：**直接消费后端事件携带的完整 `url`**（`student_done`/`done.students[].url` 已含 token 下载链接，无 file_key/token/expires_at 单列）。
- **验证**：`npm run build`（tsc）通过。

### 4.4 B4：MainPage（智能对话）

- **功能**：左侧会话区（消息列表）+ 右侧可选推荐结果卡片；输入框支持发送与多轮（session_id 持久）、可选图片附件（data URL 预览后随消息发送）；markdown 渲染回复（`react-markdown` 或 antd `Typography` 简化版）。
- **SSE 消费**：`chatStream` 的事件渲染——`text` 追加 token（打字机）、`tool` 显示工具调用阶段徽标（start/end）、`done` 结束本轮并记录 usage/latency、`error` 结构化错误 + 重试按钮（复用 StreamView 的展示模式）。
- **约束**：不重复造轮子，视觉沿用 antd 6 主题 token；无第三方 markdown 库时用纯文本 + 换行（保持轻依赖）。
- **验证**：dev 环境真实对话一轮（知识库问题 + 推荐问题），text/tool/done 事件可见、错误可重试。

### 4.5 B5：ReportPage

- **功能**：多文件上传（antd Upload，多选，校验类型/大小）→ 参数（semester、user_message 可选）→ 提交消费 SSE → 进度条（progress）+ 逐学生结果（student_done 卡片：姓名/格式/下载按钮，链接直用事件 `url` 字段）+ 失败列表（student_error 可重试）→ 完成摘要（done.students 总数/failed）。
- **验证**：上传 2 个成绩单 xlsx 真实跑通，38 份 PDF 场景抽样验证下载 200。

### 4.6 B6：EvaluationPage（教师端 + 学生端）

- **教师端**：输入 `target_user_id` + 选择 `comment_type`（四类）→ `POST /evaluation` 消费 SSE：`stage` 阶段提示、`radar` 事件渲染雷达图（echarts）、`comment_token` 评语流打字机、`done` 展示评价结果（雷达 + 评语 + status）。`radar.dimensions` 有 rejected 时展示说明。
- **学生端**：Tab 切换 `GET /evaluation/me?user_id=` 展示历史评价列表（雷达 mini 图 + 评语 + comment_type + 时间）。
- **依赖**：`npm install echarts`（radar 图）。
- **验证**：教师端生成一条（真实 user 3123003252）→ 学生端列表可见。

### 4.7 B7：DocumentsPage（知识库上传）

- **功能**：上传 CSV/PDF + `dataset_name` + `chunk_strategy`（auto/recursive/fixed/paragraph 下拉）→ `POST /documents/upload` → 展示 `dataset_id/chunks_count/status`。附知识库查询入口说明（引导去智能对话页提问）。
- **验证**：上传一个 CSV 冒烟返回 200 + chunks_count > 0。

### 4.8 B8：后端配套收尾（极小）

- §3.3 的 `RecommendationRequest.mode` 透传（已列）；
- `GET /api/v1/report/download` 对 `token=__IMG__` 的内部图片直链继续放行（既有行为，image_generate 转存用）——确认无回归即可，不新增逻辑。

---

## 5. 交付面 C：记忆管理深化

### 5.1 C1：summary_prompt 对齐决策 11 五字段

- **现状**：`agent/main/factory.py:66-71` 用 `SummarizationMiddleware` 默认 prompt（SESSION INTENT / SUMMARY / ARTIFACTS / NEXT STEPS）。决策 11 要求五字段：Goal / Progress / Key Decisions / Next Steps / Critical Context。
- **改动**：
  1. 新建 `python/agent/main/prompts/summarization.txt`（中文指令模板，含五字段，直接复用 deepagents 默认模板的 `{messages}` 占位约定；五字段缺省时显式写 "None"）。
  2. `factory.py`：`SummarizationMiddleware(..., summary_prompt=_load_summarization_prompt())`。
  3. `_load_summarization_prompt()` 读文件失败时回退默认 prompt（日志告警），保证启动不崩。
  4. **作用域**：五字段 prompt 对所有 `enable_compaction=True` 的 spec 生效（main/report/evaluation/recommendation 均走同一 `build_deep_agent`）——文档确认此为预期（五字段通用摘要结构对各场景都成立），无需按 spec 分支。
- **测试**：新增 `tests/test_summarization_prompt.py`：断言 factory 构造时注入的 prompt 含五字段关键词、文件存在、回退路径。

### 5.2 C2：记忆提取 forked subagent 化（隔离上下文）

- **现状**：`agent/memory/extractor.py` 已用独立 LLM 调用（`build_extract_llm`）+ `asyncio.create_task` 后台执行（`api/chat.py:113` 同步端点与 `:233` stream 端点各一处），上下文已隔离；但提取逻辑内嵌在 `_run_extraction`，与主 agent 装配无关。
- **改动**（深化隔离 + 明确子任务边界）：
  1. `extractor.py` 提取执行体封装为独立可测组件 `MemoryExtractWorker`（`memory_extract` LLM + 校验 + upsert + 水位推进），与主 agent 零共享（无 checkpointer/无 tool）。
  2. `api/chat.py` 维持 `asyncio.create_task(maybe_extract(...))` 后台 forked 语义；任务失败仅退避记录，绝不阻塞响应。
  3. 补充 `LLMTaskName.MEMORY_EXTRACT` 使用一致性（已用）。
- **测试**：更新 `tests/test_memory_extractor.py` 断言 worker 隔离（不依赖主 agent）、失败幂等、水位推进。

### 5.3 C3：consolidation（跨会话记忆合并）

- **现状**：注入时 `list_memory_entries(limit=50, max_chars=3000)` 只做数量/长度截断；提取时 `<previous-memory>` 聚合最近 30 条。无显式去重合并 → 长会话累积后同义条目膨胀。
- **改动**：`agent/memory/consolidation.py`（新）：
  1. 确定性去重：按 `(kind, normalized content)` 保留最新，删除重复条目（`content_hash` 已存在于 `chat_memory_entries`，直接复用）。
  2. 相似合并（可选 LLM 提案）：当某 kind 条目数 > 上限（配置 `memory_consolidate_threshold_per_kind`，默认 15）时，调用一次 `MEMORY_EXTRACT` LLM 生成合并建议（输入该 kind 全部条目），Pydantic 校验后替换——失败则仅去重不合并（规则兜底）。
  3. 触发点：`maybe_extract` 成功后顺带执行（同后台任务）。
- **配置**：`python/config/settings.py` 增 `memory_consolidate_threshold_per_kind: int = 15`。
- **测试**：`tests/test_memory_consolidation.py`：确定性去重、超限触发合并、LLM 失败仅去重、无用户数据出文件（决策 19）。

### 5.4 C4：RedisSaver 按决策 20（配置预留 + 文档化，不迁移）

- **决策 20 条件**：python-api 实例数 > 1 时才迁移 `langgraph-checkpoint-redis`；单实例维持 SqliteSaver（当前 docker 单副本 → 不迁移）。
- **改动**：
  1. `python/config/settings.py`：`checkpoint_backend: str = "sqlite"`（可选 `"redis"`）。
  2. `agent/main/checkpointer.py`：`build_checkpointer()` 按配置分支——`sqlite` 走既有 `AsyncSqliteSaver`；`redis` 路径 import 探测 `langgraph_checkpoint_redis`（未装 → 显式 `RuntimeError` + 提示安装与决策 20 条件），复用 `redis_url`。
  3. 新增 `docs/v2.0.0/notes/2026-08-16-checkpoint-backend-switch.md`：记录切换条件、namespace 建议、回滚步骤（本阶段不执行切换）。
- **测试**：`tests/test_backend_checkpointer.py` 增分支断言：默认 sqlite 行为不变；`checkpoint_backend="redis"` 且依赖缺失 → RuntimeError。
- **验证**：`pytest tests/test_backend_checkpointer.py -v` 全绿；`checkpoint_backend` 默认 sqlite 运行 `docker compose up -d --build python-api` 正常。

---

## 6. 实施步骤（由内到外，逐层加变量）

> 每步 `python -m compileall <dirs>` + 聚焦测试，出错可回滚单步。前端每页独立验收。

| Step | 内容 | 交付面 | 验证点 |
|------|------|--------|--------|
| 1 | 注册一致性基建：A1 `image_generate_get` 注册 + A2 `compute_weighted_grade` 实装 + A5 evaluation 三函数 @tool 化 + `test_tool_registry_consistency.py` | A | `pytest tests/test_tool_registry_consistency.py tests/test_compute_weighted_grade.py tests/test_evaluation_radar.py -v` |
| 2 | A3 后端 `RecommendationRequest.mode` 透传 + A4 eval oracle 采集回填 + A6 skill 小修 | A | `pytest tests/test_stream_recommend.py -v`；`eval/runner.py --set kb_retrieval --live` |
| 3 | C1 summary_prompt 五字段 + C2 forked worker + C3 consolidation + C4 checkpoint_backend 预留 | C | `pytest tests/test_summarization_prompt.py tests/test_memory_extractor.py tests/test_memory_consolidation.py tests/test_backend_checkpointer.py -v` |
| 4 | 后端配套验收回归：`pytest tests/ -m "not slow"` 全绿 | A/C | 243 + 新增用例全绿 |
| 5 | **B0 前端架构迁移**：`create-next-app` 初始化 frontend/ + 依赖迁移 + 现有 RecommendPage/MonitorPage/StreamView/stores 迁为 `"use client"` + `next.config.ts` rewrites 代理 | B | `npm run dev` 六页面路由可达；`npm run build` 通过；推荐流式功能等价 |
| 6 | B1 SSE 客户端层（consumeSSE + 四组新封装 + 删失效端点）+ B2 types 扩展 | B | `npm run build`；`grep "recommend/react\|recommend/graph" frontend/src` 零命中 |
| 7 | B3 MainPage（chat 流） | B | dev 真实对话一轮（text/tool/done/error） |
| 8 | B4 ReportPage + B5 EvaluationPage（echarts `dynamic ssr:false`）+ B6 DocumentsPage | B | 上传 2 xlsx 下载 200；evaluation 教师→学生端可见；documents 冒烟 |
| 9 | 全量回归 + 文档同步（本 plan §7 → plan.md；AGENTS.md 若涉及新配置保持准确） | 全部 | `pytest -m "not slow"` + `npm run build` + `eval/runner.py --set chat_intent` |

---

## 7. 后续 phase 输入清单（本阶段不做，写回 plan.md）

| 项 | 依据 | 当前载体 |
|----|------|---------|
| PPT 生成系统（`ppt_generate` DSL→PPTX、PPTGeneratePage、skills/ppt-generation 填充、`PPT_AGENT_SPEC` 激活） | plan.md Phase 3 交付 4；决策 7 | `agent/ppt/` 骨架、`skills/ppt-generation/` 占位 |
| 图片生成独立 Page（ImageGeneratePage） | 决策 16 | `image_generate` 工具已闭环 |
| FastGPT 二次开发 mcp_server + Python MCP client 接入 + KB 主链路评估 | 决策 6/8；plan.md Phase 3 交付 1/2 | `mcp_client.py` 基础设施已就绪 |
| Java 数据服务（身份/鉴权/REST+MQ/Redis 运维） | 决策 21 | context user_id 临时口径；Next.js `app/api/` BFF 代理层已预留 |
| **独立管理平台**（两套独立项目，React 栈，复用 antd 设计体系；对用户前端/Java 服务做管理操作） | 选型调研（2026-08-16） | 前端架构已定 Next.js，管理平台后续单独仓库立项 |
| RedisSaver 实际迁移 | 决策 20（实例数 > 1 时） | `checkpoint_backend` 配置预留 |
| LLM-as-judge / NDCG / 看板 / 插件市场 / harness 可视化 / 断裂幻觉兜底演示 | plan.md Phase 4 | `eval/runner.py --judge` 预留 |

---

## 8. 附录：关键文件索引

| 文件 | 角色 |
|------|------|
| `python/agent/runtime.py` | 工具注册清单（A1/A5 改动点） |
| `python/tools/report/compute_weighted_grade.py` | stub 实装（A2） |
| `python/models/schemas.py` | `RecommendationRequest.mode`（A3） |
| `python/api/recommend.py` | mode 透传（A3） |
| `python/eval_sets/kb_retrieval.jsonl` / `evaluation_comment_live.jsonl` | oracle 对齐（A4） |
| `python/tools/evaluation/*.py` | 三函数 @tool 化（A5） |
| `python/skills/image-generation/SKILL.md` | 引用修正（A6） |
| `frontend/`（Next.js App Router：`app/(main)/*/page.tsx`、`app/layout.tsx`、`app/api/` BFF 预留） | 架构迁移 + 路由（B0） |
| `frontend/src/lib/api.ts` / `types.ts` / `lib/sse.ts` | SSE 消费器 + 类型（B1/B2） |
| `frontend/src/pages/*`（迁移后的 `"use client"` 页面：Main/Report/Evaluation/Documents） | 四 Page（B3-B6） |
| `frontend/next.config.ts` | rewrites 代理 Python 后端（B0） |
| `python/agent/main/prompts/summarization.txt` / `factory.py` | 五字段 prompt（C1） |
| `python/agent/memory/extractor.py` / `consolidation.py` | forked worker + consolidation（C2/C3） |
| `python/config/settings.py` / `agent/main/checkpointer.py` | `checkpoint_backend` 预留（C4） |
| `docs/v2.0.0/notes/2026-08-16-checkpoint-backend-switch.md` | 决策 20 切换文档（C4） |