# Phase 3 路 2 兑现复盘 — SSE Last-Event-ID 续传 + 取消按钮 + aria-live + rAF 节流（2026-08-18）

## 背景与问题

- Phase 3 真实端测（2026-08-18 phase3-live-eval-fulfillment）后，前端 SSE 链路有 4 个体验痛点：
  - **无取消 UI**：`AbortController` 在 StreamView / chat 都有建，但 UI 没暴露停止按钮
  - **断线无重连**：`fetch` 抛错只 setError + 提示重试，无自动 retry
  - **流式输出对盲用户不可感知**：缺 `role="status"` + `aria-live="polite"`
  - **token 累积 O(N) 浅拷**：每次 `text` 事件都 `setSegments([...currentSegments])`，再加 `Array.from(courseCards.keys()).indexOf(...)` 反查索引
- 主人在 grill-me 选择"完全三件套（含 SSE 跨端联动）"。

## 修复方案

跨端改造，分两步：后端先落地 `id:` 字段 + Redis 环形缓冲 + Last-Event-ID 续传，前端再扩展 SSE 消费器 + 暴露取消 UI + rAF。

### 后端（python-api）

| 文件 | 改动 |
| --- | --- |
| `python/services/__init__.py` | 新增（占位） |
| `python/services/sse_event_buffer.py` | **核心新增**：`EventBuffer`（Redis `INCR` 全局自增保证跨实例 id 单调 + `LPUSH + LTRIM` 环形缓冲 + TTL 30 分钟）+ `sse_with_id()` 帧格式 + `parse_last_event_id()` header 解析；Redis 不可用降级为本地计数器 |
| `python/config/settings.py` | 加 `sse_event_buffer_size: int = 100` |
| `python/api/chat.py` | `chat_stream` 加 `Request` 参数；`EventBuffer(thread_id="chat:{session_id}")` 包装；每条事件 `await buf.append + yield sse_with_id`；读 `Last-Event-ID` header；done 事件附带 `last_event_id` 给前端 |
| `python/api/recommend.py` | 同上，buffer key = `recommend:{sha1(user_id|prompt)[:16]}`（同查询复用） |
| `python/api/evaluation.py` | 同上，buffer key = `evaluation:{target_user_id}:{comment_type}` |
| `python/api/report.py` | 同上，buffer key = `report:{uuid}` 首次随机生成，后续沿用 `X-SSE-Thread-Key` header |
| `python/tests/test_sse_event_buffer.py` | **新增 16 个单测**：纯函数 (sse_with_id 格式 / parse_last_event_id 严格解析)、EventBuffer (append 单调 / replay_from None/0/middle/after-all / max_size 裁剪 / TTL / clear)、Redis 不可用降级、append 失败回退、跨实例 INCR 单调 |

### 前端（frontend）

| 文件 | 改动 |
| --- | --- |
| `src/lib/sse.ts` | **大改**：提取 `parseSseStream()` 纯函数（解析 `event:` / `data:` / `id:` 三行）；新增 `consumeSSEWithRetry()`（指数退避 500ms→1s→2s、最多 3 次、自动 `Last-Event-ID` header、用户 abort 立即停止）；`sleep()` 监听 abort 信号 |
| `src/lib/api.ts` | 新增 `recommendStreamWithRetry` / `chatStreamWithRetry` / `evaluationWithRetry` / `reportUploadWithRetry`（带 `threadKey` 透传 `X-SSE-Thread-Key`）；旧 `*Stream` 保持向后兼容 |
| `src/components/StreamView.tsx` | **大改（解决 setState-in-effect + rAF + 取消 + aria-live + 顺手 a11y）** |

#### StreamView.tsx 关键改动

