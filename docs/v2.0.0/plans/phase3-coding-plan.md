# Phase 3 编码实施计划 — 扩展收尾 / 前端架构迁移 + 四 Page / 记忆管理深化

> 本文档是 `plans/phase-3-extensions.md`（详细设计）的**编码执行清单**：按工作流拆解为可落地的编码任务（文件级），带依赖顺序与验证命令。编码时以本文件为任务主索引，设计细节（契约/事件协议/防线机制）回查详细计划。
>
> 日期：2026-08-16
> 状态：待执行
> 验收：十一条试金石（详细计划 §1.4），全绿 = Phase 3 GO

## 一、概览

### 1.1 工作流划分与依赖

```
W-A 地基修复 ──┬─→ W-B 记忆深化 ──→ W-C 后端回归（W-A/B 全前置）
               └─→ W-D 前端架构迁移(Next.js) ─→ W-E SSE客户端层 ─→ W-F 四Page ─→ W-G 全量回归与文档
```

| 工作流 | 内容 | 依赖 | 阶段产物 |
|--------|------|------|---------|
| W-A | 交付面 A：image_generate_get 注册 + compute_weighted_grade 实装 + mode 透传 + eval oracle 采集 + evaluation 三函数 @tool 化 + skill 小修 + 注册一致性测试 | 无 | 地基一致、无 stub、eval 真值对齐 |
| W-B | 交付面 C：summary_prompt 五字段 + forked worker 提取 + consolidation + checkpoint_backend 预留 | W-A | 记忆深化（交付面 C） |
| W-C | 后端验收回归：`pytest -m "not slow"` 全绿 | W-A/B | 后端基线 243+ |
| W-D | 交付面 B0：Vite SPA → Next.js App Router 迁移（create-next-app + 依赖 + 现有页面 `"use client"` 迁移 + rewrites 代理） | W-A | frontend/ 可 run/build |
| W-E | 交付面 B1/B2：共享 SSE 消费器 + chat/report/evaluation/documents 封装 + types 扩展 + 失效端点删除 | W-D | 前端 API 客户端层 |
| W-F | 交付面 B3~B6：MainPage / ReportPage / EvaluationPage（echarts）/ DocumentsPage | W-D/E | 四 Page 可交互 |
| W-G | 全量回归 + 文档同步（§7 清单 → plan.md；AGENTS.md 保持准确） | 全部 | 十一条试金石 |

### 1.2 编码纪律

- 所有 ChatOpenAI 构造走 `ai.llm_client.build_chat_openai`（AGENTS.md 硬约束），新 LLM 调用必须带 `LLMTaskName`
- 工具错误返回 `isError` 结构化结果（`{code, message}`），不抛异常
- 新前端 API 必须 SSE：`done` 终结 + 结构化 `error`；SSE 消费只在 Next.js Client Component
- 测试 marker 只用既有 `unit/integration/slow/agent/api`
- 每工作流结束跑对应验证命令；W-C 起每步保持 `cd python; python -m pytest tests/ -m "not slow" -q` 全绿
- 前端改动每步 `cd frontend; npm run build`（tsc + next build）通过再前进

---

## 二、工作流 A：地基修复（交付面 A）

