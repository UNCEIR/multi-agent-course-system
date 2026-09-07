# 🎓 大学校园多智能体平台（University Campus Multi-Agent Platform）

面向大学生校园场景的一体化多智能体门户：公选课推荐、知识库问答（学生手册 / 个人成绩单）、成绩报告、评价寄语、图片生成、网页搜索、编程、脑图等能力，聚合在同一个可对话的智能体平台中。前端为 Next.js 门户（注册登录 → 智能体入口 Hub），后端为 FastAPI + deepagents 多智能体编排，会话与记忆按用户持久保存。

## ✨ 功能特性

- 🧑‍🎓 **智能选课推荐**：双模式推荐管线（pipeline / react），硬约束确定性过滤在前、LLM rerank 在后
- 📚 **知识库问答**：学生手册公开检索 + 个人成绩单按 `user_id` 强隔离；答案强制引用来源与页码，检索为空不编造
- 📊 **报告与寄语**：成绩报告批量生成（HTML + token 下载）、评价寄语直接管线（雷达图可视化）
- 🖼️ **多模态工具域**：图片生成（base64 直存 MinIO）、网页搜索、编程、脑图等 10 个功能域原子工具 + SKILL.md 渐进式技能
- ⚡ **SSE 流式体验**：事件单调 id + `Last-Event-ID` 断点续传 + 前端指数退避重连；`done` 显式终止、失败走结构化 `error`
- 🧠 **记忆与会话**：agent checkpoint（SqliteSaver）跨会话恢复 + 长期记忆，按用户隔离持久化
- 🧪 **可观测与实验**：A/B 实验中心、指标采集、离线 eval 评测集、系统监控页

## 🧠 架构总览

```text
┌───────────────────────────────────────────────────────────────┐
│  Frontend · Next.js 16 App Router（注册登录 → 智能体入口 Hub）    │
└────────────────────────────┬──────────────────────────────────┘
                             │ SSE / REST（容器内直连 python-api:8000）
┌────────────────────────────▼──────────────────────────────────┐
│  FastAPI 网关 · auth(HMAC) · 会话/记忆 · SSE 事件缓冲            │
│   ├─ main          主智能体（deepagents 编排）                   │
│   ├─ recommend / report / evaluation / ppt                     │
│   └─ documents     文档摄入（解析→脱敏→分块→embed→upsert）        │
└────────────────────────────┬──────────────────────────────────┘
                             │ ToolRegistry 白名单调度
┌────────────────────────────▼──────────────────────────────────┐
│  编排层 agent/  →  工具层 tools/（@tool）  →  技能层 skills/      │
└────────────────────────────┬──────────────────────────────────┘
                             ▼
  MySQL(事实/会话/记忆) · Milvus(向量, user_id 分区) · Redis(召回缓存)
  · MinIO(文档/报告产物) · SQLite(agent checkpoint)
```

**关键设计**

- **三层分离**：`agent/`（编排）→ `tools/`（原子工具 + ToolRegistry）→ `skills/`（SKILL.md 渐进式加载），能力按工具白名单注入主智能体
- **按用户隔离**：ContextVar 注入 `user_id` + 存储分区 + checkpoint 独立，个人成绩单仅本人可检索，LLM 永不猜测身份
- **RAG 可溯源**：回答必须引用来源文档与页码，检索为空如实说明，杜绝编造

**技术栈**：FastAPI · deepagents（LangGraph）· SQLAlchemy ｜ Next.js 16 · React 19 · antd 6 · zustand · echarts ｜ MySQL · Milvus · Redis · MinIO · SQLite ｜ Docker Compose

## 🚀 快速开始

### 1. 环境变量

Docker 只注入 `python/.env`（仓库根 `.env` 可选，先加载后被覆盖）。复制根模板并填写：

```bash
cp .env.example python/.env   # Windows: copy .env.example python\.env
```

必填：`LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`；`EMBEDDING_PROVIDER ∈ local | openai | dashscope_multimodal`。

### 2. 一键启动（推荐 Docker）

```bash
docker compose -f docker-compose.yml -f docker-compose.pull-mirror.yml --profile frontend up -d --build
```

启动后访问：前端 <http://localhost:3001> ｜ 后端健康检查 <http://127.0.0.1:8000/health>

> **国内网络**：内置 `docker-compose.pull-mirror.yml` 将镜像切到 DaoCloud 源（etcd 保持官方）；可直连 Docker Hub 时去掉该文件即可。
> **前端务必走容器**：容器内用 `python-api:8000` 直连后端，绕开 Docker Desktop host→container 转发截断 SSE body 的 bug；host 上勿同时跑 `npm run dev`（3001 端口冲突）。

### 3. 日常开发与维护