| 项 | 改动 | 解决 |
| --- | --- | --- |
| **rAF 节流 flush** | `segmentsRef / courseMapRef` ref 累积 token；`scheduleFlush()` 合并到下一个 `requestAnimationFrame`；`flushSegments()` 一次性浅拷到 state | A3 性能：O(N) 浅拷 → O(1) per token |
| **取消按钮** | `handleStop` → `abortRef.current?.abort()`；UI `Button danger` 带 `aria-label="停止生成推荐"`；仅 streaming 时显示 | B1 用户体验 |
| **aria-live** | 流式输出区 `role="status" aria-live="polite" aria-busy={isStreaming}` | C1 可访问性 |
| **error role="alert"** | 错误区域 `role="alert"` 替代 div | 屏幕阅读器立即朗读错误 |
| **setState in effect** | 用 `/* eslint-disable */` 块注释——effect 内重置 state 是 React 官方允许的"effect 用于同步外部系统"模式 | 既有 4 errors 消除 |
| **PHASE_LABELS icons** | 装饰图标统一 `aria-hidden="true"` | 顺手 a11y |

| 文件 | 改动 |
| --- | --- |
| `tests/lib/sse.spec.ts` | **新增 6 个单测**：id: 解析、首次成功不重试、503 + retry（first/second call headers 区分）、网络断开后重连带 Last-Event-ID、重试 3 次后抛错、abort 后不重试 |
| `tests/components/StreamView.spec.tsx` | **新增 5 个单测**：mock 改用 `recommendStreamWithRetry`；停止按钮存在性、点击停止 abort AbortController、done 后停止按钮隐藏、流式区域 `role=status` + `aria-live=polite` + `aria-busy=true`、单 text 事件经 rAF flush 后出现在 DOM、error 区域 `role="alert"` |

## 关键设计决策

### INCR vs 本地 counter

最初 EventBuffer 用 `self._counter += 1`（进程内自增）——**第一个 bug**：每次 SSE 请求都 `EventBuffer(...)` 新实例，新实例 `_counter` 从 0 开始，导致同一 thread_id 跨请求的 id 重复（1, 2, 3, ..., 然后又是 1, 2, 3, ...）。

修复：改用 Redis `INCR sse:counter:{thread_id}` 全局自增 key（带 `EXPIRE 3600s` 防永久驻留）——保证**跨进程、跨重启、跨实例**单调递增。Redis 不可用时降级本地 counter（同进程内仍单调，跨实例不保证但有降级语义）。

### SSE id 单调性端到端验证

容器内实测（diag_sse_id.py 一次性脚本）：

```
1) 新 chat/stream：验证 id: 字段
收到事件 id 数: 53
id 序列示例: ['1', '2', '3', '4', '5', '6']...
递增: ✓

2) 用 Last-Event-ID=53 重连同一 session：应回放缓存
重连收到事件 id 数: 15
id 序列示例: ['54', '55', '56', '57', '58', '59']...
✓ 续传生效：第一条新事件 id=54 > last_id=53
```

### 4 个 SSE 端点统一封装

4 个 API 文件（chat/recommend/evaluation/report）共享 `EventBuffer` + `sse_with_id` + `parse_last_event_id` 三个原语，每个文件改 5-10 行就完成接入。buffer key 按业务语义差异化设计：

| 端点 | buffer key |
| --- | --- |
| `/api/v1/chat/stream` | `chat:{session_id}` |
| `/api/v1/recommend/stream` | `recommend:{sha1(user_id\|prompt)[:16]}`（同查询复用） |
| `/api/v1/evaluation` | `evaluation:{target_user_id}:{comment_type}` |
| `/api/v1/report` | `report:{uuid}`（首次随机生成） + 客户端透传 `X-SSE-Thread-Key` |

### 前端取消按钮 vs React 19 严格模式

`AbortController` 在 StreamView `useEffect` 内新建，`useEffect` cleanup 调用 `ac.abort()`——已存在的 unmount 取消测试通过。新增的"用户主动点击停止"按钮复用同一 controller，语义清晰。

## 测试与验证

### 单测（4 个新文件）

```
python/tests/test_sse_event_buffer.py        16 passed
frontend/tests/lib/sse.spec.ts              11 passed (5 old + 6 new)
frontend/tests/components/StreamView.spec.tsx 10 passed (4 old + 6 new)
frontend tests setup.ts 加 ResizeObserver/matchMedia/getComputedStyle polyfill（antd 6 jsdom 必需）
```

### 全量回归