**目标**：注册中心与 spec 白名单一致、stub 清零、eval oracle 真值化、evaluation 可委派。（前端失效端点清理由 W-E 承接，见 E2/E4。）

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| A1 | image_generate_get 注册 | `python/agent/runtime.py` | import 清单 + `register_many` 补 `image_generate_get`（现 `tools/image/image_generate.py:126` 已定义、`tools/__init__.py` 已导出、`specs.py:50` 已引用，仅注册遗漏） |
| A2 | compute_weighted_grade 实装 | `python/tools/report/compute_weighted_grade.py` | 删 `raise NotImplementedError`，实现：`total = round(display_eval*0.3 + exam_eval*0.7 + bonus, 2)`，返回 `{total, display_weighted, exam_weighted, bonus}`；入参已由 args_schema 约束（0-100 / 0-20），函数内再 clamp 防 NaN |
| A3 | 注册一致性测试锁死 | `python/tests/test_tool_registry_consistency.py`（新） | ① 对 specs 里每个 AgentSpec 断言 `allowed_tools ⊆ registry.get_all()` 可获取集合；② 断言每个已注册工具名非空、`args_schema` 存在。**注意 mock 边界**：注册会 import `tools/image`（即梦 MCP）、`tools/code`（E2B）等带外部密钥模块——测试须 mock `config.get_settings()`（完整 mock，含 `mcp_servers={}`），且不真连 MCP（仅注册元数据） |
| A4 | compute_weighted_grade 单测 | `python/tests/test_compute_weighted_grade.py`（新） | 边界（0,0,0→0）、常规（60,80,5→**79.0** 即 18+56+5）、上限（100,100,20→120）、非法输入防御 |
| A5 | RecommendationRequest.mode | `python/models/schemas.py` | `RecommendationRequest` 增 `mode: str = "pipeline"`，`pattern="^(pipeline|react)$"` |
| A6 | recommend api 透传 mode | `python/api/recommend.py` | `/recommend/stream` 读 `req.mode` 传给 `supervisor.stream_recommend_unified(mode=...)`（react 失败自动兜底 pipeline，既有逻辑零编排改动） |
| A7 | evaluation 三函数 @tool 化 | `python/tools/evaluation/design_dimensions.py`、`compute_radar_values.py`、`generate_comment.py` | 各加 `@tool(args_schema=...)` 薄壳：**只包数据入参**（design_dimensions 的 snapshot / compute_radar_values 的 dimensions+snapshot / generate_comment 的 snapshot+radar+comment_type）；**llm/on_token/timeout_seconds 等运行时注入参数不进 Pydantic schema**——薄壳内部构造 LLM 并经 `LLMTaskName` 命名，generate_comment 薄壳透传 `on_token=None`（不支撑流式回调）；函数体复用，service 直调路径不变 |
| A8 | evaluation 三工具注册 | `python/agent/runtime.py` | register_many 补 `design_dimensions`/`compute_radar_values`/`generate_comment`；`agent/evaluation/service.py` 直调路径不动；补"薄壳直调 vs service 直调行为等价"单测 |
| A9 | eval oracle 采集脚本 | `python/scripts/refresh_kb_retrieval_oracle.py`（新） | 从 MySQL `document_chunks`（`dataset_id LIKE '%handbook%'`，**缺数据则显式提示并跳过而非写假值**）取真实 chunk_id，按章节关键词（奖学金/转专业/宿舍/学分/请假/处分…）映射，回填 `python/eval_sets/kb_retrieval.jsonl` 的 `expected.chunk_ids` 与 `assertions[].value`；无精确主题 → 用 **`count_ge` 断言**（命中该主题真实 chunk 数 ≥1，避免 overfit 单一 chunk_id；**不用 `contains` 子串**——`_live_kb` 输出是 chunk_id 列表，子串断言落到 str(list) 不可靠）；脚本幂等可重跑 |
| A10 | evaluation_comment 真实数据版 | `python/eval_sets/evaluation_comment_live.jsonl`（新） | target_user_id=3123003252；断言数字取自真实成绩单统计（课程数 71 / 总学分 148.5 / 平均分等，从 `document_chunks` metadata_json 提取）；**断言用 `kind:"reference"`（数字白名单容差，runner 内置）而非 `contains`**（LLM 措辞不固定，contains 具体数字会 flake）；原集保留 smoke |
| A11 | report_math live 端到端化 | `python/eval/runner.py`、`python/eval_sets/report_math_live.jsonl`（新） | **重写 `_live_report_math`**：从"工具层直调"改为消费 `/api/v1/report` SSE（上传真实样本 → 解析 `done` 事件 → 断言 `batch_id`/`students[]` 结构/`failed_students` 为空），对齐 `eval-system.md` "report_math → /api/v1/report 端到端"口径；新建 `report_math_live.jsonl` 声明 live 断言；原单元级断言（fill/Journal/merge）留 smoke/单测；runner 支持集级 live 注解，未对齐集 live 模式提示跳过 |
| A12 | skill 小修 | `python/skills/image-generation/SKILL.md`、`python/skills/README.md` | SKILL.md 引用 `commands/generate-deliver.md`（现误写 submit-task.md）；README 状态标注更新（knowledge-query/document-ingestion/deep-thinking 已填齐）；ppt-generation 保持骨架 |

