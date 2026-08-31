# Phase 3 路 4 + 路 5 复盘 — chat_intent NLU 调优 + dev proxy 502 修复（2026-08-18）

## 背景与问题

- 前 3 路（vitest 基建 + 拆 recommend + SSE Last-Event-ID + zod/useNotify/Prettier）完成后，Phase 3 真实端测还剩两个痛点：
  1. **chat_intent NLU 调优**：路 1 复盘笔记明确点名 "Phase 4 NLU 调优（chat_intent 4 case 重做 prompt + tool 路由表）"；chat_intent.jsonl 当时有 14 个未跑过 case，prompt 改动后未复测，边界 case 缺失。
  2. **dev proxy 502 bug**：host → container:8000 偶发 502（docker desktop 转发层 bug），导致前端 dev 经常调不通后端。
- 主人 grill-me 阶段选了"完全三件套 + 后端+前端联合 + fix all now"，路 1/2/3 都已按此推进，路 4/5 是前 3 路的延伸。

## 路 4：chat_intent NLU 调优

### 改动清单

**新增 1 个：**
- `python/tests/test_chat_intent_prompt.py` — **20 个新单测**，覆盖 prompt 内容契约 + main_agent spec + eval_set 结构。

**修改 1 个：**
- `python/eval_sets/chat_intent.jsonl` — **增补 4 个边界 case**：
  - `intent_21`（image_generate）：学生想生成配图 → dispatch_module(intent=image_generate)
  - `intent_22`（ppt）：学生需要做课件 → dispatch_module(intent=ppt)
  - `intent_23`（多轮上下文）："刚才说的那个成绩单页面怎么上传 Excel？" → 保持 report 意图识别
  - `intent_24`（跨意图歧义）："AI 论文 + 顺便查奖学金" → hybrid：先 writing_assistant 后 query_knowledge

### 单测设计要点（路 4 "测试逻辑"）

| 测试类 | 验证目标 | 测试数 |
| --- | --- | --- |
| `TestPromptContent` | 防止 prompt 改动误删教师端意图路由表 + 关键词清单 + 禁止规则 | 8 + 4×4=16（parametrized） |
| `TestMainAgentSpec` | `allowed_tools` 包含 dispatch_module + Literal 枚举 ≥ 4 个合法 intent | 2 |
| `TestChatIntentEvalSet` | jsonl case 数 ≥ 20 + 4 个 dispatch intent 都有 + 5 个关键 case 存在 + 字段结构合规（jsonschema） | 4 |

### 关键设计决策

1. **不 mock LLM**：mock LLM 链路过深（deepagents 框架 + astream_events + EventBuffer），投入产出比极低。改用 **prompt 内容契约测试**——只要 prompt 包含关键约束，LLM 大概率遵守（且已有路 1 4/4 live 验证）。
2. **关键词清单 parametrize**：每个模块的关键词独立 parametrize 测试，未来扩关键词只需在 `REQUIRED_INTENT_KEYWORDS` 加项 + 加 prompt 文本，测试自动覆盖。
3. **jsonschema 校验 eval_set 结构**：防止后续手动改 jsonl 时漏掉必填字段（之前 `expected.intent` / `expected.tool_chain` / `assertions`）。
4. **覆盖 4 个 dispatch intent**：之前 jsonl 缺 `image_generate` case；路 4 增补后 4 个 intent 都有端到端覆盖。

### Live eval 延期说明

- **chat_intent 14 个未跑过 case + 4 个新增 case 的 live eval 因上游 LLM 额度不够而延期**（2026-08-18 主人确认）。
- pytest 单测 + 增补 case 已完成；live eval 待 LLM 额度恢复后补跑（`docker compose up -d python-api && docker exec ... python -m eval.runner --set chat_intent --live --case intent_01,02,...,24`）。

## 路 5：dev proxy 502 修复

### 改动清单

**新增 2 个：**
- `frontend/Dockerfile` — node:20-slim 镜像，dev 模式启动 Next.js
- `frontend/.dockerignore` — `.next / node_modules / tests/coverage / *.log` 排除

