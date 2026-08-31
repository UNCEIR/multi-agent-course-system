# 大学校园多智能体平台（University Campus Multi-Agent Platform）

面向大学生校园场景的多智能体系统：公选课推荐、知识库问答（学生手册 / 个人成绩单）、成绩报告、评价寄语、图片生成、网页搜索、编程、脑图等。前端为 Next.js 门户（注册登录 → 智能体入口页聚合），后端为 FastAPI + deepagents 多智能体编排，会话与记忆按用户持久保存。



### 1. 环境准备（仅首次）

```bash
python -m venv .venv
python -m pip install -r python/requirements.txt
```

配置 `python/.env`（Docker 只注入这一个；仓库根 `.env` 可选，先加载、后被 `python/.env` 覆盖）：

```bash
LLM_API_KEY=...
LLM_BASE_URL=...
LLM_MODEL=qwen3.8-flash
EMBEDDING_PROVIDER=local|openai|dashscope_multimodal
```

### 2. 一键启动全部（后端 + 依赖 + 前端）

> **镜像源（默认 DaoCloud）**：`registry-1.docker.io` 通常被墙导致构建/拉取超时，仓库已内置
> `docker-compose.pull-mirror.yml` 覆盖文件，把 python-api 基础镜像、mysql / redis / minio /
> milvus / frontend node 镜像全部切到 DaoCloud（`docker.m.daocloud.io`）；etcd 保持 quay.io
> 官方（DaoCloud 对 quay/etcd 常返回 403，quay.io 一般可直连）。所有 `up -d` / `--build` 命令
> 统一带 `-f docker-compose.yml -f docker-compose.pull-mirror.yml`。若你的网络可直连 Docker Hub，
> 去掉该覆盖文件即可回退官方源。

```bash
docker compose -f docker-compose.yml -f docker-compose.pull-mirror.yml up -d
docker compose -f docker-compose.yml -f docker-compose.pull-mirror.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.pull-mirror.yml --profile frontend up -d --build frontend
```

启动完成：前端 <http://localhost:3001> ｜ 后端 <http://127.0.0.1:8000/health>

> **前端必须走容器**。容器内用 `http://python-api:8000` 直连后端，绕开 docker desktop
> host → container 转发层截断 SSE body 的 bug（表现为前端 network error、响应体为空）。
> ⚠️ host 上不要同时跑 `npm run dev`，会与容器 3001 端口冲突。

### 3. 单独重启某一个容器

```bash
docker compose -f docker-compose.yml -f docker-compose.pull-mirror.yml up -d --build <service>  # 重建 + 重启（改了代码用它）
docker compose restart <service>              # 只重启、不重建（容器假死 / 改了 compose 配置）
docker compose stop <service>                 # 只停止
docker compose logs -f --tail 100 <service>   # 跟踪日志
```

`<service>` 取值：`python-api`｜`frontend`｜`mysql`｜`redis`｜`milvus`｜`minio`｜`etcd`

最常用的一条——**改了 `python/` 下任何代码后**：

```bash
docker compose -f docker-compose.yml -f docker-compose.pull-mirror.yml up -d --build python-api
```

> 改 `frontend/package.json`（engines / scripts / devDependencies）后要加 `--no-cache`；
> 只改 `src/` 不必（docker 按 package.json 内容复用缓存层）。

### 4. 数据导入（首次部署 / 需重置课程库）

```bash
cd python
python scripts/ingest_course_dataset.py --limit 20   # 冒烟 20 门
python scripts/ingest_course_dataset.py              # 全量 ~500 门
python scripts/ingest_student_handbook.py            # 学生手册 → public 分区
python scripts/ingest_transcript_desensitized.py --user-id <id> --name <姓名>
cd ..
```

> ⚠️ 课程库为空时推荐会退化：召回走 `_fallback_courses()` 返回两门硬编码示例课。
> 验证数据量：`course_records` / `course_chunks` 两张表应有行。

### 5. 停止与清理