**验证**：
```bash
cd python && python -m compileall agent/ tools/ models/ api/ scripts/
cd python && python -m pytest tests/test_tool_registry_consistency.py tests/test_compute_weighted_grade.py tests/test_evaluation_radar.py tests/test_stream_recommend.py -v
cd python && python eval/runner.py --set kb_retrieval --live        # 需 API + 已摄入手册，通过率 > 0
cd python && python eval/runner.py --set evaluation_comment_live --live  # 通过率 > 0
```
**风险卡点**：eval oracle 依赖已摄入数据 → 先 `run_kb_test.py` 确认 KB 可用；chunk_id 从 MySQL 采集不依赖在线检索。

---

## 三、工作流 B：记忆深化（交付面 C）

**目标**：compaction 摘要五字段、提取隔离子任务、记忆去重合并、checkpoint 后端配置预留。

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| B1 | summarization prompt | `python/agent/main/prompts/summarization.txt`（新） | 中文指令模板：五字段 Goal / Progress / Key Decisions / Next Steps / Critical Context（缺省写 "None"）；复用 deepagents 默认模板 `{messages}` 占位约定 |
| B2 | factory 注入 prompt | `python/agent/main/factory.py` | `_load_summarization_prompt()`（读文件失败 → 回退默认 + 日志告警）；`SummarizationMiddleware(..., summary_prompt=...)` |
| B3 | prompt 注入测试 | `python/tests/test_summarization_prompt.py`（新） | 断言注入的 prompt 含五字段关键词、文件存在、回退路径（mock 文件缺失） |
| B4 | forked worker 提取 | `python/agent/memory/extractor.py` | 提取执行体封装 `MemoryExtractWorker`（memory_extract LLM + Pydantic 校验 + upsert + 水位推进），与主 agent 零共享；`maybe_extract` 调用 worker；失败退避幂等保持 |
| B5 | extractor 测试更新 | `python/tests/test_memory_extractor.py` | 断言 worker 隔离（不依赖主 agent）、失败幂等、水位推进 |
| B6 | consolidation | `python/agent/memory/consolidation.py`（新） | ① 确定性去重：`(kind, normalized content)` 保留最新；② 某 kind 超限（配置阈值）时一次 `MEMORY_EXTRACT` LLM 合并建议（Pydantic 校验）→ 替换；失败仅去重不合并；触发点：`maybe_extract` 成功后顺带执行 |
| B7 | consolidation 配置 | `python/config/settings.py` | 增 `memory_consolidate_threshold_per_kind: int = 15` |
| B8 | consolidation 测试 | `python/tests/test_memory_consolidation.py`（新） | 确定性去重、超限触发合并、LLM 失败仅去重、无用户数据写出文件（决策 19） |
| B9 | checkpoint_backend 预留 | `python/config/settings.py`、`python/agent/main/checkpointer.py` | settings 增 `checkpoint_backend: str = "sqlite"`；`build_checkpointer()` 分支：sqlite 走既有 AsyncSqliteSaver；redis 路径 import 探测 `langgraph_checkpoint_redis`（缺失 → 显式 RuntimeError + 决策 20 提示），复用 `redis_url` |
| B10 | checkpoint 测试扩展 | `python/tests/test_backend_checkpointer.py`（**已存在，扩展**） | 现有 `mock_settings` fixture 只 mock 了 `checkpoint_sqlite_path`——补 `checkpoint_backend` 字段；增分支断言：默认 sqlite 行为不变；`checkpoint_backend="redis"` 且依赖缺失 → RuntimeError |
| B11 | 决策 20 文档 | `docs/v2.0.0/notes/2026-08-16-checkpoint-backend-switch.md`（新） | 切换条件（实例数 > 1）、namespace 建议、回滚步骤（本阶段不切换） |

**验证**：
```bash
cd python && python -m pytest tests/test_summarization_prompt.py tests/test_memory_extractor.py tests/test_memory_consolidation.py tests/test_backend_checkpointer.py -v
cd python && python -m compileall agent/ config/
```

---

## 四、工作流 C：后端回归

**目标**：W-A/B 后后端基线全绿。

**验证**：
```bash
cd python && python -m pytest tests/ -m "not slow" -q
```
预期：243 + 新增用例全绿，无 skip/xfail 新增。

---

## 五、工作流 D：前端架构迁移 Vite → Next.js（交付面 B0）

