# 02 — 证据契约

> 每条强声明 → 具体代码位置 → 测试验证 → 面试风险 → 安全措辞。面试被追问时，从这里找证据。

## 契约格式

```text
声明：（一句话）
代码证据：（文件:行号 → 机制简述）
测试证据：（pytest 测试名 / Docker 验证 / 待补充）
面试风险：（追问可能 → 安全回答边界）
安全措辞：（可写入简历的措辞）
```

---

## 契约 1：Multi-Agent 双模式编排

**声明**：系统支持固定 Pipeline 和 ReAct 工具调用两种编排模式，通过 A/B 实验分流。

**代码证据**：
- `python/orchestrator/supervisor.py:83-280` → `recommend()` 固定 Pipeline 路径（Phase 1→1.5→1.75→2→3）
- `python/orchestrator/supervisor.py:823-892` → `_react_recommend()` ReAct 工具调用循环
- `python/orchestrator/supervisor.py:98-104` → `ab_engine.assign()` 读取分组决定走哪条路径
- `python/orchestrator/react_tools.py:1-200` → 7 个 ReAct 工具定义

**测试证据**：
- `tests/test_supervisor_orchestration.py`（如存在）→ 全链路编排测试
- 待补充：ReAct 模式端到端测试

**面试风险**：
- 追问："ReAct 和 LangGraph 的 AgentExecutor 有什么区别？"
- 安全回答：当前是自建轻量 ReAct 循环（20 轮上限 + 强制硬约束），没有用 LangGraph。如果需要多 Agent 间协商或条件分支，可以考虑迁移到 LangGraph。
- 追问："为什么不用 LangChain 的 Agent？"
- 安全回答：为了更精确控制硬约束锁死和 fallback 行为。

**安全措辞**：
> 实现 Supervisor Pipeline 与 ReAct 工具调用双模式编排；ReAct 模式下硬约束过滤工具锁死不可跳过，循环结束后编排器强制执行。

---

## 契约 2：硬约束确定性过滤

**声明**：校区、考试偏好等硬约束用纯规则过滤，在 LLM 参与排序之前完成，违规课程不会进入重排。

**代码证据**：
- `python/orchestrator/hard_constraint_filter.py:1-228` → 完整 HardConstraintFilter 实现
- `python/orchestrator/hard_constraint_filter.py:201` → `_fuzzy_text_match()` 类别子串匹配
- `python/agents/student_profile_agent.py:143-180` → 自然语言→硬约束提取规则
- `python/agents/student_profile_agent.py:190` → `category_rules` 别名映射
- `python/orchestrator/supervisor.py` → Phase 1.5 在 Phase 2（重排）之前执行

**测试证据**：
- `tests/test_hard_constraint_prompt_fallback.py` → 硬约束 fallback 测试
- 待补充：类别模糊匹配边界测试（"理工" vs "自然科学与工程技术"）

**面试风险**：
- 追问："如果用户说'东校区或者西校区都可以'你怎么处理？"
- 安全回答：当前画像提取会将多校区写成自然语言约束，硬约束过滤按"提及即触发"逻辑匹配。OR 逻辑需要增强 Prompt 引导。
- 追问："类别匹配的准确率是多少？"
- 安全回答：当前是纯子串匹配，像"理工"不匹配"自然科学与工程技术"。已在 CLAUDE.md 记录为已知局限，需要通过别名映射修复。

**安全措辞**：
> 在召回后插入 Phase 1.5 确定性硬约束过滤：校区、类别、考试偏好用纯规则移除违规课程，重排器不会看到它们。过滤后候选不足时返回警告，不悄悄放宽约束。

---

## 契约 3：Embedding 冗余调用消除

**声明**：将召回阶段的 query embedding 调用从 3 次降为 1 次，入口计算后复用给三个消费者。

**代码证据**：
- `python/agents/course_recall_agent.py:38` → `query_embedding` 在 `_execute()` 入口计算一次
- `python/agents/course_recall_agent.py:291-344` → 消费者 1：`_semantic_cached_courses()` Redis 语义缓存探测
- `python/agents/course_recall_agent.py:377-402` → 消费者 2：`_semantic_course_ids()` Milvus ANN 搜索
- `python/agents/course_recall_agent.py:346-375` → 消费者 3：`_index_semantic_cache()` Redis 语义缓存索引写入

**测试证据**：
- 待补充：日志验证同一请求只调用一次 Embedding API

**面试风险**：
- 追问："为什么一开始会有 3 次调用？"
- 安全回答：原始设计中三个子方法各自独立调用 Embedding API，重构时将公共计算上提到入口处。这是一个典型的 DRY + 性能优化。
- 追问："节省了多少延迟？"
- 安全回答：没有精确测量，但 Embedding API 调用通常是召回路径中最慢的环节，减少 2/3 调用量理论上减少约 2/3 的 Embedding 延迟。

