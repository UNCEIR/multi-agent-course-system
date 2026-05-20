# 流式编排文档澄清与架构问答复盘

## 背景与问题

- 本轮要解决的问题：在 `docs/supervisor-main-orchestration.md` 工程细节版基础上，澄清用户阅读文档和链路时产生的多个架构疑问，避免把「精确缓存 / 语义缓存 / query 字段 / 硬过滤 / 可行性检查」混为一谈。
- 触发原因或用户诉求：
  1. 文档需聚焦流式链路工程细节，删除 STAR、LangChain 等面试包装内容（已在同日前序任务完成）。
  2. 追问「没有结构化条件时 prompt 进 payload」与「语义相同命中缓存」是否矛盾。
  3. 追问前端 `query` 字段何时为空、何时非空。
  4. 追问 `HardConstraintFilter` 与 `CourseFeasibilityAgent` 为何不合并为一个 Phase。
- 影响范围：本轮为文档理解与架构说明，未修改 Python 业务代码；新增本 note，并更新 `tasks/todo.md` 记录。

## 总体架构方案

- 涉及模块：
  - `python/orchestrator/supervisor.py`：流式 Phase 1～3 编排
  - `python/repositories/course_recall_cache_repository.py`：`RecallCacheKeyBuilder`、精确/语义 Redis 缓存
  - `python/agents/course_recall_agent.py`：召回顺序、`_score_candidates()` 打分
  - `python/orchestrator/hard_constraint_filter.py`：Phase 1.5 硬约束删除
  - `python/agents/course_feasibility_agent.py`：容量/软偏好 warning、时间冲突兜底
  - `frontend/src/components/StreamView.tsx`、`frontend/src/pages/RecommendPage.tsx`：请求体字段
- 数据流或调用链（流式主路径）：
  - HTTP `/api/v1/recommend/stream` → `stream_recommend()` → Phase 1（画像 ∥ 宽召回）→ 可选画像召回 → Phase 1.5 硬过滤 → Phase 2（重排 ∥ 可行性）→ Phase 3 流式理由 → `done`
- 关键设计取舍：
  - 同步与流式共用 Phase 1～2 业务逻辑，差异在 Phase 3 交付方式（一次性 JSON vs SSE token）。
  - 召回缓存分两层：精确 key 命中 vs 同 structured_signature 桶内 embedding 语义相似命中。
  - 硬约束必须在重排前删除；可行性检查与重排并行，且以 warning 为主而非硬删。

## 细节实现

### 1. 文档重构（同日前序）

- 修改文件：`docs/supervisor-main-orchestration.md`
- 删除：STAR 口播、LangChain/LangGraph 边界、自测清单、同步老接口输出原理。
- 补充：请求→prompt 转换、缓存 key、MySQL/Milvus 召回依据、`_score_candidates()` 加分表、硬过滤规则、重排规则分、marker parser、`done` 聚合等。

### 2. 「没有结构化条件」何时出现

- 定义：`RecallCacheKeyBuilder._build_payload()` 中 9 个字段（domains/categories/campus/exam/workload/grade_friendly/group_work/grade/major）全为空时，`payload["prompt"] = prompt[:80]` 参与精确 cache key。
- 典型场景：Phase 1 **宽召回**传 `student_profile=None`，且 `context` 未带上述结构化字段；用户仅发自然语言、无校区/专业等预填。
- 画像召回在画像成功后通常会有结构化字段，cache key 不再只靠 prompt 文本。
- 注意：`context.avoid_time_slots` **不参与** cache payload，只影响硬约束/可行性，不能算「有结构化条件」。

### 3. 精确缓存 vs 语义缓存（澄清「语义相同就命中」）

| 层级 | 判定 | 是否看语义相似 |
| --- | --- | --- |
| 精确缓存 | cache key 完全一致 | 否；无结构化条件时比 prompt 前 80 字 |
| 语义缓存 | 同 `structured_signature` 桶内，query embedding 余弦相似度 ≥ 阈值（默认 0.9） | 是 |