**目标**：`frontend/` 成为 Next.js App Router 工程，现有功能等价迁移，build 通过。

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| D1 | create-next-app | `frontend/`（整目录重建） | `npx create-next-app@16.3.1 frontend --ts --tailwind --eslint --app --src-dir --no-import-alias`（**固定 16.3.1，node ≥ 20.9**）；`package.json` **engines 收紧为 `^20.9.0 || >=22.0.0`**（Node 18.18 不满足 Next 16，需同步 G4 更新 AGENTS.md 的 Node 说明）；package.json 固定 `next` 精确版本避免环境漂移 |
| D2 | 依赖迁移 | `frontend/package.json` | 加 antd 6 / @ant-design/icons / zustand / echarts；移除 vite / react-router-dom；保留 react 19 / typescript |
| D3 | 现有代码迁移 | `frontend/src/components/`（StreamView、CourseInlineCard）、`frontend/src/stores/`、`frontend/src/types/` | 迁为 `"use client"` 组件，业务逻辑零重写；`RecommendPage`/`MonitorPage` 迁移为 `app/(main)/page.tsx`、`app/(main)/monitor/page.tsx`（页面组件 `"use client"` 包裹）；zustand store 页面级实例化避免 SSR 水合污染；**一并处理失效端点引发的变化**：StreamView 内 `mode==='react' ? api.recommendReactStream : api.recommendStream` 分支改为统一 `recommendStream`（react 经 body.mode 切换）、被删功能专用的 stores 死代码收敛 |
| D4 | 布局与导航 | `frontend/src/app/layout.tsx`（根布局） | 顶部导航（推荐/智能对话/报告/评价/知识库/系统监控）+ API 健康轮询徽标（迁移 Layout.tsx 逻辑）；`(main)` 路由组承载六页面 |
| D5 | BFF 预留 + 代理 | `frontend/next.config.ts` | `rewrites()`：`/api/:path*`、`/health` → `process.env.API_PROXY_TARGET || 'http://localhost:8000'`；`app/api/` 目录建 README 说明未来 Python SSE 直连 / Java REST 走 BFF 分线 |
| D6 | echarts 动态加载 | `frontend/src/components/RadarChart.tsx`（新） | `dynamic(() => import('...'), { ssr: false })`，客户端挂载后渲染（防水合告警） |

**验证**：
```bash
cd frontend && npm ci && npm run dev &   # 六页面路由可达
cd frontend && npm run build              # tsc + next build 通过
```
**风险卡点**：antd 6 peerDependencies `react >=18.0.0`，React 19 原生兼容，**无需** `@ant-design/v5-patch-for-react-19`（该补丁只针对 antd v5）；SSR 下 `window` 未定义 → 全部交互组件 `"use client"`。

---

## 六、工作流 E：SSE 客户端层 + types（交付面 B1/B2）

**目标**：前端统一 API 客户端，四组新端点封装 + 失效端点删除。

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| E1 | 共享 SSE 消费器 | `frontend/src/lib/sse.ts`（新） | `async function* consumeSSE(url, init, signal)`：fetch POST + reader 按行解析 `event:`/`data:` → yield `{event, data}`；无法解析行跳过 |
| E2 | API 客户端 | `frontend/src/lib/api.ts`（由 services/api.ts 迁移） | 复用 `consumeSSE`：`recommendStream`（body 支持 `mode`）+ 新增 `chat`（JSON）/`chatStream`/`reportUpload`（multipart，**下载直用事件 `url` 字段，无需拼接**）/`evaluation`/`evaluationMe`/`documentsUpload`（multipart JSON）；**删除** recommend/recommendReact/recommendGraph/recommendReactStream 四封装 |
| E3 | types 扩展 | `frontend/src/types/index.ts` | 新增 ChatEvent/ReportEvent/EvaluationEvent/UploadResult 类型（对齐 §4.2 契约；**report 下载不建 DownloadInfo**，直接用 `student_done`/`done.students[].url`）；`RecommendationRequest` 加 `mode?: 'pipeline'\|'react'` |
| E4 | 失效入口清理 | `frontend/src/app/(main)/page.tsx`（推荐页）+ StreamView 引用 | 移除"经典模式/批量对比/ReAct"入口，统一流式（pipeline 默认，可选 react 切换）；**StreamView.tsx 的 `mode==='react' ? api.recommendReactStream : api.recommendStream` 分支改写为统一 `recommendStream`（react 经 body.mode）**，否则删除封装后编译悬空 |