```bash
# 改了 python/ 代码 → 重建后端
docker compose -f docker-compose.yml -f docker-compose.pull-mirror.yml up -d --build python-api

# 改了 frontend/package.json → 需 --no-cache 重建前端（只改 src/ 不必）
docker compose -f docker-compose.yml -f docker-compose.pull-mirror.yml --profile frontend up -d --build --no-cache frontend

docker compose -f docker-compose.yml -f docker-compose.pull-mirror.yml --profile frontend logs -f --tail 100 <service>  # 日志
docker compose -f docker-compose.yml -f docker-compose.pull-mirror.yml --profile frontend stop                        # 停止全部（容器保留）
docker compose -f docker-compose.yml -f docker-compose.pull-mirror.yml --profile frontend down                        # 停止并移除容器（卷保留）
```

`<service>` = `python-api` | `frontend` | `mysql` | `redis` | `milvus` | `minio` | `etcd`

### 4. 数据导入（首次使用）

```bash
cd python
python scripts/ingest_course_dataset.py --limit 20   # 冒烟 20 门；全量去掉 --limit（约 500 门）
python scripts/ingest_student_handbook.py            # 学生手册 → public 分区
python scripts/ingest_transcript_desensitized.py --user-id <id> --name <姓名>   # 个人成绩单（仅本人可检索）
cd ..
```

> ⚠️ 课程库为空时推荐会退化（返回两门示例课）；导入后 `course_records` / `course_chunks` 应有数据。

### 5. 测试与评测

```bash
cd python   && python -m pytest tests/ -m "not slow" -v   # 后端单测（mock LLM，不触真实配额）
cd python   && python eval/runner.py --set chat_intent     # 离线 eval（--live / --judge 需真实 LLM）
cd frontend && npm test                                    # 前端 vitest（改动必跑 lint + test + build）
```

## 🔌 主要 API

| 端点 | 说明 |
| --- | --- |
| `POST /api/v1/auth/register` · `/auth/login` | 注册 / 登录（HMAC token） |
| `POST /api/v1/chat/stream` | 主智能体 SSE 会话（`text/tool/done/error`，多轮 + 记忆） |
| `GET /api/v1/chat/sessions` · `/sessions/{id}/messages` | 会话列表 / 历史回显 / 重命名 / 软删 |
| `POST /api/v1/recommend/stream` | 选课推荐 SSE（pipeline 默认 / react） |
| `POST /api/v1/report` · `GET /api/v1/report/download` | 成绩报告批量生成（SSE）+ token 下载 |
| `POST /api/v1/evaluation` · `GET /api/v1/evaluation/me` | 评价寄语生成 / 学生端查看 |
| `POST /api/v1/documents/upload` | 知识库文档摄入 |
| `GET /health` · `/api/v1/metrics` · `/api/v1/experiments` | 健康检查 / 指标 / A-B 实验 |

## 📁 项目结构

```text
├── python/                  # FastAPI 后端（agent.app:app）
│   ├── agent/               # 编排：app / runtime / main / recommend / report / evaluation / documents / memory / ppt
│   ├── api/                 # 路由层（auth / chat / recommend / report / evaluation / documents / health）
│   ├── tools/               # 10 个功能域 @tool + ToolRegistry / CircuitBreaker / MCPClient
│   ├── skills/              # SKILL.md 技能库（渐进式加载）
│   ├── services/            # SSE 事件缓冲等服务
│   ├── ai/ · auth/ · config/ · models/ · storage/ · observability/ · experiment/
│   ├── scripts/             # 数据导入 / 冒烟脚本
│   ├── eval/ · eval_sets/   # 离线评测 runner 与评测集
│   ├── memories/            # 运行时长期记忆（勿与仓库指令文件混淆）
│   └── tests/               # pytest（单元 + API 流式断言）
├── frontend/                # Next.js 16（App Router，React 19 + antd + zustand + echarts）
│   ├── src/app/             # (main) hub / chat / recommend / report / evaluation / documents / experiments / monitor + login
│   ├── src/lib/ · components/ · stores/ · types/
│   └── tests/               # vitest（含 SSE 流式断言）
├── sql/init-db.sql          # 唯一建表来源
├── docs/                    # 架构文档 / 决策记录 / 复盘笔记
├── docker-compose.yml       # python-api + mysql + redis + milvus + minio + etcd + frontend(profile)
└── AGENTS.md · CLAUDE.md    # 仓库开发指令与架构决策参考
```

## 📚 文档与参考

- [AGENTS.md](AGENTS.md) — 仓库开发指令（命令 / 约束 / 契约，含高频故障速查）
- [CLAUDE.md](CLAUDE.md) — 详细架构与历史决策
- [docs/v2.0.0/frontend-architecture.md](docs/v2.0.0/frontend-architecture.md) — 前端架构详解（Next.js 16 挂载链路 + SSE 消费链路）
- `docs/v2.0.0/` — 设计计划、决策记录（notes/）、详细设计（plans/）

> 本项目暂无开源 LICENSE（课程/学习用途），对外使用前请先与作者确认。