# Repository Instructions

每次回答必须带问候"主人"二字。调用 shell 优先级的顺序：window下linux子系统的wsl > powershell > cmd（Windows）> git bash。

详细架构与历史决策见 `CLAUDE.md`；前端（Next.js 16 App Router）完整版见 `docs/v2.0.0/frontend-architecture.md`。

## Layout

- 工作区：`python/`（FastAPI 后端）+ `frontend/`（Next.js 16）+ `docs/`；Python 命令一律从 `python/` 目录跑（pytest.ini 已配 package layout）。
- 后端入口 `python/agent/app.py`（`agent.app:app`）；lifespan 初始化 `agent.runtime`（repos / ToolRegistry / main deep agent）。前端入口 `frontend/src/app/`。
- 三层分离：`agent/`（编排）→ `tools/`（原子 @tool + ToolRegistry）→ `skills/`（SKILL.md，SkillsMiddleware 渐进式加载）。子 agent 场景：recommend / report / evaluation / ppt。
- 主 agent checkpoint 落 SQLite；长期记忆读 `python/memories/AGENTS.md`（运行时文件，**勿与仓库根本文件混淆**，代码级禁写回）。

## Setup & Commands

```bash
cd python && python -m pytest tests/test_file.py -v      # 单文件
cd python && python -m pytest tests/ -m "not slow" -v    # 默认本地 suite（mock LLM，禁真实 LLM）
cd python && python -m pytest tests/ --cov               # 覆盖率
```
markers 只用 `unit / integration / slow / agent / api`（已启用 auto asyncio），不发明新 marker。

- 数据导入（cwd=python/）：`scripts/ingest_course_dataset.py [--limit 20]` / `ingest_student_handbook.py` / `ingest_transcript_desensitized.py --user-id <id> --name <姓名>`；CSV 源 `course_dataset_tools/output/course.csv`。
- 离线 eval：`cd python && python eval/runner.py --set <name>`；`--live`/`--judge` 真调真实 LLM（默认不跑省额度）；集在 `eval_sets/*.jsonl`，报告落 `eval/reports/`。

前端（Node ≥ 20.9；改 package.json 后容器必须 `--no-cache` 重 build）：
```bash
# 推荐容器跑（绕开 host→container 转发丢 SSE body/502 bug）
docker compose -f docker-compose.yml -f docker-compose.pull-mirror.yml --profile frontend up -d --build frontend
# 仅调试/快速验证：cd frontend && npm ci && npm run dev（host 有 SSE 截断已知 bug）
# 前端验证三件套：npm test + npm run lint + npm run build（单测改动必跑全）
```

## Env & Services

- `.env`：根 `.env` 先、`python/.env` 后覆盖；Docker 仅注入 `python/.env`。启动门槛必须 `LLM_API_KEY/LLM_BASE_URL/LLM_MODEL`；`EMBEDDING_PROVIDER ∈ local|openai|dashscope_multimodal`。
- `docker compose up -d`（mysql/redis/minio/etcd/milvus/python-api）；Python 代码变更 `docker compose up -d --build python-api`（镜像源不可达时显式 `--build-arg PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.12-slim`）。
- host→container:8000 偶发 502/SSE 空 body：用 `127.0.0.1:8000`，或前端容器内走 `python-api:8000`；证书问题设 `HTTPX_VERIFY_SSL=false` 重建。

## Implementation Constraints

- `ChatOpenAI` 一律走 `ai.llm_client.build_chat_openai`（保留 `LLMTaskName` run name），不直接 new。
- `config.get_settings()` 是 lru_cache：测试 patch 它并给完整 mock，别在 import 后改 env。
- 工具在 `agent/runtime.py` 的 `build_main_agent()` 前 `ToolRegistry.register_many` 注册；编排工具白名单在 `MAIN_AGENT_SPEC.allowed_tools`。
- Redis 只缓存**候选课程 ID**；硬约束（确定性过滤）在 rerank 之前，不是软偏好。

### Image Generation Delivery（2026-09-05 修复后契约）