**验证**：
```bash
cd frontend && npm run build
# grep 确认失效端点清零
```

---

## 七、工作流 F：四 Page（交付面 B3~B6）

**目标**：MainPage / ReportPage / EvaluationPage / DocumentsPage 可交互。

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| F1 | MainPage（智能对话） | `frontend/src/app/(main)/chat/page.tsx` | `"use client"`；消息列表 + 输入框（session_id 持久、图片附件可选）+ `chatStream` 消费：`text` 打字机 / `tool` 阶段徽标 / `done` 结束（usage/latency）/ `error` 结构化 + 重试；回复 markdown 渲染（无第三方库则纯文本+换行，保持轻依赖） |
| F2 | ReportPage | `frontend/src/app/(main)/report/page.tsx` | antd Upload 多选（≤20、≤10MB）+ semester/user_message 参数 → `reportUpload` 消费 SSE：`progress` 进度条、`student_done` 卡片（姓名/格式/下载按钮走 reportDownloadUrl）、`student_error` 列表、`done` 摘要（总数/failed）；失败可重试 |
| F3 | EvaluationPage（教师端） | `frontend/src/app/(main)/evaluation/page.tsx` | target_user_id + comment_type（四类）→ `evaluation` 消费 SSE：`stage` 阶段提示 / `radar` 渲染 RadarChart（echarts，rejected 展示说明）/ `comment_token` 打字机 / `done` 完整结果 |
| F4 | EvaluationPage（学生端） | 同上（Tab 切换，数据源 `GET /evaluation/me?user_id=`，见 api/evaluation.py） | `evaluationMe(user_id)` → 历史评价列表（radar mini + 评语 + comment_type + 时间） |
| F5 | DocumentsPage | `frontend/src/app/(main)/documents/page.tsx` | 上传 CSV/PDF + dataset_name + chunk_strategy（auto/recursive/fixed/paragraph）→ `documentsUpload` → 展示 dataset_id/chunks_count/status；引导去智能对话页提问 |

**验证**：
```bash
cd frontend && npm run build
# dev 手动冒烟：
#  chat 一轮（知识库问题 + 推荐问题）→ text/tool/done 可见
#  report 上传 2 个 xlsx → 下载 200
#  evaluation 教师端生成（3123003252）→ 学生端 /me 列表可见
#  documents 上传 CSV → chunks_count > 0
```

---

## 八、工作流 G：全量回归 + 文档同步

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| G1 | 后端回归 | — | `cd python && python -m pytest tests/ -m "not slow" -q` 全绿 |
| G2 | 前端构建 | — | `cd frontend && npm run build` 通过 |
| G3 | eval 不回归 | — | `cd python && python eval/runner.py --set chat_intent`（smoke） |
| G4 | 文档同步 | `docs/v2.0.0/plan.md`、`AGENTS.md` | plan.md Phase 3 状态更新 + §7 后续 phase 输入清单写入；AGENTS.md 增补 `checkpoint_backend` 配置与 Next.js 前端说明（若必要）；本文件状态改 ✅ |

---

## 九、验收清单（对应详细计划 §1.4 十一条试金石）

- [ ] 注册一致性：image_generate_get 已注册、compute_weighted_grade 已实装、白名单 ⊆ 注册表测试全绿、evaluation 三工具注册
- [ ] 前端失效端点清零；RecommendationRequest 前后端均含 mode；/recommend/stream 支持 mode="react"
- [ ] 前端已迁移 Next.js：四 Page 可交互（chat 流 / report 下载 200 / evaluation 教师→学生端 / documents 上传）
- [ ] App Router 真路由六菜单；废弃 display:none 假路由
- [ ] eval oracle 对齐：kb_retrieval live > 0、evaluation_comment_live > 0
- [ ] summary_prompt 五字段注入且有单测
- [ ] forked worker 提取隔离 + 失败幂等测试
- [ ] consolidation 去重合并 + 单测
- [ ] checkpoint_backend 配置预留 + 分支单测 + 决策 20 文档
- [ ] pytest not-slow 全绿 + npm run build 通过
- [ ] plan.md/AGENTS.md 文档同步