**安全措辞**：
> 消除召回路径 Embedding 冗余调用：统一在入口计算 query 向量后传递给 Redis 语义缓存、Milvus ANN 搜索、缓存索引写入三个消费者（3 次降 1 次）。

---

## 契约 4：评分职责分离

**声明**：召回阶段评分仅用关键词匹配+热度（有意不使用 profile），重排阶段评分融合 profile 偏好+Milvus COSINE 距离。

**代码证据**：
- `python/agents/course_recall_agent.py:404-428` → `_score_candidates()` 仅用关键词匹配+热度，接受但不使用 `profile` 参数
- `python/agents/course_rerank_agent.py:165-192` → `_compute_score()` 融合 profile 偏好+Milvus COSINE
- `CLAUDE.md:关键设计决策 #1` → 明确标注此设计是有意为之，不是 bug

**测试证据**：
- 待补充：对比实验验证职责分离对最终推荐质量的影响

**面试风险**：
- 追问："召回阶段为什么不用 profile？这不是浪费了画像信息吗？"
- 安全回答：召回阶段目标是保广度，不提前收缩候选集。profile 偏好信号留给重排阶段做精细排序。如果召回阶段就用 profile 过滤，可能漏掉"关键词不匹配但语义相关"的课程。
- 追问："你怎么证明这种分离比直接用 profile 召回更好？"
- 安全回答：当前没有定量 A/B 结果，但从设计逻辑上，分离让两个阶段的失败模式独立——召回失败（缓存/Milvus 都不可用）不影响重排兜底。

**安全措辞**：
> 实现召回-重排评分职责分离：召回阶段保留关键词匹配+热度（有意不引入画像偏好），重排阶段用 `_compute_score()` 融合 profile 偏好与 Milvus COSINE 距离（`final = profile_score × (1 + sim × 0.5)`）。

---

## 契约 5：Redis 语义缓存

**声明**：Redis 缓存支持精确 key 和语义近邻两种命中模式，语义缓存在同结构化签名 bucket 内按 cosine ≥ 0.95 匹配。

**代码证据**：
- `python/repositories/course_recall_cache_repository.py:1-271` → 完整缓存实现
- `python/repositories/course_recall_cache_repository.py:234` → `setnx` 分布式锁防击穿
- `python/agents/course_recall_agent.py:291-344` → `_semantic_cached_courses()` 语义缓存探测逻辑
- `CLAUDE.md:常见陷阱` → 语义缓存阈值 0.95（从 0.9 提高）的修复记录

**测试证据**：
- 待补充：缓存命中/未命中场景的单元测试

**面试风险**：
- 追问："语义缓存会不会错误复用不相关的查询结果？"
- 安全回答：有这个风险。历史上阈值 0.9 时"我对计算机感兴趣"命中了"心理学"缓存（1024 维向量对句式模板区分度不足），已提高到 0.95。另外缓存只存候选 ID，最终仍经过 MySQL 回表+硬约束过滤，即使错误命中也不会绕过安全检查。
- 追问："为什么不用向量数据库直接做语义缓存？"
- 安全回答：Redis 延迟更低（<1ms），语义缓存的 bucket 机制通过结构化签名做了粗筛，同 bucket 内做余弦相似度比较，不需要全量向量检索。

**安全措辞**：
> 设计 Redis 召回缓存：精确 key（SHA256）+ 语义近邻（同结构化签名 bucket 内 cosine ≥ 0.95）+ 分布式短锁防击穿；缓存仅存候选 ID，命中后回 MySQL 保证事实最新。

---

## 契约 6：流式 SSE + Token 级标记解析

**声明**：SSE 流式推荐通过状态机解析 LLM 输出的 `[COURSE:id:name]` 标记，将 token 流按课程拆分。

**代码证据**：
- `python/orchestrator/supervisor.py:282-535` → `stream_recommend()` SSE 流式编排
- `python/services/stream_token_markup_parser.py:1-101` → `StreamTokenMarkupParser` 状态机
- `python/orchestrator/supervisor.py` → `stream_timeout_seconds=60` Phase 3 独立超时

**测试证据**：
- 待补充：SSE 流式端到端测试

**面试风险**：
- 追问："为什么用自定义标记而不是 JSON 结构化输出？"
- 安全回答：LLM 流式输出时 JSON 需要完整接收后才能解析，标记方案可以在收到增量 token 时实时判断归属，实现真正的流式效果。
- 追问："如果 LLM 输出格式错误（标记不闭合）怎么办？"
- 安全回答：状态机会在超时或流结束时强制关闭未闭合的课程块，未闭合的内容归属到上一门课或丢弃。

