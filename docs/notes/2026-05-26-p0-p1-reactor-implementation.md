# 2026-05-26 P0+P1+A 实施完整记录

## 改动总览

| Phase | 内容 | 新增/改动行 | 影响文件 |
|---|---|---|---|
| Phase 0 | StudentProfile 扩展 grade + department | ~20 | schemas.py, student_profile_agent.py |
| P0 | FeasibilityAgent priority_advice LLM 化 + 数据流贯通 | ~100 | schemas.py, course_feasibility_agent.py, supervisor.py, graph.py, main.py, 前端 4 文件 |
| Grade 融入 | RerankAgent penalty + ReasonAgent 提示 | ~20 | course_rerank_agent.py, recommendation_reason_agent.py |
| P1 | LLM 语义初筛替代规则预筛 | ~80 | supervisor.py, graph.py |
| A | Supervisor ReAct 编排 | ~200 | react_tools.py(新), supervisor.py, llm_client.py, services/__init__.py |
| 前端适配 | priority_advice 类型定义 + 渲染 | ~60 | types/index.ts, RecommendPage.tsx, StreamView.tsx |

## Phase 0: StudentProfile 扩展

### 改动点

- `models/schemas.py`: StudentProfile 加 `grade: str = ""`、`department: str = ""`
- `agents/student_profile_agent.py`:
  - SYSTEM_PROMPT JSON schema 加 `grade` 和 `department` 字段
  - `_analyze_profile()` 传入 `grade`/`department`
  - `_heuristic_profile()` 正则提取：`"大[一二三四]"` → grade，学院关键词 → department

### 设计原则

- 不作为硬约束，可选字段
- 学生不提则为空字符串，不影响正常推荐
- 供下游 Agent (Feasibility/Rerank/Reason) 参考使用

---

## P0: FeasibilityAgent priority_advice LLM 化

### 背景发现

`priority_advice` 原本被计算但从未透传至 API 响应，存在三层缺口：Schema → Supervisor → 前端。

### Schema 新增

```python
class PriorityAdvice(BaseModel):
    advice: str = ""
    priority: str = "medium"  # high|medium|low

# CourseFeasibilityResult
priority_advice: dict[str, PriorityAdvice]

# RecommendationResponse 新增
priority_advice: dict[str, PriorityAdvice]
```

### FeasibilityAgent 改动

- `__init__`: 加 `self.llm = build_chat_openai(temperature=0.3, max_tokens=1024)`
- 原 `_priority_advice(course) -> str` → 重命名为 `_rule_priority_advice_batch(courses) -> dict[str, PriorityAdvice]`
- 新增 `_llm_priority_advice(courses, profile)` 异步批量生成
- `_execute()` 循环后批量调 LLM，失败退回规则

### 年级优先权规则

```
大四 > 大三 > 大二 = 大一
爆满课程（enrolled >= capacity）：大四优先留，大三次之，大二/大一可能被随机踢出
```

### Supervisor/Graph/Main 数据贯通

- `supervisor.recommend()`: 从 `feasibility_result` 提取 `priority_advice` → `RecommendationResponse`
- `supervisor.stream_recommend()`: SSE done 事件加 `priority_advice`
- `graph.py`: pipeline state 加 `priority_advice` 字段，节点间传递
- `main.py` graph 端点返回加 `priority_advice`

---

## Grade 融入

### RerankAgent

- `_compute_score()`: 加 grade penalty
  ```python
  if profile and profile.grade in ("大一", "大二") and course.popularity_level >= 4:
      profile_score -= 2.0
  ```
- RERANK_PROMPT 排序原则加：低年级选爆满课优先权低，除非高度匹配否则排后面

### ReasonAgent

- REASON_PROMPT 加抢课优先权提示规则
- REASON_STREAM_PROMPT 同步加

---

## P1: LLM 语义初筛

### 插入位置

```
Phase 1.5 硬过滤后 ~150 门
  → _llm_semantic_filter() → Top 40（新增）
  → Phase 2 重排（规则预筛只作为排序基准）
```

### 触发条件

