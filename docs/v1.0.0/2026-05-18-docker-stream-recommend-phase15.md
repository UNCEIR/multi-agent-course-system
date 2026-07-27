# Docker 启动与流式推荐验证（含 Phase 1.5 硬约束）

## 背景与问题

- **目标**：用 `--profile python` 启动 `python-api` 及 MySQL、Redis、Milvus 等依赖；验证 `/health`、同步与流式推荐；确认 Phase 1.5（`HardConstraintFilter`）日志与 SSE 行为。
- **现象**：
  1. 任务说明中的 `POST /api/v1/stream_recommend` 返回 **404**，而代码仅注册 `POST /api/v1/recommend/stream`。
  2. 流式链路在 Phase 3 报错：`RecommendationReasonAgent.astream_reasons() got an unexpected keyword argument 'student_profile'`。
  3. 修复参数后，若不调整超时逻辑，**整段编排**已超过默认 `stream_timeout_seconds`（60s）时，Phase 3 可能被误判为 `STREAM_TIMEOUT`。

## 总体架构方案

- **路由**：流式实现仍为 `SupervisorOrchestrator.stream_recommend()` + `StreamingResponse` + `_sse_wrapper`；为对外文档/脚本兼容，增加与 `recommend/stream` 等价的 **`/api/v1/stream_recommend`** 别名。
- **编排**：Phase 1 →（可选）精召回 → **Phase 1.5 硬约束过滤** → Phase 2 重排+可行性 → Phase 3 流式理由；日志关键字 `course_supervisor.phase15_complete`、`hard_constraint_filter.done`。
- **流式超时语义**：`stream_timeout_seconds` 仅约束 **Phase 3 token 流**耗时，避免前几阶段（画像、重排等）占用全部预算。

## 细节实现

| 文件 | 变更 |
|------|------|
| `python/main.py` | 提取 `_recommend_stream_response()`；`recommend/stream` 与 `stream_recommend` 两个路径共用；模块注释补充别名说明。 |
| `python/orchestrator/supervisor.py` | `astream_reasons(..., profile=student_profile, ...)`；Phase 3 前 `phase3_stream_start = time.perf_counter()`，循环内与 `stream_timeout_seconds` 比较使用 `phase3_stream` 起始时间。 |

## Debug 结论

| 问题 | 根因 | 处理 |
|------|------|------|
| 404 on `stream_recommend` | 仅存在 `/api/v1/recommend/stream` | 增加别名路由 |
| Phase3 `TypeError` | `astream_reasons` 签名参数名为 `profile`，非 `student_profile` | 调用处改为关键字 `profile=` |
| 潜在的 `STREAM_TIMEOUT` | 超时从 `stream_recommend` 入口计时，总延迟常 >60s | 超时改为从 Phase3 流开始计时 |

## 测试与验证

- **已执行**：
  - `docker compose -f docker-compose.python.yml --profile python up -d --build`
  - `docker compose ... ps`：MySQL `3307->3306`，`mysql` / `redis` healthy，`python-api` 监听 8000
  - `curl.exe http://localhost:8000/health` → `status` healthy，`deps.mysql/redis/milvus` 均为 true
  - `curl.exe POST /api/v1/recommend`（payload：`python/scripts/curl_recommend_payload.json`）→ 200，多 Agent 成功
  - `curl.exe -N POST /api/v1/stream_recommend`（同上 payload）→ 200，SSE 序列含：`start` → `phase1_complete` → **`phase15_complete`** → `phase2_complete` → `phase3_start` → `text` / `course_start` / `course_end` → **`phase3_complete`** → **`done`**
  - `docker compose ... logs python-api`：可见 `hard_constraint_filter.done`、`course_supervisor.phase15_complete`
  - `python -m pytest python/tests/test_stream_recommend.py -v` → **5 passed**
- **未执行**：全量 `tests/`（与本轮无关）；未改库、未清数据。

## 经验与后续

- **PowerShell**：`curl` 默认指向 `Invoke-WebRequest`，探测 API 宜用 **`curl.exe`**；`@文件` 作为 body 时，在 `python/scripts` 下用相对路径可减少转义问题。
- **文档对齐**：前端当前使用 `/recommend/stream`（`frontend/src/services/api.ts`）；对外说明可同时列出 **`/stream_recommend` 别名**，避免集成方 404。
- **环境**：`python/.env` 已含 `ECOM_HTTPX_VERIFY_SSL=false`；MySQL 宿主端口保持 **3307** 时，容器内仍为 3306，应用连接配置勿改回宿主 3306。
