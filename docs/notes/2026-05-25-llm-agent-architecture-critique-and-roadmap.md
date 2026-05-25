# 2026-05-25 LLM 参与度审视、Agent 架构批判与改造路线

## 一、项目的真实 LLM 参与度

| 编排环节 | 实现方式 | LLM 的实际贡献 |
|---|---|---|
| 课程召回 | Redis 缓存 + MySQL 结构化查询 + Milvus 向量搜索 + 规则打分 | **零** — 纯工程代码 |
| 硬约束过滤 | 8 条正则/字符串匹配（校区、类别、时间、老师、考试、小组、难度、作业量） | **零** — 纯确定性规则 |
| 学生画像提取 | `StudentProfileAgent`: LLM 主路径 + `_heuristic_profile()` 规则后备 + `_extract_prompt_hard_constraints()` 确定性补充 | NLP 结构化抽取，规则兜底确保不丢关键约束 |
| 排序预评分 | `CourseRerankAgent._compute_score()`: domain +4 / category +3 / campus +2 / 偏好加权 / Milvus×0.5 | **零** — 纯规则公式，仅用于缩候选集至 Top 40 |
| 最终排序 | `CourseRerankAgent`: LLM 对 Top 40 重排序，解析失败自动退回 `_rule_based_rerank()` | 规则排完粗序后 LLM 做语义微调 |
| 可行性检查 | `CourseFeasibilityAgent`: 容量告警、偏好软冲突检测、抢课优先级建议 | **零** — 纯规则 `if/else` |
| 推荐理由生成 | `RecommendationReasonAgent`: LLM 生成文案（非流式 + SSE 流式两路径），失败退回字段拼接模板 | 唯一真正的生成性任务 |

**总体判断：核心召回、过滤、评分链路是工程代码。LLM 参与 3 个环节，其中 2 个有完整的规则后备（画像提取失败→规则，排序解析失败→规则）。**

---

## 二、核心架构决策：Pipeline vs 单次 LLM

面试官必问问题：**"为什么不直接一个 prompt 把学生需求 + 500 门课喂给 LLM，一次返回推荐？"**

| 维度 | 单次 LLM 全量推荐 | 当前多 Agent Pipeline |
|---|---|---|
| 确定性正确性 | ❌ LLM 可能漏课、幻觉、漏约束 | ✅ 硬约束过滤零概率出错 |
| Token 成本 | 500 门课×完整描述 → 单次数万 token | Top 40 送 LLM → 大幅节省 |
| 延迟 | 一次 LLM 调用 | 3-4 次 LLM + embedding 搜索 |
| 语义理解深度 | ✅ LLM 读取全部课程，全局视野 | ⚠️ LLM 只见过规则预筛后的 40 门 |
| 理由质量 | ✅ 基于全量课程，可能更贴切 | ⚠️ 理由在"被裁切后的世界"中生成 |

**架构 trade-off 本质：确定性可靠性 vs LLM 理解深度。**

面试话术：

> "全量塞给 LLM 在理论上更理想，但 500 门课×描述 单次请求上万 token，经济性不可靠。我选择用规则做 safety net 保证硬约束不犯错，用 LLM 做 reasoning 和 generation 提升排序和文案的上限。规则保下限，LLM 提上限，两个能力各司其职。"

---

## 三、"这是不是真正的 Agent 系统？"——自我审视

### 当前不足

1. **Agent 之间无对话/协商/质疑** — 编排器按固定顺序调用，每个 Agent 拿到上游输出、加工、返回，无交互
2. **编排全硬编码** — Phase 1→1.5→2→3 写死在代码里，LLM 不参与"下一步该做什么"的决策
3. **非 Plan-and-Execute、非 ReAct、非 crew debate** — LLM 不产出计划，不思考，不协作
4. **Redis 缓存 ≠ Agent 记忆** — 当前缓存是请求去重+加速，不是"能记着学生上一轮偏好并调整策略"的 conversation memory

### 已有但未强调的亮点

- **Robustness pattern**: 画像 Agent 的 LLM→规则后备双路径
- **Fallback chain**: 重排 Agent 解析失败自动退回规则排序
- **关注点分离**: 硬约束过滤独立于排序，各模块职责清晰
- **多阶段并行编排**: Phase 2 重排与可行性并行，Phase 3 串行保证理由引用排好的顺序

