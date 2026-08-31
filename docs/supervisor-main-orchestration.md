# 流式推荐接口编排细节（v2.0.0）

> v1 文档聚焦 `SupervisorOrchestrator.stream_recommend()`。v2 已升级为：**main_agent（deepagents）通过 `recommend_courses` tool 包装 v1 supervisor**；v1 supervisor 仍是 v2 推荐的核心，但入口、调用形态、SSE 协议、缓存层都变了。本文件按 v2 现状重写，配套 `docs/architecture.md` + `docs/v2.0.0/eval-system.md` + `notes/2026-08-09-recommend-default-pipeline-speedup.md` + `notes/2026-08-09-recommend-react-optimization-and-skill-tools.md`。

## 1. 总体数据流（v2）

```
main_agent.astream_events (chat/stream)
  → LLM 识别意图 = "推荐" → 调 recommend_courses tool
    → recommend_courses.ainvoke (v2 ToolRegistry)
      → SupervisorOrchestrator.stream_recommend_unified
        → 双模式分支（pipeline 默认 / react 可选）
        → stream_recommend_pipeline（默认，最快）
        ├─ Phase 1: 画像 ∥ 宽召回  (student_profile ∥ course_recall)
        ├─ Phase 1.5: 硬约束过滤  (纯规则, 8 tool 锁死)
        ├─ Phase 1.75: LLM 语义初筛 (候选>40 且有画像)
        ├─ Phase 2: 重排 ∥ 可行性  (course_rerank ∥ course_feasibility)
        └─ Phase 3: 流式理由  (recommendation_reason → course_start/text/course_end)
      → done 事件
  → SSE 协议 (路 2 升级)
    每条事件: id: N\nevent: <name>\ndata: {...}
    重连: Last-Event-ID header → EventBuffer.replay_from()
```

## 2. v2 入口与 SSE 协议

### 2.1 三个入口

| 入口 | 路径 | 调用 | 评估 |
| --- | --- | --- | --- |
| **直接推荐** | `POST /api/v1/recommend/stream` | `SupervisorOrchestrator.stream_recommend_unified()` | eval 无独立数据集（covered by 旧 `recommend-2026-08-15.json`） |
| **main_agent chat 路由** | `POST /api/v1/chat/stream` | main_agent LLM 决策 → `recommend_courses` tool → 同上 | `chat_intent-2026-08-18.json`：intent_01/02/03 等 |
| **前端 React 入口** | `<StreamView />` → `api.recommendStreamWithRetry` | 同 chat 路由 | dev smoke |

### 2.2 SSE 帧格式（路 2 升级）

```text
id: 42
event: text
data: {"course_id":"c1","token":"AI 导论推荐..."}

id: 43
event: done
data: {"last_event_id":43,...}
```

- 每条事件带 `id:` 字段（按 `chat:{session_id}` 或 `recommend:{sha1(user_id|prompt)[:16]}` 单调递增）
- 用 Redis `INCR` 全局自增 + `LPUSH+LTRIM` 环形缓冲（max 100 条）+ TTL 30 分钟
- 客户端 `Last-Event-ID` header 触发 `EventBuffer.replay_from()` 回放缺失事件
- 客户端 `consumeSSEWithRetry` 指数退避 500ms→1s→2s（max 3）

### 2.3 响应头

| Header | 值 | 作用 |
| --- | --- | --- |
| `Content-Type` | `text/event-stream` | SSE 标记 |
| `Cache-Control` | `no-cache` | 避免中间层缓存 |
| `Connection` | `keep-alive` | 长连接 |
| `X-Accel-Buffering` | `no` | 避免代理缓冲 |
| `X-SSE-Thread-Key` | `report:{uuid}` | 仅 `/api/v1/report` 用，客户端断线续传回放缓存 |

## 3. v1 supervisor 在 v2 中的角色

### 3.1 双重身份

| 身份 | 调用方 | 路径 |
| --- | --- | --- |
| **main_agent 子 agent** | `<StreamView>` chat → LLM 识别"推荐"意图 → `recommend_courses` tool | `python/tools/recommend/recommend_courses.py` |
| **直接 API 端点** | `POST /api/v1/recommend/stream` | `python/api/recommend.py` |

