
# Repository Instructions

每次提问后大模型的回答 ── 必须带有问候"主人"二字。

window 系统调用 bash 工具时优先考虑 git bash，优先级：git bash > powershell > cmd。

详细架构与历史决策见 `CLAUDE.md`；前端 (Next.js 16 App Router) 详见 `docs/v2.0.0/frontend-architecture.md`。

## Layout And Entrypoints

- 工作区由 `python/`（FastAPI 后端）+ `frontend/`（Next.js 16 前端）+ `docs/` 组成。Python 命令从 `python/` 目录运行（`pytest.ini` 配置 package layout）。
- 后端入口 `python/agent/app.py`（`agent.app:app`），lifespan 启动时初始化 `agent.runtime`（supervisor / 仓储 / ToolRegistry / main deep agent 单例）。
- 前端入口 `frontend/src/app/`（App Router），URL 挂载链路见 `docs/v2.0.0/frontend-architecture.md` § 3；（main）路由组包裹 8 个页面 + Hub，login 独立。
- 三层分离（与 CLAUDE.md 一致）：`agent/`（编排）→ `tools/`（原子 @tool + ToolRegistry）→ `skills/`（SKILL.md 文档，SkillsMiddleware 渐进式加载）。
- 主要子包：`python/agent/main/`（v2 main_agent 工厂 + 5 个 spec）｜`python/agent/recommend/`（v1 推荐管线，已降级为 main_agent 的子 agent）｜`python/agent/report/`、`evaluation/`（编排）｜`python/agent/documents/`（RAG 上传）｜`python/agent/memory/`（注入/持久化/提取）。
- 主 agent 持久化 checkpoints 到 SQLite，从 `python/memories/AGENTS.md` 读长期记忆（运行时文件，与本仓库 `AGENTS.md` 不同名易混）。

## Setup And Commands

后端（root `.venv` + python 双 `.env`）：
```bash
python -m venv .venv && python -m pip install -r python/requirements.txt
cd python && python -m pytest tests/test_file.py -v          # 单文件
cd python && python -m pytest tests/ -m "not slow" -v         # 默认本地 suite（mock LLM，不连真实后端）
cd python && python -m pytest tests/ --cov --cov-report=term-missing   # 覆盖率（.coveragerc 已存在）
```

pytest 已启用严格 markers + auto asyncio；用 `unit / integration / slow / agent / api` 五个声明 marker，不发明新 marker。`not slow` 是默认验证目标，mock 必须避免真实 LLM 调用。

离线 eval：`cd python && python eval/runner.py --set <name>`（断言式）；`--live` 调真实 API；`--judge` **当前是占位（仅打印"未实装"提示），不真正调用 LLM-as-judge**——LLM judge（faithfulness / answer_relevancy / rubric）属 Phase 4。JSONL 里的 `judge` 字段（`metric: exact | code | recall`）就是现在生效的断言式判断。集在 `python/eval_sets/*.jsonl`，报告落 `python/eval/reports/`。

数据导入（cwd = `python/`）：
```bash
python scripts/ingest_course_dataset.py --limit 20          # 冒烟
python scripts/ingest_course_dataset.py                       # 全量
python scripts/ingest_student_handbook.py                     # 学生手册（public 分区）
python scripts/ingest_transcript_desensitized.py --user-id <id> --name <姓名>   # 个人成绩单
```
CSV 源：`course_dataset_tools/output/course.csv`（旧名 `public_elective_courses.csv`）。RAG 摄入策略见 `docs/v2.0.0/rag-ingest.md`。

前端（Node ≥ 20.9；package.json `engines: ^20.9.0 || >=22.0.0`，Next.js 16 不支持 Node 18）：

**默认推荐：通过 docker 容器跑**（避免 host 转发丢 SSE body 的 bug）：

```bash
# 启动前端容器（frontend Dockerfile ARG NODE_BASE_IMAGE 默认 node:20-slim；改 package.json 后 --no-cache 重 build）
docker compose -f docker-compose.yml -f docker-compose.pull-mirror.yml --profile frontend up -d --build frontend
# → http://localhost:3001
# 关闭：docker compose --profile frontend stop

# 镜像源不可达时显式传 build-arg（跟 python-api 同模式）
NODE_BASE_IMAGE=docker.1ms.run/library/node:20-slim docker compose -f docker-compose.yml -f docker-compose.pull-mirror.yml --profile frontend build --no-cache frontend
```

**仅调试/快速验证时**（host 上跑 `npm run dev`，**已知有 host 转发 bug，SSE 可能 body 被截断**）：

```bash
cd frontend && npm ci
npm run dev                # http://localhost:3001（Turbopack ~0.6s ready）
npm test                   # vitest run（路 0 基建；jsdom + polyfill 已 setup）
npm run test:watch
npm run test:coverage      # 需要 @vitest/coverage-v8 安装
npm run lint               # ESLint 9 + eslint-config-prettier
npm run format             # prettier --write
npm run build              # 2.6s + 10 路由全静态
```

前端 dev server 代理 `/api` + `/health` → `API_PROXY_TARGET`（默认 `http://127.0.0.1:8000`；**容器内**默认 `http://python-api:8000`）；`next.config.ts` rewrites。