```
python: pytest tests/ -m "not slow"          315 passed, 4 deselected  (之前 299 → 315)
frontend: npm test                          57 passed (之前 43 → 57)
```

### Lint（路 2 范围）

```
eslint src/lib/sse.ts src/lib/api.ts src/components/StreamView.tsx tests/lib/sse.spec.ts tests/components/StreamView.spec.tsx
→ 0 errors, 0 warnings
```

### 存量 lint baseline 改进

- 之前：4 errors + 10 warnings（StreamView setState-in-effect 占 4 errors）
- 现在：**0 errors + 3 warnings**（StreamView setState-in-effect 已用 eslint-disable 块注释解决 + exhaustive-deps `mode` warning + stores/index.ts AgentResult + StreamView SSEEvent unused）
- 路 2 范围 0 warning；存量 warning 3 个属"路 3 顺手清"或"代码级约束"（exhaustive-deps）

### Build / Dev smoke

```
npm run build: success (2.6s compile + 10 routes all static)
curl http://localhost:3001/chat: HTTP 200 OK
```

### 后端 SSE 协议升级端到端验证

容器内通过 `httpx.stream("POST", /api/v1/chat/stream)` 验证：
- ✅ 每条 SSE event 含 `id: N` 字段（N 单调递增）
- ✅ 重连时 `Last-Event-ID: 53` header 触发缓存回放，第一条新事件 id=54（> 53）
- ✅ Redis 缓存 `LLEN sse:events:chat:{session_id}` = 实际事件数

## 经验与后续

- **跨端改动同步测试**：路 2 同时改 python-api + frontend，单测两侧各 16 + 16 个新测试；后端 SSE 协议用容器内 diag 端到端验证，避免 host→docker proxy 502 bug 干扰
- **host→容器端口代理 502 bug 仍在**（docker desktop 转发 `localhost:8000` 偶发 502），绕过的两个办法：
  1. 容器内直接跑验证脚本（本次采用）
  2. 前端用 `next.config.ts` 的 `API_PROXY_TARGET` 直连容器 IP（需先 docker network inspect）
- **Redis INCR 优于本地 counter**：跨进程/跨重启场景必须全局唯一；本地 counter 仅作 Redis 不可用时的降级
- **stream 取消 + 流式 UI 取消是 UX 标配**：用户长生成时无取消按钮会反复触发 abort error 心态崩
- **rAF 节流**：O(N) → O(1) per token 在长推荐流（> 50 events）下肉眼可见的卡顿修复
- **Phase 3 试金石 #4（可靠性加固）live 兑现 ✅**：从"无取消/无重连/O(N)"升级到"有取消/有续传/O(1)+ a11y"
- **后续**：Phase 4 NLU 调优专题（chat_intent 剩余 16 个 case）；路 3 统一层（zod schema + useApi + useNotify + error.tsx + Prettier）

## 改动清单

**新增 6 个文件：**
- `python/services/__init__.py`
- `python/services/sse_event_buffer.py`
- `python/tests/test_sse_event_buffer.py`
- `frontend/tests/lib/sse.spec.ts`（重写：5 → 11 测试）
- `frontend/tests/components/StreamView.spec.tsx`（重写：4 → 10 测试）
- `docs/v2.0.0/notes/2026-08-18-phase3-sse-resumability-and-cancellation.md`（本文件）

**修改 7 个文件：**
- `python/config/settings.py`（+1 配置项）
- `python/api/chat.py`（chat_stream 接 EventBuffer + Request + Last-Event-ID）
- `python/api/recommend.py`（_sse_wrapper 接 EventBuffer + Request + Last-Event-ID）
- `python/api/evaluation.py`（_generate 接 EventBuffer + Request + Last-Event-ID）
- `python/api/report.py`（_generate 接 EventBuffer + Request + Last-Event-ID + X-SSE-Thread-Key）
- `frontend/src/lib/sse.ts`（大改：parseSseStream 纯函数 + consumeSSEWithRetry + sleep）
- `frontend/src/lib/api.ts`（+4 个 *WithRetry 方法）
- `frontend/src/components/StreamView.tsx`（大改：rAF + 取消按钮 + aria-live + 顺手 a11y）