**安全措辞**：
> 基于 FastAPI SSE 实现流式推荐：Phase 3 理由 token 通过 marker 状态机（`StreamTokenMarkupParser`）实时归属到课程，Phase 3 独立超时保护（60s）。

---

## 契约 7：Agent 基类 + 降级链

**声明**：所有 Agent 继承 BaseAgent，模板方法模式统一处理重试、计时和降级。

**代码证据**：
- `python/agents/base_agent.py:1-75` → BaseAgent 实现
- `python/agents/student_profile_agent.py` → 继承 BaseAgent
- `python/agents/course_recall_agent.py` → 继承 BaseAgent
- `python/agents/course_rerank_agent.py` → 继承 BaseAgent
- `python/agents/course_feasibility_agent.py` → 继承 BaseAgent
- `python/agents/recommendation_reason_agent.py` → 继承 BaseAgent

**测试证据**：
- `tests/test_base_agent.py`（如存在）→ Agent 基类单元测试
- 39 个单测全部通过 → 整体测试覆盖

**面试风险**：
- 追问："tenacity 重试和 fallback 的区别是什么？"
- 安全回答：retry 是瞬时错误（网络抖动、API 限流）的透明恢复；fallback 是重试耗尽后的降级路径（画像提取失败→启发式规则、重排失败→纯规则评分）。

**安全措辞**：
> 封装 Agent 基类统一处理耗时记录、指数退避重试（tenacity）和 fallback 降级；每个 Agent 独立失败返回降级结果，不阻断整条链路。

---

## 契约 8：Docker 容器化部署

**声明**：项目支持 Docker Compose 一键部署（API + MySQL + Redis + Milvus）。

**代码证据**：
- `docker-compose.python.yml` → 4 个服务定义
- `python/Dockerfile` → Python API 镜像
- `.env` + `python/.env` → 双层配置加载

**测试证据**：
- Docker E2E 接口验证通过（`docs/resume-template.md` 确认）
- `curl` 测试 payload：`python/scripts/curl_recommend_payload.json`
- 待补充：当前环境 Docker 服务状态确认

**面试风险**：
- 追问："MySQL 端口为什么是 3307？"
- 安全回答：避免与宿主机已有 MySQL 3306 端口冲突。Docker 内部容器间通信仍用标准 3306。
- 追问："为什么不直接用 docker-compose.yml？"
- 安全回答：仓库根目录的旧 `docker-compose.yml` 是电商系统前身用的，公选课系统用 `docker-compose.python.yml --profile python`。CLAUDE.md 有明确说明。

**安全措辞**：
> Docker Compose 一键部署（FastAPI + MySQL + Milvus + Redis），支持 `--profile python` 按需启动服务。

---

## 契约 9：Thompson Sampling A/B 测试

**声明**：基于 Thompson Sampling 实现动态流量分配，一致性哈希保证同用户同组。

**代码证据**：
- `python/services/ab_test.py:1-185` → 完整 A/B 引擎实现
- `python/services/ab_test.py:48` → 实验注册
- `python/orchestrator/supervisor.py:98-104` → 路由逻辑

**测试证据**：
- 待补充：A/B 分流正确性的单元测试

**面试风险**：
- 追问："为什么用 Thompson Sampling 而不是固定比例分流？"
- 安全回答：Thompson Sampling 可以在实验进行中动态调整流量——表现好的分组自动获得更多流量，减少 regret。但当前实验样本量不足以体现这个优势，代码能力大于实际收益。
- 追问："有多少实验样本？"
- 安全回答：当前是个人项目，没有真实流量。Thompson Sampling 的实现是工程能力的展示，不是生产优化依据。

**安全措辞**：
> 实现 Thompson Sampling A/B 实验引擎：一致性哈希分桶 + Beta 分布动态采样 + 多层实验并行；注册 3 个实验，支持指标收集和聚合统计。

---

## 综合风险矩阵

| 风险等级 | 触发条件 | 应对 |
| --- | --- | --- |
| 🔴 高风险 | 被问到真实用户指标、CTR、延迟 P99、并发量 | 直接说"当前是个人项目，没有真实用户数据。这些指标需要上线后才能收集。" |
| 🟡 中风险 | 被问到 ReAct 是否真的在生产运行 | 说"ReAct 模式代码已实现，A/B 实验已注册但尚未激活。Pipeline 模式是当前默认路径。" |
| 🟡 中风险 | 被追问答对准确率、缓存命中率 | 说"没有标注测试集或真实流量统计，目前只有功能验证（39 单测 + Docker E2E）。" |
| 🟢 低风险 | 被问到代码设计细节 | 代码文件+行号+设计意图可以完整回答。CLAUDE.md 有设计决策记录。 |