## Environment And Services

- `.env` 加载顺序：仓库根 `.env` 先，python/.env 后覆盖；Docker 仅注入 `python/.env`。
- 启动：`docker compose up -d`（mysql 宿主机 3307→容器 3306、redis、minio、etcd、milvus、python-api）。Python 代码变更后：`docker compose up -d --build python-api`（PYTHON_IMAGE 默认是 docker.io/library/python:3.12-slim，registry-1.docker.io 不可达时**必须显式传** `--build-arg PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.12-slim`，缓存复用率高）。
- **docker desktop 转发 host → container:8000 偶发 502**：dev proxy 层 bug；用 `127.0.0.1:8000` 代替 `localhost` 缓解，**或（推荐）`docker compose --profile frontend up -d --build frontend` 让 frontend 容器内走 service 名 `python-api:8000` 彻底绕开**——同步请求可能 502，SSE 长连接可能 body 被截断为空（前端报 network error）。详见前端段命令。
- 启动门槛：必须 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`；`EMBEDDING_PROVIDER` ∈ `local / openai / dashscope_multimodal`（local 跳过 embedding key 检查）。证书 / SAN 问题：相关 env 设 `HTTPX_VERIFY_SSL=false` 后重建容器。

## Implementation Constraints

- `ChatOpenAI` 全部走 `ai.llm_client.build_chat_openai`，**不直接 new ChatOpenAI**；保留 `LLMTaskName` run names。
- `config.get_settings()` 是 `lru_cache`-backed → 测试 **patch `config.get_settings` 加完整 mock**，不要在 import 后改环境变量。
- 编排在 `agent/`，原子工具在 `tools/`，过程式技能在 `skills/`；工具在 `agent/runtime.py` 里 `build_main_agent()` 之前用 `ToolRegistry.register_many` 注册。
- Redis 缓存**候选课程 ID**（不是完整对象），课程事实仍来自 MySQL；硬约束是确定性过滤发生在 rerank 之前，不是软排序偏好。

## Frontend API Contract

- 修改或新增前端面向 API **默认 SSE 流式**：使用 SSE 或仓库既定流式事件协议，不要新加最终同步 JSON 端点。
- 流必须暴露有意义的 progress / results 事件，**必须以 `done` 事件显式终止**；失败走结构化 `error` 事件，**不能静默断流**。
- 前端面向 API 的测试必须**消费流并断言**：事件顺序 / 有意义 payload / 终态 `done` / 结构化 error；仅有同步 mock 不算充分验证。
- 前端通过 Next.js rewrites 直连 Python 后端；`app/api/` 是预留 BFF 层（未来 Java REST），**当前故意空**，不要在里面写真实 proxy 逻辑。

**SSE 路 2 协议**（后端 4 个 SSE 端点统一）：每条事件携带 `id: <int>` 字段（按 thread_id 单调递增）；客户端 `Last-Event-ID` HTTP header 续传；前端 `consumeSSEWithRetry` 指数退避（500ms→1s→2s, max 3）。具体见 `frontend/src/lib/sse.ts` + `python/services/sse_event_buffer.py`。

## Knowledge Base RAG

- Milvus `document_chunks`（schema `user_id` partition key）；公开学生手册 `user_id=public`；个人成绩单 per-user 分区，仅本人可检索。
- 摄入流水线：解析（pypdf, pymupdf 兜底表格）→ NFKC normalize → 脱敏（姓名→`[姓名]`、学号 mask、班级→年级、日期→年；课程名/学分/成绩保留供本人查询）→ 递归分块（heading-aware + 中文分隔）→ embed → Milvus upsert + MySQL 元数据。
- 脚本：`python scripts/ingest_student_handbook.py`（学生手册，public）/ `python scripts/ingest_transcript_desensitized.py --user-id <id> --name <姓名>`（个人）。`--embedding local` 是无配额冒烟。
- 端到端冒烟（需 API）：`python scripts/run_kb_test.py scripts/kb_test_transcript.json`；关键词命中 / 脱敏 case 在 `kb_test_*.json`。
- 上传运行时路径：`POST /api/v1/documents/upload`（multipart `file` + `dataset_name` + `chunk_strategy`），由 `python/agent/documents/service.py` 服务。
- 摄入幂等：`DocumentVectorRepository.delete_by_dataset` + `DocumentRepository.replace_chunks` 替换整个 dataset，新旧知识不混存。
- **2026-08-25 重构**：`query_knowledge` 拆成 `query_handbook`（手册/公开 user_id=public 分区，top_k=5） + `query_transcript`（个人成绩单，仅本人 user_id 分区，top_k=3，强权限隔离）。两类问题不再共用 top_k 候选集、不再混排。答案**必须引用** `source_doc_name` / `page_number`；检索为空时不准编造。设计动机见 `docs/v2.0.0/notes/2026-08-25-knowledge-tools-split.md`。
- LangSmith RAG 质量门（context recall / faithfulness）见 `docs/v2.0.0/plan.md`；基线**必须真实端到端测量**后再调 top_k / chunking / rerank。

## User Context Injection

- 当前请求 `user_id` 通过 `agent.main.context.user_context()` (ContextVar) 注入 main_agent run；`/api/v1/chat` 和 `/api/v1/chat/stream` 包装 agent 调用，并在 `configurable` 里也放 `user_id`。
- 工具需要当前 user **必须** `from agent.main.context import get_current_user_id`；**绝不**让 LLM 从对话猜 `user_id`，**绝不**把 `user_id` 加进工具的 `args_schema`。
- 遵循此模式的工具：`query_transcript`（个人成绩单）、`recommend_courses`（个性化推荐），以及未来任何个性化 / 授权工具。`query_handbook` 不涉及 user_id（公开手册），但同样走 ContextVar 注入的 user_id 主要用于 LLM 引用与监控。
- 直连端点如 `/api/v1/recommend/stream` 仍显式接收结构化 `user_id`（绕过 chat 路径）。

## Frontend 路径提醒

- `frontend/AGENTS.md` 是 Next.js 16 自动生成的项目本地 Next.js 提示（`next dev` 自动重写），**与本仓库根 `AGENTS.md` 是两份独立文件**；不要往 frontend/AGENTS.md 加仓库级指引。
- 前端架构、挂载链路、组件层次、SSE 消费链路、错误反馈层、测试基建：**完整版** 在 `docs/v2.0.0/frontend-architecture.md`（路 7 沉淀）。
- 前端 conventions（路 1~7 累计）：
  - 错误反馈统一走 `useNotify().toast.*` / `useNotify().inline.*`（不再写 `message.error` / `inline <Text type="danger">`）
  - SSE 消费优先 `*WithRetry` 版本（路 2：指数退避 + Last-Event-ID）
  - 装饰图标必须 `aria-hidden="true"`；语义 landmark 用 `role="group"` + 完整 `aria-label`
  - 跑命令时 `npm test` 不要省略，单测改动必跑三件套（lint + test + build）

## 关键故障排查速查

| 症状 | 排查 |
|---|---|
| `npm run lint`：`'X' is defined but never used` | 检查刚 import 但已删的组件；Prettier 不会删 import |
| `npm test`：`ResizeObserver is not defined` / `getComputedStyle ... not implemented` | `tests/setup.ts` polyfill 还在不在（重写时不要动 setup） |
| `npm run dev` 启动后 host:3001 502 | docker desktop 转发 bug；改用 `127.0.0.1:8000` 或 `docker compose --profile frontend up -d` |
| `npm run dev` 白屏 + 错乱组件（`npm run build` 却成功） | antd 6 + React 19 + Turbopack 三方兼容：① 装 `@ant-design/v5-patch-for-react-19` 并在 `app/layout.tsx` 首行 import；② `next.config.ts` 加 `transpilePackages: ['antd', '@ant-design/icons', '@ant-design/cssinjs', ...]`；③ login 页 `<App><ConfigProvider>` 顺序错（应为 `<ConfigProvider><App>`）；④ `globals.css` 在 `@import "tailwindcss";` 后补 `@layer base` 救回 button/input 默认值。详见 `docs/v2.0.0/notes/2026-08-24-frontend-dev-white-screen-fix.md` |
| Header 错乱（菜单挤出徽章 / 徽章文字"在线"单字竖排成 64px 高） | antd 6 Layout Header 把 `line-height: var(--ant-layout-header-height)` 继承给所有子元素（实测 64px）。修法：① Menu 加 `minWidth: 0` 让 overflow indicator 工作；② 徽章加 `flexShrink: 0` + `whiteSpace: 'nowrap'`；③ 徽章内 statusText span 加 `style={{ lineHeight: 1.5 }}` 覆盖 antd 注入。详见 `docs/v2.0.0/notes/2026-08-24-frontend-dev-white-screen-fix.md` 阶段二 |
| SSE 流卡住 / 130s+ 无 done | 上游 LLM 配额耗尽（路 4 live eval 真实遇到）；不是代码 bug |
| 流式 token 不显示 | StreamView 的 rAF flush + ref→state 同步断链；检查 `flushSegments` 是否在 done 时调用 |
| 后端 `agent = None` / `main_agent not initialized` | lifespan 跳过；检查 `agent.runtime.init()` 异常日志 |
| `api/recommend/stream` 返回 500 | `Last-Event-ID` 续传：`EventBuffer.replay_from` 找不到事件 → 检查 `sse_event_buffer` Redis 连接 |
| 评估 `chat_intent` live 1/5 通过 | LLM 路由 prompt 漂移；检查 `python/agent/main/prompt.py` 教师端意图路由表 + `MAIN_AGENT_SPEC.allowed_tools` 包含 `dispatch_module` |
| python pytest `event loop closed` | 测试用 `asyncio.run` 嵌套；改用 `pytest-asyncio` `asyncio_mode=auto`（pytest.ini 已启用） |
| `npm run build` 失败：Types error | 新组件缺 `'use client'` / 类型 export 漏掉；先跑 `npx tsc --noEmit` 单独检查 |
| 端口 8000 已被占用 | `netstat -ano | findstr :8000` → 杀进程；或改 `python-api` ports 映射 |