两种入口都走同一 `supervisor.stream_recommend_unified(request, mode=...)` —— **同一套核心代码**。

### 3.2 决策 4：v1 包装为 subgraph 暴露为 tool

> v1 supervisor 是 deepagents 的**子 agent**：以 `recommend_courses` tool 形式被 main_agent 调用，对外屏蔽内部 5 agent 细节。v1 supervisor 内部仍可独立做 A/B 实验（pipeline vs react）。

**实现**（`python/tools/recommend/recommend_courses.py`）：
```python
@tool(args_schema=RecommendCoursesInput)
async def recommend_courses(
    user_id: str,
    prompt: str,
    num_items: int = 5,
    scene: str = "course_selection",
    mode: Literal["pipeline", "react"] = "pipeline",
) -> RecommendationResponse:
    """main_agent 工具入口；内部走 supervisor.stream_recommend_unified"""
    request = RecommendationRequest(user_id=user_id, prompt=prompt, ...)
    return await supervisor.stream_recommend_unified(request, mode=mode)
```

## 4. supervisor.stream_recommend_unified 详解（v2 现状）

### 4.1 双模式分支

```python
async def stream_recommend_unified(request, mode="pipeline"):
    if mode == "react":
        async for evt in _stream_recommend_react(request):
            yield evt
    else:  # pipeline 默认
        async for evt in _stream_recommend_pipeline(request):
            yield evt
```

| 模式 | 用途 | 延迟 | 备注 |
| --- | --- | --- | --- |
| **pipeline**（默认） | 常规推荐 | 8-15s | 5 阶段确定顺序，token 可预测 |
| **react** | 异常恢复（召回不足 / 全爆满） | 15-30s | 7 工具动态决策，硬约束锁死不可跳过 |

### 4.2 Pipeline 5 阶段

| Phase | 阶段 | 内部实现 | 延迟占比 |
| --- | --- | --- | --- |
| 1 | 画像 ∥ 宽召回 | `student_profile_agent` (LLM 抽 8 维) + `course_recall_agent` (Redis 候选 ID → MySQL 96 + Milvus 54 → 合并 143) | ~30% |
| 1.5 | 硬约束过滤 | `hard_constraint_filter.py`（纯规则：校区/时间/考试/教师/类别） | <1% |
| 1.75 | LLM 语义初筛 | 候选 >40 且有画像时调 LLM | ~10% |
| 2 | 重排 ∥ 可行性 | `course_rerank_agent`（规则预筛 + LLM 精排）+ `course_feasibility_agent`（LLM priority_advice + 规则兜底） | ~40% |
| 3 | 流式理由 | `recommendation_reason_agent` + `stream_token_markup_parser`（按课程级 token 输出） | ~20% |

### 4.3 关键业务指标（eval_system.md + reports）

| 指标 | 来源 | 数值 | 备注 |
| --- | --- | --- | --- |
| **chat_intent → recommend** 路由 | `chat_intent-2026-08-18.json` | intent_01/02/03 等历史 smoke 通过 | 路由到 dispatch_module(recommend) |
| **直接 recommend/stream** | `recommend-2026-08-15.json` | v1 历史通过 | pipeline 模式默认 |
| **5 agent 完整链路** | supervisor.py `stream_recommend` 函数 | 8-15s 端到端 | 1 阶段画像 30% + 2 阶段并行 40% + 3 阶段 20% + 1.5+1.75 11% |
| **8 tool 锁死**（react 模式） | `react_tools.py` + `hard_constraint_filter.py` | 硬约束不可跳过 | 用户说"只要西校区"时推荐东校区是 bug |
| **Redis 候选 ID 缓存** | `recall_cache_repo.py` | exact_key + semantic_key 双层 | 召回 143 候选里多数来自 cache |

## 5. SSE 事件类型（v2 推荐流）