### 面试官的潜在追问

> "你标题写多 Agent，但翻了代码发现 Agent 之间没有任何对话，这跟一个普通的 FastAPI + LangChain + Milvus 后端有什么区别？"

回应思路：
- 承认当前是"固定编排 Pipeline + LLM 增强"，而非自主协作 Agent
- 解释选择：推荐场景硬约束必须确定，对话会引入概率误差
- 指出可扩展点：画像变更时可触发 Agent 相互通知、召回不足时 Agent 自主放宽条件重试

---

## 四、改造路线图

### 不该 LLM 化的环节（动了反而退步）

| 环节 | 原因 |
|---|---|
| HardConstraintFilter 的约束检查 | 硬约束必须确定。LLM 会让"东校区不能变西校区"产生概率误差——这是安全底线 |
| FeasibilityAgent 的容量/时间计算 | `enrolled >= capacity` 不需要 LLM 去"理解"，算数就是算数 |

### P0 — 改动最小，效果最明显

**可行性 Agent `_priority_advice()` LLM 化**

现状：两行字符串 — "冲刺优先级高" 或 "可作为稳妥备选"。

改造：LLM 根据课程容量、抢课节奏、学生年级/选课轮次，生成个性化建议：

> "这门课上学期 150% 满员，你是大二，大三大四优先选。建议准备《XX 课》作为备选，内容相似但竞争小。如果时间灵活可以考虑周三晚上的平行班。"

Token 成本极低，三行提示词，文案质量质变。

### P1 — 让 LLM 真正参与语义筛选

**召回后 → LLM 初筛替代规则预筛**

现状：规则公式打分从 200 门缩到 40 门。规则只能做字段匹配（domain、category、关键词命中）。

改造：把召回的~200 门课各一行摘要 + 学生画像送给 LLM，让 LLM 从中挑出 30-40 门"真正语义相关"的。LLM 能看懂的规则看不懂：
- 课程名《Python 入门》但大纲全是爬虫，跟学生说的"想学数据分析"不对口
- 课程名《影视鉴赏》但实际是理论课写影评，跟学生"想轻松看电影"不符

Token 成本：一次调用，中等。

### P2 — 增强重排 LLM 的信息完整度

现状：Top 40 送 LLM 的是紧凑摘要，LLM 没读完整课程描述。

改造：喂给 LLM 每门课的 4 类 chunk 完整描述（basic、schedule_capacity、learning_profile、audience_tags），让 LLM 基于对课程内容的语义理解排序，而非基于规则分数排序。

Token 成本：中高（40门×完整描述）。

### P3 — 可行性后加 LLM 反思 + 替代方案生成

现状：可行性只检查不生成替代方案。

改造：可行性检测完成后，让 LLM 对有风险的推荐生成替代课程建议。真正解决学生"纠结取舍"的核心痛点——不是告诉学生"这门课满了"，而是告诉学生"满了该怎么办"。

Token 成本：低（仅在风险课程上触发）。

### 可选增强：真正的 Agent 交互

| 层次 | 改动 | Token 增量 | 工作量 |
|---|---|---|---|
| 事后反思 | 可行性后 LLM 回顾理由并补充风险提示 | +1 次 LLM | 加编排节点 |
| 条件分歧 | 召回 <3 门时 Agent 自主放宽条件重试 | 偶尔 +1 次 | 修改编排器分支 |
| 真正对话 | Agent 间可互发消息、质疑、修正 | 不可控 | 重写编排器 |

---

## 五、面试核心话术

> "我用规则保证下限——硬约束过滤绝对不能出错。但排序和推荐理由的上限是 LLM 提上去的：规则只能做字段匹配，LLM 能理解'这门 Python 课实际是教爬虫的，跟你想学数据分析不对口'这种语义。我的架构是：规则做 safety net，LLM 做 reasoning 和 generation，两个各司其职。"
>
> "为什么不是全 LLM？因为推荐场景里有确定性约束——校区、时间、考试要求——这些错一个就是一次糟糕体验。我用规则处理确定性，把容忍模糊的部分留给 LLM。这是 pragmatist 的选择，不是设计不足。"
>
> "多 Agent 的价值不只在对话，也在关注点分离。画像提取、召回、排序、可行性、理由生成各由一个专门的 Agent 负责，每个 Agent 有自己的 LLM 调用策略和后备路径。这比一个巨型 prompt 更可控、更可测试、更可解释。"