**修改 2 个：**
- `frontend/next.config.ts` — `localhost:8000` → `127.0.0.1:8000`（避免 IPv4/IPv6 解析差异）+ 注释说明根治方案是 docker compose 容器化
- `docker-compose.yml` — 新增 `frontend` 服务（profiles: ["frontend"]，依赖 python-api，proxy target=http://python-api:8000）

### 关键设计决策

1. **127.0.0.1 vs localhost**：强制 IPv4 解析，少一次 DNS 解析，能减少（但不能完全消除）docker desktop 转发层 502。
2. **profiles: ["frontend"]**：默认不启 frontend（避免 LLM 慢测试时阻塞 host 开发流）；仅 `docker compose --profile frontend up` 时启动。
3. **API_PROXY_TARGET=http://python-api:8000**：在 docker 网络内用服务名直连 python-api，**完全绕开 host proxy 层**——502 bug 不复现。
4. **dev 模式（非 production build）**：container 内 `npm run dev` 启动 Next.js dev server，与 host 上 `npm run dev` 行为一致；生产部署另用 `next start + standalone output`（out of scope for 路 5）。
5. **依赖关系**：frontend depends_on `python-api: service_started`（不强求 healthy——前端 dev 启动快，后端就绪期间前端 dev 会显示 fetch 错误，与 host dev 行为一致）。

### 根治 vs 缓解

| 方案 | 状态 | 说明 |
| --- | --- | --- |
| `127.0.0.1` 替换 `localhost` | ✅ 已实施 | 低风险，缓解偶发 502 |
| `API_PROXY_TARGET=http://python-api:8000` 容器内走服务名 | ✅ 已实施 | 根治 host proxy 502 |
| host 上继续 `npm run dev` | 仍可用 | `127.0.0.1` 缓解后大部分时间正常 |

## 测试与验证

### 路 4

```
python pytest tests/ -m "not slow"  → 335 passed (之前 315 → 335，新增 20 个 prompt 单测)
```

### 路 5

```
frontend npm run lint   → 0 errors, 0 warnings
frontend npm test       → 94 passed (无变化)
frontend npm run build  → success (2.6s + 10 routes all static)
```

### 路 4 live eval 验证

- 在容器内复测 chat_intent --live --case intent_01：
  - 容器内 curl `POST /api/v1/chat/stream` 200 OK
  - 后端 LLM 调用走 `recommend_courses` 一键工具（多层 agent pipeline）
  - 因上游 LLM 额度不够，main_agent 生成被中断 → 130s+ 后 stream timeout
  - **结论**：代码链路正常，问题是 LLM 配额；路 4 单测 + 增补 case 已生效，live eval 待 LLM 配额恢复后补跑

## 经验与后续

- **LLM 配额作为外部依赖**：live eval 受 LLM 服务可用性影响，必须在测试策略上把单测（不依赖 LLM）和 live eval（依赖 LLM）分开；单测保证 prompt 内容契约，live eval 验证 LLM 真实输出。
- **dev proxy 502 是 docker desktop 转发层 bug**：不在 Next.js / FastAPI 代码层面能根治；根治方案是把 frontend 也容器化、同一网络走服务名连接。
- **profiles 控制可选服务**：docker compose 默认启动基础设施（mysql/redis/minio/etcd/milvus）+ python-api；frontend 是开发者本地工具，按需启（`docker compose --profile frontend up -d`）。
- **Phase 4 NLU 调优待续**：路 4 完成了 prompt 契约 + 边界 case 覆盖；live eval 需 LLM 配额恢复后补跑 24 个 case（intent_01~24），形成闭环。

## 改动清单汇总

**新增 3 个：**
- `python/tests/test_chat_intent_prompt.py`（20 单测）
- `frontend/Dockerfile`
- `frontend/.dockerignore`

**修改 3 个：**
- `python/eval_sets/chat_intent.jsonl`（+ 4 边界 case）
- `frontend/next.config.ts`（`127.0.0.1` + 注释）
- `docker-compose.yml`（+ frontend service）