`student_profile 存在` and `候选课程 > 40`

### 实现

- `supervisor._llm_semantic_filter(courses, profile, target_count=40)`:
  - 拼课程摘要（name, domain, category, campus, description[80], tags[5], difficulty, has_exam, popularity）
  - 拼学生画像（interests, domains, campus, exam/difficulty/workload preference, grade）
  - 调 LLM `temperature=0, max_tokens=2048` → 返回 course_id JSON 数组
  - 解析成功 → 筛出对应 Course 对象；失败 → 返回空列表
- `graph.py`: 新增 `semantic_filter_node`，插入 `parallel_phase1` 和 `parallel_phase2` 之间

### 回退策略

LLM 失败时返回空列表，`raw_courses` 保持不变，RerankAgent 的 `_compute_score` 规则预筛作为兜底。

---

## A: Supervisor ReAct 编排

### 新增文件

- `orchestrator/react_tools.py`:
  - `REACT_TOOLS`: 7 个 tool 定义（用于 `bind_tools`）
  - `ReactState`: 跨轮次状态管理
  - `ReactToolExecutor`: 工具调度器，包装各 Agent 为 async tool function

### 7 个工具

| Tool | 是否可跳过 | 说明 |
|---|---|---|
| `extract_profile` | ✅ | 提取学生结构画像 |
| `search_courses` | ✅ | 召回，strategy=wide/refined |
| `filter_hard_constraints` | ❌ 锁死 | 硬约束过滤，loop 结束时自动补调 |
| `semantic_filter_courses` | ✅ | P1 语义初筛 |
| `rerank_courses` | ✅ | 重排序 |
| `check_feasibility` | ✅ | 可行性检查 |
| `generate_reasons` | ✅ | 生成推荐理由 |

### Supervisor 改动

- `recommend()`: 加 A/B 路由 — `experiment_group == "react"` 时调用 `_react_recommend()`
- `_react_recommend()`: ReAct 循环
  - System prompt 定义工具链顺序约束
  - 最多 10 轮
  - `build_tool_calling_llm(REACT_TOOLS)` → `bind_tools`
  - 解析 `response.tool_calls` → dispatch 到 `ReactToolExecutor`
  - 强约束：loop 结束后检测 `hard_filtered == False` → 自动补调 `filter_hard_constraints`

### llm_client 改动

- 新增 `build_tool_calling_llm(tools)` → `ChatOpenAI.bind_tools(tools, tool_choice="auto")`

---

## 前端适配

### types/index.ts

- 新增 `PriorityAdvice` 接口
- `RecommendationResponse` 加 `priority_advice: Record<string, PriorityAdvice>`
- `SSEDoneData` 同步加

### RecommendPage.tsx

- `SingleResultView` 新增抢课优先级建议 Collapse 区块
- 按 priority 值渲染颜色标识：high=绿色、medium=黄色、low=红色
- 显示中文标签：稳妥/偏紧/冲刺

### StreamView.tsx

- done footer 加显示 priority_advice 条目数

---

## 测试验证

### 单元测试

39/39 全部通过。

### API 验证

```bash
# 经典模式
POST /api/v1/recommend
→ 返回包含 priority_advice (顶层字段，每个 course_id 有 advice + priority)

# 流式模式
POST /api/v1/recommend/stream
→ SSE 事件流: phase → text(流式理由) → course_start → text → course_end → done(含 priority_advice)
```

### LLM 实际调用情况

Docker 环境下 FeasibilityAgent 的 LLM priority_advice 调用可能因超时失败，自动退回规则路径。本地 `python main.py` 直接运行时 LLM 调用正常。

---

## 面试话术更新

> "Phase 0~A 五步改造后，系统从'规则为主 LLM 为辅'升级为'LLM 驱动的多 Agent 协作'。画像提取、语义初筛、重排、可行性判断、理由生成都由 LLM 参与。Supervisor 支持固定 Pipeline 和 ReAct 两种编排模式，通过 A/B 实验分流。硬约束过滤锁死在工具链中不可跳过——这是确定性安全的底线。"