---

## 六、方案 A — Supervisor 工具调用（ReAct 编排）

### 6.1 当前系统：零工具调用

`grep` 搜索 `tool|function_call|bind_tools|with_structured_output` 全项目无命中。编排器 553 行全是硬编码流程，LLM 从未参与"下一步该干什么"的决策。

### 6.2 为什么推荐 Pipeline 的执行顺序不变

推荐这件事的依赖关系是天然的：

```
必须先有画像 ──→ 才能定向召回 ──→ 才能过滤 ──→ 才能排序 ──→ 才能出理由
```

不可能"先排序再召回"。LLM 再聪明也绕不开这个依赖图。**方案 A 不是让 LLM 乱序执行，而是让 LLM 做三类动态决策。**

### 6.3 LLM 接管的三类决策

| LLM 决策点 | 当前硬编码做法 | LLM 接管后 |
|---|---|---|
| **是否需要精召回** | 第 126 行 `if student_profile:` 固定判断 — 只要有画像就无条件精召回 | LLM 看画像："这个学生只说了'推荐几门课'没具体偏好，宽召回够了，跳过精召回" |
| **召回是否充分** | 不判断，直接往下走 | LLM 检查结果："只召回了 5 门，且全是艺术类，学生说了想选理科 — 放宽条件再搜一轮" |
| **可行性告警后要不要重排** | 不处理 — 只挂 warning 不回头 | LLM 看到 3 门全爆满："找相似的非爆满课程替换，重新排序" |

**核心逻辑不变，但 LLM 多了三个可以回头的决策点。** 这是 ReAct 里 `Act → Observe → Reflect → Act again` 的循环。

### 6.4 具体设计

#### Tool Schema 定义

编排器 LLM 拿到的 6 个工具：

```python
tools = [
    {"name": "extract_profile", "params": {"prompt": "string"},
     "desc": "从学生自然语言需求中提取结构化画像"},
    {"name": "search_courses", "params": {"strategy": "wide|refined", "profile": "StudentProfile|null"},
     "desc": "召回候选课程。wide=仅用prompt向量搜索；refined=基于画像结构化字段搜索"},
    {"name": "filter_hard_constraints", "params": {"courses": "list", "constraints": "HardConstraints"},
     "desc": "硬约束确定性过滤 — 校区/类别/时间/老师/考试等违规直接剔除"},
    {"name": "rerank_courses", "params": {"courses": "list", "profile": "StudentProfile"},
     "desc": "按学生偏好排序课程"},
    {"name": "check_feasibility", "params": {"courses": "list"},
     "desc": "检查容量、时间冲突、偏好匹配"},
    {"name": "generate_reasons", "params": {"courses": "list"},
     "desc": "生成推荐理由和选课建议"},
]
```

**关键约束：`filter_hard_constraints` 锁死不可跳过。** LLM 只能决定"什么时候调"，不能决定"调不调"。硬约束过滤内部仍是 8 条纯规则 — 确定性不妥协。

#### 一次推荐的 ReAct 执行轨迹示例

```
System: 你是一个课程推荐编排器。根据学生需求调用工具完成推荐。
        硬约束过滤工具必须调用，不可跳过。

User: "我是计算机学院大二，想选东校区的艺术类公选课，不要考试"

─────────────────────────────────────────────
[Round 1]
Thought: 学生提了校区（东校区）、类别（艺术）、考核要求（不考试）。
        先提取结构化画像。
Action: extract_profile(prompt="我是计算机学院大二...")
Observation: {
  "hard_constraints": {
    "campus": ["东校区"], "categories": ["艺术"],
    "no_exam": true
  },
  "interests": ["艺术"],
  "department": "计算机学院", "grade": "大二"
}

─────────────────────────────────────────────
[Round 2]
Thought: 画像有具体硬约束（校区+类别+不考试），用 refined 策略召回。
Action: search_courses(strategy="refined", profile=...)
Observation: 返回了 3 门课程，只有 1 门在东校区

─────────────────────────────────────────────
[Round 3]
Thought: 结果太少。宽松一点用 wide 策略再搜一轮，然后合并。
Action: search_courses(strategy="wide")
Observation: 返回了 18 门课程

─────────────────────────────────────────────
[Round 4]
Thought: 18 门够了。先硬约束过滤再排序。
Action: filter_hard_constraints(courses=18门, constraints=...)
Observation: 过滤后剩余 9 门，移除了西校区的 7 门和有考试的 2 门

─────────────────────────────────────────────
[Round 5]
Thought: 9 门通过硬过滤，排序。
Action: rerank_courses(courses=9门, profile=...)
Observation: 排名完成

─────────────────────────────────────────────
[Round 6]
Thought: 检查可行性，然后出理由。
Action: check_feasibility(courses=...)
Observation: 第 1 名爆满（150%），第 2 名容量偏紧（85%），第 3 名正常

─────────────────────────────────────────────
[Round 7]
Thought: 第 1 名爆满风险高 — 但学生没要求避开爆满课，这是软约束。
        不需要回头重排，理由里提示风险即可。
Action: generate_reasons(courses=...)
Observation: ["第 1 名：人气爆满抢课难度高，建议开选后优先抢...", ...]

Final: 返回 3 门推荐 + 抢课风险提示
```