```bash
docker compose up --profile frontend stop   # 只停前端
docker compose up stop                      # 停全部（容器保留，可再 start）
docker compose up down                      # 停并移除容器（数据卷保留）
```

### 6. 测试

```bash
cd python   && python -m pytest tests/ -m "not slow" -v   # 后端单测（mock，不触真实 LLM）
cd python   && python eval/runner.py --set chat_intent    # eval smoke（--live 需 API + 算力）
cd frontend && npm test                                    # 前端 vitest
```

## 基本排查

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"   # 容器是否在跑（Unhealthy = 有 bug）
curl -sS http://127.0.0.1:8000/health | head -c 200  # 后端 health（model 字段确认 LLM 配对）
docker compose logs --tail 100 python-api                        # 后端最近日志
netstat -ano | findstr :8000                          # 端口 8000 是否被占（PID 在最后一列）
```

### SSE 流挂起 / 响应体为空（前端报 network error）

特征：接口返回 **200**、没有 5xx，但响应体长时间为空，前端等到超时后报 network error。

第一步看日志，**务必滤掉前端 15s 一次的 health 轮询噪声**，否则业务日志会被完全淹没：

```bash
docker compose logs python-api 2>&1 | grep -v "GET /health HTTP" | tail -80
```

第二步给 SSE 事件打相对时间戳，定位具体是哪一段没有输出：

```bash
start=$(date +%s)
curl -sS -N --max-time 75 -X POST http://127.0.0.1:8000/api/v1/recommend/stream \
  -H "Content-Type: application/json" \
  -d '{"user_id":"debug","prompt":"想选好过的公选课，南校区，最好不要考试","num_items":5,"mode":"pipeline"}' \
  | grep --line-buffered -E '"phase"|event: done' \
  | while IFS= read -r line; do
      now=$(date +%s); printf 'T+%03ds | %s\n' $((now-start)) "${line:0:130}"
    done
```

排查要点：

- **uvicorn 访问日志在响应完成后才打印**，挂起的 SSE 请求不会留痕，不能据此判断"接口没问题"。
- 推荐链路正常应依次输出 `start → phase1_complete → phase15_complete → phase2_complete → phase3_start → … → done`。
  若卡在 `start` 之后、`phase1_complete` 始终不出现，就是 phase1 的 `gather(画像, 召回)` 没完成。
- 画像 agent 的关键日志是 `student_profile.llm_call.start / .done / .cancelled / .failed`，
  其中 `.done` 的 `latency_ms` 直接给出 LLM 真实耗时（thinking 开启时常达 20~30s）。
- 出现 `agent.cancelled` 表示该 agent 被上游取消（客户端断开 / `wait_for` 超时）。
  注意 `asyncio.CancelledError` 在 Python 3.8+ 继承 `BaseException`，`except Exception` 捕获不到——
  这正是"无任何报错却卡住"的常见成因，现已补日志。

### localhost:3001 报 502 / network error / body 空

docker desktop host → container:8000 转发层 bug（同步请求可能 502，SSE 长连接可能 body 被截断）。
**走前端容器化可彻底绕开**：`frontend-1` 与 `python-api-1` 在同一 docker 网络内，
用 service 名 `http://python-api:8000` 直达后端，不经过 host 转发层。

```bash
# 先关掉 host 上的 npm run dev
Get-Process node | Where-Object { $_.CommandLine -match "next dev" } | Stop-Process -Force
# 再启前端容器
docker compose up --profile frontend up -d --build frontend
```

## 主要 API

| 端点 | 说明 |
|------|------|
| `POST /api/v1/auth/register`、`/auth/login` | 注册 / 登录（HMAC token，业务接口维持 user_id 临时口径） |
| `POST /api/v1/chat/stream` | 主智能体 SSE 会话（text/tool/done/error），多轮 + 记忆 + 跨会话恢复 |
| `GET /api/v1/chat/sessions`、`/sessions/{id}/messages`、`/rename`、`DELETE` | 会话列表 / 历史回显 / 重命名 / 软删 |
| `POST /api/v1/recommend/stream` | 推荐（mode=pipeline 默认 / react，SSE） |
| `POST /api/v1/report`、`GET /api/v1/report/download` | 成绩单批量生成（SSE）+ token 下载 |
| `POST /api/v1/evaluation`、`GET /api/v1/evaluation/me` | 评价寄语生成（SSE）/ 学生端本人查看 |
| `POST /api/v1/documents/upload` | 文档摄入（file + dataset_name + chunk_strategy） |
| `GET /health`、`/api/v1/metrics`、`/api/v1/experiments` | 健康 / 指标 / A-B 实验 |