- 链路：`image_generate`（提交 task_id）→ `image_generate_get`（done 后**优先 base64 直存** MinIO/本地；base64 空才回退 24h URL 下载）。实现 `python/tools/image/image_generate.py` + `jimeng_mcp_server.py`。
- 图片内部链接一律走 **`GET /api/v1/images/download?file_key=images/<uuid>.<ext>`**（`api/images.py`：仅 images/ 前缀、image/* + inline、无 token/无过期）。
- **禁止**图片转存返回 `/api/v1/report/download`（report 产物专用：HMAC + pdf/html + attachment）；report/download 对 images/ 的放行仅 legacy（旧历史链接），新代码不得复用。
- MCP 返回可能有 `{"output":[{text: json}]}` 包装：统一走 `_call_mcp`/`_extract_text` 解析兜底；MCP_SERVERS 里 jimeng = stdio `python -m tools.image.jimeng_mcp_server`，凭据 `VOLC_ACCESS_KEY/SECRET_KEY`。修复记录 `docs/v2.0.0/notes/2026-09-05-image-delivery-render-fix.md`。

## Frontend 契约 & 渲染

- 前端面向 API 默认 **SSE 流式**：有意义的 progress/results、**`done` 显式终止**、失败走结构化 `error`、不能静默断流；前端测试必须消费流断言（事件序/payload/done/error）。
- SSE 路 2：事件带单调 `id`、客户端 `Last-Event-ID` 续传、前端 `consumeSSEWithRetry` 指数退避（见 `frontend/src/lib/sse.ts` + `python/services/sse_event_buffer.py`）。
- `app/api/` 是预留 BFF 层，**当前故意空**，别写真实 proxy。
- 错误反馈统一 `useNotify().toast.*/inline.*`；SSE 消费优先 `*WithRetry`；装饰图标 `aria-hidden="true"`，landmark 用 `role="group"`+完整 `aria-label`。
- chat 渲染：assistant 走 `MarkdownContent`（react-markdown，`frontend/src/components/MarkdownContent.tsx`，图片→`<img>`、raw HTML 默认不渲染防 XSS）；user 保持 pre-wrap 纯文本；历史回显同走 MarkdownContent。
- 单测改动必跑三件套（lint + test + build）。`frontend/AGENTS.md` 是 Next 自动生成，勿加仓库级指引。

## RAG & 用户身份

- Milvus `document_chunks` 按 `user_id` 分区；公开手册 `user_id=public`，个人成绩单仅本人可检索。
- 摄入：解析→NFKC→脱敏（姓名/学号/班级/日期，课程与成绩保留）→递归分块→embed→upsert + MySQL 元数据；整 dataset 幂等替换（delete_by_dataset + replace_chunks）。上传 `POST /api/v1/documents/upload`（`python/agent/documents/service.py`）。
- 检索已拆：`query_handbook`（公开，top_k=5）/ `query_transcript`（本人分区强隔离，top_k=3）；答案**必须引用 source_doc_name/page_number**，检索为空不编造。
- 个性化/授权工具必须 `from agent.main.context import get_current_user_id`（ContextVar 注入），**绝不**让 LLM 猜 user_id、绝不进 args_schema；直连端点如 `/api/v1/recommend/stream` 显式收结构化 user_id。

## 高频故障速查

| 症状 | 排查 |
|---|---|
| SSE 流 200 但长时间无 body / 前端 network error | uvicorn 访问日志在响应完成后才打，挂起请求不留痕；`docker compose logs python-api 2>&1 | grep -v "GET /health HTTP"`；卡在 start 后即上游 gather/LLM 未完成；`asyncio.CancelledError` 继承 BaseException，`except Exception` 捕不到 |
| SSE 流 130s+ 无 done | 上游 LLM 配额耗尽（真实遇过），不是代码 bug |
| chat 图片不显示 / 链接打不开 | URL 必须 `/api/v1/images/download?file_key=images/...`；旧 `/api/v1/report/download?...token=__IMG__` 仅 legacy；403=key 非 images/ 前缀，404=对象不在 MinIO/本地兜底（查卷 `python_documents_data:/app/.documents`） |
| MCP 工具返回缺字段/解析异常 | adapters 包装形态差异（`{"output":[{text}]}`），统一走 `_call_mcp`/`_extract_text` 兜底 |
| `npm run dev` host:3001 502 / SSE 截断 | docker desktop 转发 bug；`127.0.0.1:8000` 或 frontend 容器内 `python-api:8000` |
| `npm run dev` 白屏（build 却成功） | antd6+React19+Turbopack：装 `@ant-design/v5-patch-for-react-19` 首行 import、`transpilePackages`、`<ConfigProvider><App>` 顺序、`globals.css` 补 `@layer base`；见 `docs/v2.0.0/notes/2026-08-24-frontend-dev-white-screen-fix.md` |
| Header 错乱（徽章竖排 64px） | antd Header 继承 line-height；Menu `minWidth:0`、徽章 `flexShrink:0`+nowrap、文字 `lineHeight:1.5`；见同上 note 阶段二 |
| 后端 `agent=None` / not initialized | lifespan 跳过，查 `agent.runtime.init()` 异常日志 |
| `api/recommend/stream` 500 | `Last-Event-ID` 续传 replay 找不到事件 → 查 sse_event_buffer Redis |
| `npm test` ResizeObserver/getComputedStyle 缺失 | `tests/setup.ts` polyfill 被删，别动 setup |
| python pytest `event loop closed` | 别用 `asyncio.run` 嵌套；pytest-asyncio `asyncio_mode=auto` 已启用 |
| 端口 8000 被占 | `netstat -ano | findstr :8000` 杀进程或改映射 |