- 召回顺序：精确 → 语义 → MySQL/Milvus 真召回。
- 「两次 prompt 语义相近就命中」仅指**语义缓存**路径，且须同桶、开启语义缓存、过阈值；不是任意相似文本都命中精确缓存。

### 4. 前端 `query` 字段空/非空

- 后端解析顺序：`request.prompt or request.query or context["query"]`，再 `.strip()`。
- 当前前端（`StreamView`、`RecommendPage`）请求体只传 **`prompt`**，不传 **`query`**，故 `request.query` 默认为 `""`。
- `RecommendPage` 中局部变量名 `query = prompt.trim()` 写入的是 JSON 字段 **`prompt`**，不是 `query` 字段。
- 有效 query（用于 Milvus/语义缓存）非空：只要 prompt/query/context.query 任一有内容即可；现有前端靠 `prompt`。

### 5. HardConstraintFilter 与 CourseFeasibilityAgent 为何不合并

| 维度 | HardConstraintFilter (Phase 1.5) | CourseFeasibilityAgent (Phase 2) |
| --- | --- | --- |
| 职责 | 用户硬约束删除候选 | 容量/抢课 warning、软偏好提醒、时间兜底 |
| 对结果集 | 违反即删除，不进重排 | 容量满不删除，仅 warning；仅 `_hard_conflicts` 兜底删时间 |
| 时机 | **重排之前** | 与重排**并行** |
| 触发 | 仅 `has_active_constraints()` 为真 | 每次请求 |

- 合并到 Phase 2 会导致重排 LLM 在违规候选上排序，污染排序空间。
- 合并会损失 Phase 1.5 无硬约束时的早退，以及重排与可行性并行的耗时优势。
- Feasibility 中 `_hard_conflicts` 是画像未解析时的时间二次保险，不是主硬过滤重复实现。

## Debug 结论

- 根因：文档与口头说明中把「prompt 进 payload」「语义缓存」「query 字段」写在相近语境，读者易误以为三者等价；HardConstraint 与 Feasibility 表面都在「过滤」，但代码职责与 Phase 位置不同。
- 排查过程：对照 `RecallCacheKeyBuilder`、`CourseRecallAgent._execute()`、`_semantic_cached_courses()`、前端 `StreamView`/`RecommendPage` 请求体、`hard_constraint_filter.py` 与 `course_feasibility_agent.py` 注释及 Supervisor Phase 2 并行调用。
- 解决方式：通过问答澄清概念边界；主文档已改为工程细节版，本 note 沉淀易混点，便于后续读文档或面试排障时对照。

## 测试与验证

- 已执行：只读对照上述源码与 `docs/supervisor-main-orchestration.md`；同日前序任务已对主文档做 ReadLints，无 Markdown 诊断。
- 结果：本轮问答结论与当前代码行为一致；未发现在代码层面需要立即修复的 bug。
- 未执行及原因：未运行业务测试、Docker 或 pytest；本轮为文档理解与架构说明，无代码改动。

## 经验与后续

- 本轮经验：
  - 讲缓存时要拆成「精确 key 怎么算」和「语义相似怎么复用」两层，不要一句「语义相同就命中」带过。
  - 讲前端字段时要区分 JSON 里的 `query` 与局部变量名、以及实际使用的 `prompt`。
  - 讲过滤时要区分「硬删候选（Phase 1.5）」与「warning + 并行可行性（Phase 2）」，合并需说明顺序与并行代价。
- 后续建议：
  - 可在 `docs/supervisor-main-orchestration.md` 增加一小节「易混概念对照表」（精确 vs 语义缓存、query vs prompt、HardConstraint vs Feasibility）。
  - 若产品希望 API 统一，可考虑前端显式传 `query` 或文档标明「当前仅使用 prompt」。