## 架构速览

- 三层分离：`agent/`（编排）→ `tools/`（@tool 原子能力 + ToolRegistry 注册）→ `skills/`（SKILL.md 渐进式技能）
- 主智能体：deepagents（checkpoint SqliteSaver + 记忆表 + compaction 五字段摘要）
- 存储：MySQL（事实/会话/记忆/评价）、Milvus（向量，user_id 分区）、Redis（召回缓存）、MinIO（文档/报告产物）
- 智能体隔离：checkpoint 独立 + 工具白名单 + ContextVar user_id 注入 + 存储分区

## 目录结构

```
mult-agent-university-system/
├── python/                        # FastAPI 后端（agent.app:app）
│   ├── agent/
│   │   ├── app.py                 # 入口（lifespan 初始化 runtime）
│   │   ├── runtime.py             # 单例容器（supervisor/仓储/ToolRegistry/main_agent）
│   │   ├── main/                  # v2 deepagents 主智能体（factory/specs/subagents/context/checkpointer/prompts）
│   │   ├── recommend/             # v1 推荐管线（supervisor 双模式 + 5 个 agent + 硬约束过滤）
│   │   ├── report/                # 成绩报告编排（四决策点 + stream_report）
│   │   ├── evaluation/            # 评价寄语编排（五层反幻觉直接管线）
│   │   ├── documents/             # 文档摄入服务
│   │   ├── memory/                # 记忆（注入/持久化/提取 worker/consolidation/prompts）
│   │   └── ppt/                   # PPT 骨架（后续 phase）
│   ├── api/                       # 路由层（auth/chat/recommend/report/evaluation/documents/health）
│   ├── ai/                        # LLM/Embedding 工厂 + LLMTaskName + LangSmith tracing
│   ├── auth/                      # HMAC token 签发/校验（轻量认证）
│   ├── tools/                     # 10 个功能域 @tool 原子能力 + ToolRegistry/CircuitBreaker/MCPClient
│   │   └── (system/chat/code/documents/evaluation/image/knowledge/mindmap/recommend/report)
│   ├── skills/                    # 10 个 SKILL.md 技能 + _shared 共享规则
│   ├── storage/                   # MySQL（base/user/chat_session/document/evaluation/report_artifact）+ Milvus + Redis + MinIO
│   ├── config/                    # settings.py（双 .env 加载，lru_cache）
│   ├── models/                    # Pydantic 契约
│   ├── experiment/                # A/B 分桶
│   ├── observability/             # 指标采集
│   ├── eval/                      # 评估 runner + reports/
│   ├── eval_sets/                 # 评估数据集（chat_intent/kb_retrieval/report_math/evaluation_comment/web_search/image_generate + live 集）
│   ├── scripts/                   # 数据导入/采集/冒烟脚本
│   ├── templates/                 # 报告 HTML 模板
│   ├── tests/                     # pytest（单元 + API 流式断言 + fixtures）
│   └── (memories/AGENTS.md        # 主智能体运行时长期记忆文件，勿与仓库指令文件混淆)
├── frontend/                      # Next.js 16（App Router, React+TSX）
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx         # 根布局
│   │   │   ├── (main)/            # 主导航布局 + 8 页面（route group 括号不影响 URL）
│   │   │   │   ├── layout.tsx     # Header 导航 + App context + 15s 健康轮询
│   │   │   │   ├── error.tsx      # (main) 路由级 ErrorBoundary
│   │   │   │   ├── page.tsx       # 智能体入口 Hub（角色感知卡片）
│   │   │   │   ├── chat/          # 智能对话（左侧会话栏 + SSE 流）
│   │   │   │   ├── recommend/     # 推荐选课
│   │   │   │   ├── report/        # 成绩报告
│   │   │   │   ├── evaluation/    # 评价寄语（echarts 雷达）
│   │   │   │   ├── documents/     # 知识库摄入
│   │   │   │   ├── experiments/   # 实验中心（A/B + 架构对比）
│   │   │   │   └── monitor/       # 系统监控
│   │   │   ├── login/             # 登录/注册（独立 layout，不走 MainLayout）
│   │   │   └── api/               # BFF 预留（未来 Java REST，当前为空）
│   │   ├── lib/                   # api.ts 客户端 / sse.ts 消费器 / theme.ts 设计 token / api/{safeCall,useNotify,useApi}.ts
│   │   ├── components/            # StreamView / CourseInlineCard / RadarChart / CourseFields（路 7 抽取的共享字段层）
│   │   │   └── recommend/          # 路 1 拆出的 5 个推荐子组件 + constants
│   │   ├── stores/                # zustand（auth 登录态 / session 会话，localStorage 持久）
│   │   └── types/                 # 主类型（Course / API 响应）+ sse.ts（zod schema）
│   ├── next.config.ts             # rewrites 代理 /api、/health → :8000（API_PROXY_TARGET 可覆盖；容器内默认 http://python-api:8000）
│   ├── Dockerfile                 # 路 5：node:20-slim + ARG NODE_BASE_IMAGE；`--profile frontend up -d --build` 启；改 package.json 后需 `--no-cache` 重建
│   └── package.json               # engines: ^20.9.0 || >=22.0.0；`dev` = `next dev -p 3001`（与 docker 端口映射对齐）
├── sql/init-db.sql                # 唯一建表来源（course/chat_sessions/users/...）
├── course_dataset_tools/          # 课程数据集生成（output/course.csv）
├── docs/
│   ├── v2.0.0/                    # 计划/决策（plan.md, notes/, plans/, rag-ingest.md, eval-system.md）
│   │   └── frontend-architecture.md   # 前端架构详解（Next.js 16 App Router 挂载链路 + SSE 消费链路 + 错误反馈层 + 测试基建）
│   └── notes/v2.0.0/              # 阶段复盘笔记（路 1~路 7 + Phase 3 live eval 兑现）
├── docker-compose.yml             # python-api + mysql(3307) + redis + milvus + minio + etcd + frontend(profiles)
└── AGENTS.md / CLAUDE.md          # 仓库指令与架构决策参考
```