| event | data 字段 | 触发时机 | 消费者 |
| --- | --- | --- | --- |
| `phase` | `{phase, request_id?, num_items?, profile_extracted?, warning_count?}` | 5 阶段进度 | 前端 phase dots |
| `course_start` | `{course_id, course_name, index?}` | 一门课开始流式理由 | `CourseInlineCard` 渲染 |
| `text` | `{course_id, token}` | 单个 token | 流式累加 + rAF flush |
| `course_end` | `{course_id}` | 一门课结束 | 隐藏流式 cursor |
| `done` | `{request_id, user_id, courses[], selection_warnings[], experiment_group, agent_results{}, total_latency_ms, last_event_id?}` | 推荐结束 | `SingleResultView` / `CompareView` 渲染 |
| `error` | `{code, message, phase?}` | 任一阶段失败 | 红色 error 卡片 + 重试按钮 |

## 6. 字段转换

| 来源 | 字段 | 转换 |
| --- | --- | --- |
| `RecommendationRequest` | `user_id` | 注入到所有 agent 内部（`get_current_user_id()`） |
| `RecommendationRequest` | `prompt` | 画像 agent 抽 8 维（兴趣/校区/时间/考核/作业量/类别/教师/年级） |
| `RecommendationRequest` | `mode` | 透传到 `stream_recommend_unified(request, mode=mode)` |
| `RecommendationResponse` | `agent_results{}` | 每个 agent 的 success/latency_ms/confidence/error 字典 |
| `RecommendationResponse` | `selection_warnings[]` | 可行性 agent 的 `selection_warnings` + 规则兜底 |

## 7. 异常收口

- 硬约束 agent 锁死（决策 4 修订）：用户说"只要西校区" → 必过滤东校区；re-act 模式下不可跳过
- 召回不足 → 触发 `shortage_warning`（course_supervisor.py:127），fallback to 全量 500 门
- LLM 失败 → 走 `default 8 / 6 / 3` 规则排序（course_rerank_agent.py fallback）
- SSE 中断 → `EventBuffer.replay_from(Last-Event-ID)` 回放（路 2）
- 重试耗尽 → 抛 `NETWORK_ERROR`（前端 toast.error 提示）

## 8. 缓存层

| 层 | key | TTL | 命中场景 |
| --- | --- | --- | --- |
| Redis exact | `recall_cache:exact:{sha1(profile)}` | 900s | profile 完整 → MySQL 96 候选 |
| Redis semantic | `recall_cache:semantic:{sha1(profile_sign)}` | 900s | profile 相似（threshold 0.95） → 跳过 Milvus |
| Redis short lock | `recall_lock:{sha1(profile)}` | 5s | 防并发重复召回 |
| Redis SSE | `sse:counter:{thread_id}` + `sse:events:{thread_id}` | 3600s + 1800s | 路 2 SSE 续传环形缓冲 |

## 9. 验证

| 维度 | 状态 | 证据 |
| --- | --- | --- |
| pipeline 端到端 | ✅ | `notes/2026-08-09-recommend-default-pipeline-speedup.md` 测速；intent_01/02/03 smoke 通过 |
| react 端到端 | ✅ | `notes/2026-08-09-recommend-react-optimization-and-skill-tools.md` |
| 5 agent 完整 | ✅ | `python -m eval/runner.py --set chat_intent --live` 20 case |
| 8 tool 锁死 | ✅ | supervisor.py 单元测试 39 个通过（v1 历史）+ pytest 335 passed（v2） |
| Redis 缓存命中率 | ✅ | `recall_cache_repo.py` 单元测试 + cache_probe 日志 |
| SSE 续传 | ✅ | `notes/2026-08-18-phase3-sse-resumability-and-cancellation.md`（路 2） |

## 10. 不在 v2 范围

- A/B 实验组（v1 `experiment` 字典）—— 已移到 LangSmith Dataset
- react 模式自动 fallback to pipeline（决策 4 修订）—— v1 时代有，v2 已简化
- LLM-as-judge 全套指标（faithfulness / answer_relevancy）—— Phase 4
- 多模态推荐（基于课程封面图）—— Phase 4+