### 6.5 LLM 可能触发的"回头看"分支

正常情况下走直线：画像→召回→过滤→排序→可行性→理由（6 轮，与当前 pipeline 相同）。

额外分支仅在异常时触发：

| 异常场景 | 触发条件 | LLM 额外动作 | Token 增量 |
|---|---|---|---|
| 初始召回太少 | <5 门 | `search_courses(strategy="wide")` 宽松再搜 | +1 轮 |
| 硬过滤后严重不足 | <3 门 | `search_courses(strategy="wide")` 放宽校区/类别再搜 | +1 轮 |
| 全部爆满 | feasibility 返回全部 high_severity | 寻找非爆满相似课替换 | +1-2 轮 |
| 学生多次交互 | 同一 session 第二次请求 | 对比上次画像，仅搜索变化部分 | +1 轮 |

### 6.6 改动量评估

| 文件 | 改动 | 行数 |
|---|---|---|
| `orchestrator/supervisor.py` | 新增 `_react_loop()` 方法，保留原 `recommend()` 做 fallback | ~150 行 |
| `orchestrator/` | 新增 `react_tools.py` — 把 5 个 Agent 包装成 tool 函数 | ~80 行 |
| `services/llm_client.py` | 新增 `build_tool_calling_llm()` — `ChatOpenAI.bind_tools(tools)` | ~20 行 |
| 原有 5 个 Agent | **不改动** — Agent 接口不变，只是被 tool function 包装调用 | 0 行 |
| `HardConstraintFilter` | **不改动** — 作为 tool 内部实现，确定性不变 | 0 行 |

**总新增 ~250 行，原有代码零改动。Token 增量：正常路径 +0 轮（与当前相同），异常路径 +1~2 轮（200-500 token/轮）。**

### 6.7 面试话术

> "我的编排器不是硬编码的 pipeline，而是一个 ReAct 循环：LLM 根据学生需求的复杂度动态决定执行哪些步骤。正常情况走固定路径确保延迟可控，但遇到 — 召回不足、硬过滤后课程太少、推荐的课全爆满 — LLM 可以自主决定回头放宽条件重试或寻找替代方案。"
>
> "硬约束过滤锁死在工具链中不可跳过 — 校区不允许推测、考试要求不允许商量。LLM 控制的是策略选择，不是规则本身。这是 Agent 自主性与确定性安全的平衡。"

### 6.8 P0-P3 与方案 A 的关系

方案 A（Supervisor ReAct）与四、五章的 P0-P3 改造是**独立、互补**的两条线：

| | P0-P3 改造 | 方案 A：Supervisor ReAct |
|---|---|---|
| 改什么 | Agent 内部的 LLM 使用质量 | Supervisor 的编排决策方式 |
| 解决的问题 | LLM 在排序/理由里的参与度太浅 | 编排流程缺乏动态决策能力 |
| 面试体现 | "LLM 真正理解课程语义来做判断" | "LLM 自主编排推荐流程" |
| 可以先做哪个 | P0 改动最小，先做 | A 需要 A/B 实验接口配合验证 |

**建议实施顺序：P0 → P1 → A → P2 → P3。** P0 最快见效果，A 最难但面试价值最大。