## 前端架构（Next.js 16 App Router）

```
URL: /
  RootLayout (app/layout.tsx)             <html><body> + 字体 + globals.css
    └─ MainLayout (app/(main)/layout.tsx) <App> + ConfigProvider + Header 导航
        └─ HubPage (app/(main)/page.tsx)   角色感知卡片

URL: /chat | /recommend | /report | /evaluation | /documents | /experiments | /monitor
  RootLayout
    └─ MainLayout
        └─ <PageName>Page (app/(main)/<name>/page.tsx)

URL: /login
  RootLayout                                注意：login 不走 MainLayout
    └─ LoginPage (app/login/page.tsx)        独立 ConfigProvider
```

完整挂载链路 + SSE 消费链路 + 错误反馈层 + 测试基建详见 **[docs/v2.0.0/frontend-architecture.md](docs/v2.0.0/frontend-architecture.md)**。

## 文档

- `AGENTS.md` — 仓库指令（开发必读：命令/约束/契约）
- `CLAUDE.md` — 详细架构与历史决策
- `docs/v2.0.0/` — 计划、决策记录（notes/）、详细设计（plans/）
- `docs/v2.0.0/frontend-architecture.md` — **前端架构详解**（Next.js 16 App Router 挂载链路 + SSE 消费链路 + 错误反馈层）
- `docs/notes/v2.0.0/` — 各阶段复盘笔记（路 1~路 7 + Phase 3 live eval 兑现）
