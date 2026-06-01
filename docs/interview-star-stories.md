# 面试 STAR 故事库

<!-- markdownlint-disable MD024 -->

本文档按面试价值排序组织 8 个项目故事。每个故事按 STAR 结构组织，包含口播版和展开版，避免"报菜名"。真实未知的业务指标统一标为"待补充"。

---

## 故事一：ReAct 编排 vs 固定 Pipeline——A/B 双模式设计

### 一句话

让 LLM 不只做生成，还做编排决策——在推荐不足或全爆满时可以回头重试。

### S 情境

固定 Pipeline（Phase 1→1.5→2→3）流程确定、延迟可控，但遇到异常情况（召回不足、硬过滤后课程太少、推荐的课全爆满）无法回头调整。推荐场景的依赖关系是天然的（必须先画像→才能召回→才能过滤→才能排序），LLM 再聪明也不能乱序执行。

### T 任务

在保留 Pipeline 稳定性的同时，增加一种动态编排模式，让 LLM 能在异常时自主决定回头放宽条件重试。

### A 行动

- 新增 `orchestrator/react_tools.py`，把 5 个 Agent + 硬约束过滤 + 语义初筛包装成 7 个工具
- 硬约束过滤工具锁死不可跳过——编排器在循环结束时检测 `ReactState.hard_filtered`，为 False 则强制补调
- Supervisor 通过 A/B 实验分组决定走 Pipeline 还是 ReAct（`ab_test.py` 分流）
- 正常请求 ReAct 走直线（等价于 Pipeline），异常时才触发额外轮次
- ReAct 最多 10 轮工具调用，防止无限循环

### R 结果

- 代码已实现，39/39 单测通过
- ReAct 模式 A/B 实验尚未注册 "react" group（需手动在 `ab_test.py:48` 添加）
- 正常路径 token 增量为 0，异常路径 +1-2 轮（约 200-500 token）

### 60 秒口播

我在项目里实现了两种编排模式。固定 Pipeline 按 Phase 1 到 Phase 3 顺序执行，延迟可控，适合大部分请求。但有个问题：如果召回只找到 3 门课，或者硬过滤后课程太少，Pipeline 只能照样往下走，没办法回头放宽条件。所以我又做了 ReAct 模式，把 5 个 Agent 和硬约束过滤包装成 7 个工具，让 LLM 根据中间结果决定下一步。比如召回不足时 LLM 会自己再调一次宽召回。关键是硬约束工具锁死不可跳过——校区和考试要求不能让 LLM 商量。两种模式通过 A/B 实验分流，正常请求走 Pipeline，可以按需开启 ReAct 对比。

### 3 分钟展开版

固定 Pipeline 我分了四个阶段：Phase 1 画像和召回并发执行，Phase 1.5 硬约束过滤，Phase 2 重排和可行性分析并发，Phase 3 串行生成推荐理由。这个链路覆盖 80% 以上的正常请求没问题，但异常情况——比如用户指定了很窄的条件导致硬过滤后只剩 2 门课，或者推荐的课全爆满——Pipeline 只会把 2 门课原样返回，不会回头放宽条件重新召回。

为了解决这个问题，我做了 ReAct 模式。核心思路是把每个 Agent 和过滤步骤注册成 LLM 可调用的工具。`orchestrator/react_tools.py` 定义了 7 个工具：`build_profile`、`wide_recall`、`refined_recall`、`hard_filter`、`semantic_filter`、`rerank`、`feasibility_check`。LLM 通过 `bind_tools` 拿到工具列表，每轮根据上一步结果决定下一步调什么。

设计上有几个关键约束。第一，硬约束过滤不可跳过：我在 `ReactState` 里维护了 `hard_filtered` 标志，编排器循环结束时检测这个标志，如果 LLM 跳过了硬过滤，编排器会强制补调。第二，最多 10 轮工具调用，超过直接返回当前最优结果。第三，system prompt 里约束了工具的推荐调用顺序，但允许 LLM 在异常时偏离——比如 `hard_filter` 后候选太少，LLM 可以决定降低条件重新 `wide_recall`。

两种模式通过 `services/ab_test.py` 分流。目前 A/B 实验只注册了 "control" group（固定 Pipeline），"react" group 需要手动添加才能生效。这是有意为之——ReAct 模式的 token 成本不确定，需要在灰度环境先观察再放量。

### 可追问点

- 为什么不只用 ReAct？（延迟不可控，token 成本随轮次增长）
- 硬约束工具怎么"锁死"？（编排器循环结束检测 hard_filtered 标志，强制补调）
- ReAct 模式的 token 成本？（正常路径 +0，异常 +200-500）
- 7 个工具的执行顺序怎么保证？（system prompt 约束 + 依赖关系天然限制）

---

## 故事二：用规则保下限、用 LLM 提上限——硬约束从软打分中独立

### 一句话

用户说"只要西校区"时不能只靠排序分数，必须有确定性过滤门槛。

### S 情境

原先所有偏好（包括校区、不考试）都混在排序分数里。排序分数只能影响顺序，不能保证违规课程不出现——用户明确说"只要西校区"时，如果东校区某门课其他维度分高，仍然会被推荐。

### T 任务

把"必须满足"的硬约束从 LLM 排序和软偏好里独立出来。同时处理类别名称不匹配的问题（学生说"理工类"，数据库里是"自然科学与工程技术类"）。

### A 行动

- 在 Supervisor 中插入 Phase 1.5 `HardConstraintFilter`，在重排前做确定性过滤
- 硬约束检查：校区精确匹配、类别/领域模糊匹配、教师子串、不考试、不小组、避开时段、难度/作业量有序比较
- 画像 Agent 提取硬约束时补充了 `_extract_prompt_hard_constraints` 正则规则：校区关键词、类别别名映射（"理工"→"自然科学与工程技术"）、不考试
- 修复了类别模糊匹配：原来纯子串匹配"理工"不在"自然科学与工程技术"中；新增 category_rules 别名映射表
- 过滤后课程不够时返回 warning，不偷偷放宽

### R 结果

- 相关单测和 Docker 验证：指定"西校区 + 自然科学类"时最终课程均满足约束
- 39/39 单测通过（含硬约束 prompt fallback 测试）
- 遗憾：类别别名映射仍是静态表，不支持动态扩展

### 60 秒口播

我后来发现一个问题：如果把所有偏好都交给排序分数，用户明确说"只要西校区"时，系统仍可能因为别的分数推荐东校区的课。这类需求不应该只是软分数，所以我在 Phase 1 和 Phase 2 之间加了硬约束过滤。画像 Agent 提取出校区、类别、不考试等硬约束，过滤器先把不符合的课程挡掉，再让 LLM 在剩余候选里排序。过程中还碰到一个坑：学生说"理工类"，数据库里叫"自然科学与工程技术类"，纯子串匹配不上。我加了一个别名映射表解决。如果过滤后课程不够，我返回 warning，不自动放宽条件。

### 3 分钟展开版

问题的根源是：排序分数是连续值，无法表达"绝对不行"。校区精确匹配、不考试、不做小组作业——这些需求用户用的是"只要""不要"这类绝对语气，如果只在排序分里给个 +5 / -5，当另一个维度打分很高时，违规课程仍然可能挤进 Top N。

我在 Supervisor 中 Phase 1（召回）和 Phase 2（重排）之间插入了 Phase 1.5 `HardConstraintFilter`。它是纯规则组件，不调 LLM。每条硬约束有对应的检查函数：校区用精确匹配；类别和领域用模糊匹配（去掉"类"字后子串比较）；教师用子串；"不考试""不小组"检查布尔字段；避开时段做交集判断；难度和作业量做有序比较。

类别匹配有个坑：画像 Agent 从用户 prompt 里提取出"理工类"，过滤器拿去和数据库的"自然科学与工程技术类"比较。原来的 `_fuzzy_text_match` 做的是去掉"类"字后的纯子串匹配——"理工" in "自然科学与工程技术" 返回 False。我在两处做了修复：`student_profile_agent.py` 的 `_extract_prompt_hard_constraints` 方法里加了 category_rules 别名映射（"理工"→"自然科学与工程技术"），`hard_constraint_filter.py` 的 `_fuzzy_text_match` 也加了别名查找。

过滤后如果课程数量少于请求数量，系统返回 `hard_constraint_sparse` warning 和实际可用课程，不会偷偷放宽条件。这是有意设计——用户说"只要西校区"，那就只给西校区的课，哪怕只有 3 门。

### 可追问点

- 哪些算硬约束，哪些算软偏好？
- 过滤后没有课程怎么办？
- 为什么不让 LLM 自己判断硬约束？（概率性判断不适合确定性需求）
- 类别别名映射怎么维护？

---

## 故事三：MySQL + Milvus + Redis 三层召回与评分职责分离

### 一句话

把召回的"广度"和重排的"精度"拆开，让 Milvus 的向量距离真正参与排序。

### S 情境

原来召回阶段的 `_score_candidates()` 和重排阶段都在做 profile 匹配（domain/category/campus/workload 等），评分逻辑重复。Milvus 返回的 COSINE 距离被完全丢弃——只用来决定召不召回，不参与排序。

### T 任务

消除召回和重排之间的评分重复，让 Milvus 的向量相似度真正参与最终排序。

### A 行动

- 召回 `_score_candidates()` 移除所有 profile 匹配逻辑，只保留 query 关键词匹配 (+1.5/term) 和热度 (+0.8)
- 语义召回课程的初始分从 Milvus COSINE 距离初始化：`max(0.0, 1.0 - distance)`
- 重排新增 `_compute_score()`：profile_score 汇总所有偏好匹配分；最终公式 `final = profile_score * (1.0 + milvus_sim * 0.5)`
- Milvus 相似度作为加权乘法放大器——向量命中的课程 profile 分会被放大最多 50%

### R 结果

- 消除了两阶段评分重复
- 39/39 单测通过
- 遗憾：乘法放大器的系数 0.5 目前是经验值，没有基于大量真实 query 调参

### 60 秒口播

原来召回和重排都在做 profile 匹配——domain 加分、category 加分、campus 加分，两边逻辑重复。而且 Milvus 返回的余弦距离被完全丢掉了，只决定"召不召回"，不影响排序。所以我做了一次拆分：召回阶段只保留关键词匹配和热度，负责广度；重排阶段用新的 `_compute_score` 做完整的 profile 匹配，并且把 Milvus 的 COSINE 距离融进去。具体公式是 profile 分乘以 `(1 + 向量相似度 * 0.5)`，也就是向量命中的课程 profile 分会被放大最多 50%。这样 Milvus 不只是召回工具，它的语义信号也参与了最终排序。

### 3 分钟展开版

问题分两层。第一层是评分职责重叠：召回阶段 `_score_candidates()` 在做 domain 匹配加分、category 匹配加分、campus 匹配加分、workload 匹配加分；重排阶段的 LLM prompt 和 `_compute_score()` 又在做同样的事情。两套评分标准不统一，后续维护改一边忘另一边就会出不一致。

第二层是 Milvus 信号被浪费。Milvus 返回 `(chunk_id, distance)` 对，distance 是 COSINE 距离（越小越相似）。原来只用它做召回门控——distance < threshold 才召回，但具体值完全丢弃。这意味着 Milvus 认为相似度 0.1 和 0.4 的两门课在排序阶段被同等对待。

拆分方案：召回阶段 `_score_candidates()` 只保留两件事——query 文本中每个关键词在课程 name/description 里命中的加分（+1.5/term），和热度加分（+0.8）。语义召回的课程初始分从 Milvus 距离初始化为 `max(0.0, 1.0 - distance)`，而不是统一给固定分。

重排阶段新增 `_compute_score(course, profile, milvus_sim)`：先算 profile_score（domain/category/campus/workload/difficulty 各维度匹配加分），然后用公式 `final = profile_score * (1.0 + milvus_sim * 0.5)`。这是乘法融合而非加法——向量相似度作为放大器，让 profile 分高且向量也高的课程更突出。选乘法的原因是：如果用加法，向量高但 profile 完全不匹配的课程也会获得额外分数；乘法保证 profile_score 为 0 时无论向量多高最终分仍为 0。

系数 0.5 是经验值。意思是向量完全命中时 profile 分最多放大 50%。这个值没有经过大量真实 query 调参，是一个遗憾点。

### 可追问点

- 为什么用乘法而不是加法融合 Milvus 分？（乘法让向量高分和 profile 高分同时满足的课程更突出）
- 系数 0.5 怎么选的？
- 召回不做 profile 匹配会不会漏课？（宽召回不带 profile，精召回带 profile MySQL WHERE，两次合并保证广度）

---

## 故事四：语义缓存误命中修复——1152 维向量句式模板区分度不足

### 一句话

缓存命中推荐了心理学课程给对计算机感兴趣的学生——问题出在向量的句式敏感性。

### S 情境

我做了语义缓存，让语义相近的 prompt 复用召回结果。但上线后发现推荐结果和用户意图不匹配。排查发现不是精确缓存碰撞，而是语义缓存误命中：

- "我对计算机感兴趣"和"我对心理学感兴趣"的余弦相似度 ~0.94
- 原始阈值 0.9 被轻松超过
- 8 个字中 7 个相同，只差一个关键词

### T 任务

修复语义缓存误命中，同时保留相同 prompt 的精确缓存收益。

### A 行动

- 语义缓存阈值从 0.9 提高到 0.95：宁可降低命中率也不给错误结果
- `_build_payload()` 始终将 prompt 纳入 cache key（删除 `if not any(payload.values())` 条件）：即使有结构化字段也不跳过 prompt，避免结构化条件相同但 prompt 意图不同时误命中
- 在同一 `structured_signature` 桶内比较，确保结构化条件（校区/考试/作业量）相同时才做语义比较

### R 结果

- 相同 prompt 仍精确命中
- 句式相似但关键词不同的 query 大概率 < 0.95 而走全量召回
- 遗憾：0.95 是经验阈值，理想方案是结合关键词差异做混合判断

### 60 秒口播

我做了语义缓存，让相近措辞的请求复用召回结果。但后来发现一个问题："我对计算机感兴趣"命中了"我对心理学感兴趣"的缓存。排查发现原因是 1152 维向量对这种句式模板的区分度不够——两句话 8 个字中 7 个相同，只差一个关键词，余弦相似度达到 0.94，超过了我设的 0.9 阈值。修复很直接：阈值从 0.9 提到 0.95，宁可少命中不给错误结果。同时把 prompt 始终纳入 cache key，不再只依赖结构化字段。效果是相同 prompt 仍然命中，但关键词不同的请求会走全量召回。

### 3 分钟展开版

问题的表现是：一个学生说"我对计算机感兴趣"，系统推荐了心理学课程。排查路径：先检查 MySQL 课程数据没问题，再看 Milvus 向量检索结果也没问题，最后发现召回阶段根本没走 Milvus——命中了 Redis 语义缓存。

语义缓存的工作原理是：把用户 prompt embedding 后和历史缓存的 embedding 做余弦相似度比较，超过阈值就认为是"相同意图"，直接返回历史缓存的候选 course_id 列表。问题出在阈值设置：0.9 看起来很高，但 1152 维向量对短句式模板的区分度不够。"我对计算机感兴趣"和"我对心理学感兴趣"只差一个关键词，其余字完全相同，余弦相似度达到 ~0.94。

修复三步。第一，阈值从 0.9 提到 0.95。这会降低语义缓存命中率，但宁可多调一次 embedding API 也不给错误结果。第二，`_build_payload()` 始终将 prompt 文本纳入 cache key 的计算。原来有个优化：如果已经有结构化字段（校区、考试等），就跳过 prompt。但这会导致两个不同意图但结构化条件相同的请求共享缓存。第三，语义比较限定在同一 `structured_signature` 桶内——只有结构化条件完全一致时才做向量相似度比较。

这个问题让我意识到 embedding 模型的语义粒度和业务需要的区分度之间有 gap。理想方案不是只调阈值，而是结合关键词提取做双重判断：先提取 prompt 中的核心关键词（"计算机" vs "心理学"），关键词不同直接判为不同意图，关键词相同再做向量比较。这个方案没有实现，是一个遗憾。

### 可追问点

- 阈值为什么选 0.95 而不是更高？（更高会让合理复用也失效）
- 还有什么更好的方案？（关键词提取 + 向量双重判断）
- 语义缓存的 ROI？（减少 embedding API 调用和 Milvus 检索）

---

## 故事五：LLM 语义初筛替代规则预筛

### 一句话

让 LLM 看课程摘要挑出真正相关的 40 门，而不是只靠字段匹配缩候选。

### S 情境

硬约束过滤后可能还剩 100-150 门课，但重排 LLM 只能处理约 40 门。原来用规则公式打分从候选中取 Top 40：domain/category 匹配加分。规则只能匹配字段，无法理解课程实际内容——比如课程名"Python 入门"但大纲全是爬虫，跟学生说的"数据分析"不对口。

### T 任务

在规则预筛和 LLM 重排之间插入一层语义理解，让候选集更精准。

### A 行动

- 在 Supervisor 中新增 Phase 1.75 `_llm_semantic_filter`
- 触发条件：候选 >40 且有画像
- 每门课拼一行摘要（name/domain/category/campus/description[:80]/tags[:5]/difficulty/has_exam/popularity）
- LLM temperature=0, max_tokens=2048，返回 course_id JSON 数组
- 失败返回空列表，保留原候选——`_compute_score` 规则预筛作为兜底
- LangGraph 版本中也同步实现了 `semantic_filter_node`

### R 结果

- 39/39 单测通过
- API 验证中 LLM 语义初筛正常执行
- 遗憾：单次 LLM 调用处理 ~150 门课的 token 成本中等，如果候选更多可能需要分批

### 60 秒口播

硬约束过滤后通常还剩一两百门课，但重排 LLM 只能看 40 门。原来我用规则公式取 Top 40——domain 匹配加分、category 匹配加分。但规则只能匹配字段，不能理解课程内容。比如一门"Python 入门"课，大纲全是爬虫，跟学生说的"想学数据分析"其实不对口，规则看不出来。所以我在 Phase 1.5 硬约束后插入了 Phase 1.75，让 LLM 看每门课的一行摘要和学生画像，挑出真正语义相关的 40 门。失败时保留原候选，不会比不做更差。

### 3 分钟展开版

问题本质是信息损失：规则预筛只看 domain、category 这些离散字段，但课程的"适不适合这个学生"其实藏在 description、tags、先修要求这些文本里。举个例子：一门课叫"Python 入门"，domain 是"计算机"，category 是"自然科学与工程技术类"。学生说"想学数据分析"，规则预筛会给这门课加分（domain 匹配）。但如果看 description，全是爬虫和网络编程，跟数据分析不对口。

Phase 1.75 `_llm_semantic_filter` 的做法是：给 LLM 一段 system prompt 说明任务，然后把学生画像和每门课的一行摘要发过去。摘要包含 name、domain、category、campus、description 前 80 字、tags 前 5 个、difficulty、has_exam、popularity。LLM 返回一个 course_id 的 JSON 数组，表示它认为和学生画像最相关的课程。

设计上有几个关键决定。第一，触发条件是候选 >40 且有画像。如果候选本来就 ≤40，不需要筛；如果没有画像，LLM 没有依据做筛选。第二，LLM 返回空列表或调用失败时，保留原候选走 `_compute_score` 规则预筛。这意味着 Phase 1.75 是"只能变好不会变差"的增强——最坏情况退化为不做。第三，temperature=0 保证结果稳定，max_tokens=2048 足够返回 40 个 course_id。

在 LangGraph 版本中，我也同步实现了 `semantic_filter_node`，保证两种编排模式的 Phase 1.75 行为一致。

### 可追问点

- Phase 1.75 失败为什么不中断链路？
- 和 Phase 1.5 硬约束为什么不合并？（一个是确定性过滤，一个是语义理解）
- Token 成本怎么控制？

---

## 故事六：流式推荐 SSE + marker parser 状态机

### 一句话

让长链路推荐过程实时可见，推荐理由逐字输出并自动归属到课程。

### S 情境

推荐链路包含画像、召回、过滤、重排、理由生成等阶段，同步接口等到最后才有结果。前端或演示时无法看到中间进度。理由 token 是连续字符串，需要结构化地归属到每门课程。

### T 任务

让流式接口把阶段进度和理由 token 稳定输出。理由 token 自动归属到对应课程。

### A 行动

- SSE 事件序列：`start → phase1_complete → phase15_complete → phase2_complete → phase3_start → token流 → phase3_complete → done`
- Phase 3 理由生成用 marker 协议：模型输出 `[COURSE:id:name]` 标记分隔不同课程
- 实现 `StreamTokenMarkupParser` 双状态机（idle/buffering）：
  - idle 状态正常透传文本
  - 遇到 `[` 进入 buffering，收集到 `]` 后尝试 marker 正则匹配
  - 匹配成功发 `course_start`，失败把 buffer 当普通文本输出
  - MAX_BUFFER=256 防止异常输出无限缓存
- Phase 3 超时从 token 流开始算，不从请求入口算——避免前置阶段耗时挤占理由生成预算
- 路由别名统一：`/api/v1/recommend/stream` 和 `/api/v1/stream_recommend` 走同一套实现

### R 结果

- `test_stream_recommend.py` 5 passed
- Docker 验证 SSE 事件完整输出
- 遗憾：当前流式主要服务展示，不等于全链路异步任务系统

### 60 秒口播

流式接口主要解决两个问题。第一个是阶段可见性：推荐链路阶段多，同步接口等到最后才出结果。我用 SSE 把每个 Phase 的完成状态推给前端，学生能看到"正在召回""正在过滤""正在生成理由"。第二个是理由归属：理由 token 是连续字符串，需要知道哪段属于哪门课。我设计了 marker 协议，模型在每门课理由前输出 `[COURSE:id:name]` 标记，parser 用状态机解析出 course_start 和 course_end 事件。另外 Phase 3 超时从 token 流开始算，不从请求入口算，避免前置阶段慢了一进入理由生成就超时。

### 3 分钟展开版

SSE 事件设计分两层。外层是阶段事件：`start`（推荐开始）、`phase1_complete`（画像+召回完成）、`phase15_complete`（硬约束过滤完成）、`phase2_complete`（重排+可行性完成）、`phase3_start`（开始生成理由）、`phase3_complete`（理由生成完成）、`done`（全部完成）。每个阶段事件带 payload，前端可以据此更新进度条。

内层是 Phase 3 的 token 流。推荐理由 LLM 按课程依次输出，每门课的理由前面有一个 marker：`[COURSE:course_id:course_name]`。我写了 `StreamTokenMarkupParser`，它是一个双状态状态机。idle 状态下，token 正常透传给前端。当遇到 `[` 字符时进入 buffering 状态，开始收集字符。收集到 `]` 后，用正则尝试匹配 `[COURSE:(\d+):(.+)]` 格式。匹配成功则发出 `course_start` 事件（携带 course_id 和 name），后续 token 归属这门课；匹配失败则把 buffer 内容当普通文本输出。MAX_BUFFER=256 是防御措施——如果模型输出了 `[` 但迟迟不输出 `]`，buffer 超限后强制清空并回到 idle。

超时设计有个细节：Phase 3 的超时计时器从第一个 token 到达时开始，不从请求入口开始。原因是前面四个 Phase 可能因为 LLM 调用、Milvus 检索等原因耗时不稳定。如果从入口开始算 30 秒超时，前面用了 25 秒，Phase 3 只剩 5 秒——理由还没生成完就超时了。从 token 流开始算，Phase 3 有完整的超时预算。

路由别名是历史遗留问题：旧脚本用 `/api/v1/stream_recommend`，代码注册的是 `/api/v1/recommend/stream`。我让两个路径走同一个 handler，不会 404。

### 可追问点

- SSE 和同步接口共用了哪些逻辑？
- marker 格式为什么这样设计？
- buffer 超限怎么处理？
- Phase 1.5 事件对用户有什么价值？

---

## 故事七：召回 embedding 从 3 次降为 1 次

### 一句话

同一个 query 在缓存未命中时被 embedding 了三次，统一到入口一次解决。

### S 情境

完整缓存未命中路径中，同一个 query 文本被 embedding 最多 3 次：

1. 语义缓存探测（比较历史 embedding 的相似度）
2. Milvus 向量检索（`search()` 内部调用）
3. 缓存索引写入（保存新的 embedding 供后续语义比较）

### T 任务

消除冗余 API 调用，在不引入外部缓存层的前提下解决。

### A 行动

- 在 `CourseRecallAgent._execute()` 入口统一调一次 `embed_text(query)`，将向量存为局部变量
- 语义缓存探测：传入 `query_embedding` 参数，移除内部 embedding 调用
- Milvus 检索：`search()` 新增 `query_vector` 可选参数
- 缓存索引写入：传入 `query_embedding` 参数
- embedding 异常时置 None 降级

### R 结果

- 缓存未命中时 embedding API 调用从 3 次降为 1 次
- 39/39 单测通过
- 遗憾：两处 `build_embedding_client()` 仍各自实例化（main.py 和 recall agent），未合并为真正的单例

### 60 秒口播

排查日志时发现同一个 query 在缓存未命中时被 embedding 了 3 次：语义缓存探测一次、Milvus 检索一次、缓存写入一次。三次调的是同一个外部 API，返回结果一样。修复很直接：在 `_execute()` 入口统一算一次，把向量传给三个消费者。具体实现是给 `_semantic_cached_courses()`、`search()` 和 `_index_semantic_cache()` 都加了 `query_embedding` 参数，如果传了就直接用，不传才自己算。embedding 异常时向量置 None，后续降级不调 Milvus。

### 3 分钟展开版

排查过程是这样的：我在日志里看到同一个请求对 DashScope embedding API 有 3 次调用，请求体里的 text 完全一样。追溯代码发现三个调用点：

第一次在 `_semantic_cached_courses()` 里。这个方法会把当前 query embedding 后，和 Redis 里存的历史 query embedding 做余弦相似度比较，超过阈值就命中缓存。

第二次在 `CourseVectorRepository.search()` 里。这个方法内部调 `embed_text(query)` 拿到向量后再调 Milvus 做 ANN 检索。

第三次在 `_index_semantic_cache()` 里。缓存未命中后要把当前 query 的 embedding 写入 Redis，供后续请求做语义比较。

三次调用的输入完全相同（同一个 query 文本），输出也完全相同（同一个 1152 维向量）。解决方案是在 `_execute()` 方法入口统一调一次 `embed_text(query)`，拿到 `query_embedding` 后作为参数传给三个消费者。

接口改动最小化：给三个方法都加了 `query_embedding: Optional[List[float]] = None` 参数。传入时直接使用，不传时保持原逻辑自己调 embedding——这样不影响其他调用方。

降级设计：如果入口的 `embed_text` 抛异常，`query_embedding` 置为 None。语义缓存探测跳过（没向量无法比较），Milvus 检索跳过（没向量无法 ANN），缓存写入跳过。召回退化为纯 MySQL 结构化查询，不中断整个推荐链路。

一个遗留问题：`main.py` 和 `CourseRecallAgent` 各自调 `build_embedding_client()` 实例化 embedding client。虽然两个实例读的是同一份配置、行为相同，但从代码洁癖角度应该合并为单例。没做是因为 Agent 层和 API 入口层的生命周期管理不同，强行共享可能引入隐式依赖。

### 可追问点

- 为什么不用全局缓存层？（Agent 层局部变量更简单，不引入额外状态管理）
- embedding 失败后怎么降级？
- 为什么 main.py 和 recall agent 各自实例化 embedding client？

---

## 故事八：课程拆分四类 chunk 提升语义召回精度

### 一句话

不把整门课压成一个向量，而是按语义维度拆成四类 chunk。

### S 情境

课程 CSV 字段很杂：课程名、教师、学分、校区、时间、容量、简介、考核、标签…如果整行 embedding，"不考试、作业少"和"东校区、周三"的语义会互相稀释。用户问学习体验和问时间容量应该命中不同的文本。

### T 任务

设计课程数据的向量化策略，让不同类型的需求能命中更对应的课程文本。

### A 行动

- 每门课拆成 4 类 chunk：
  - `basic`：课程名、教师、学分、类型、分类、领域——解决"这是什么课"
  - `schedule_capacity`：校区、时间、地点、容量、热度——解决"能不能选、难不难抢"
  - `learning_profile`：简介、考核、难度、作业、考试、小组作业——解决"学起来轻不轻松"
  - `audience_tags`：年级/专业/先修、适合人群、标签——解决"适不适合这个学生"
- 500 门课 × 4 = 2000 条 chunk，每条独立 embedding 后写入 Milvus
- 检索命中 chunk 后解析 `course_id`，回 MySQL 拿完整课程——Milvus 不做事实判断

### R 结果

- MySQL 导入验证：`course_records=50, course_chunks=200`（50×4）
- Milvus 有效实体与 MySQL chunk 一致
- 遗憾：chunk 设计不是一次定终局，后续可以根据真实 query 命中分布调整字段组合

### 60 秒口播

课程数据我没有整行直接 embedding。原因是课程 CSV 字段很杂，课程名、时间、校区、考核、标签全混在一起，整行 embedding 后"不考试"和"东校区"的语义会互相稀释。所以我把每门课拆成四类 chunk：basic 解决"这是什么课"，schedule_capacity 解决"能不能选"，learning_profile 解决"学起来轻不轻松"，audience_tags 解决"适不适合这个学生"。用户说"不考试、作业少"时更容易命中 learning_profile，说"东校区、别太难抢"时命中 schedule_capacity。Milvus 命中后只返回 course_id，最终展示仍回 MySQL。

### 3 分钟展开版

课程 CSV 每行有 20+ 个字段。如果把所有字段拼成一段文本做整行 embedding，会出现语义稀释问题。举个例子："不考试"的语义和"东校区"的语义在同一个 1152 维向量里互相干扰——一个描述学习体验，一个描述物理位置，强行压在一起后两个方向的区分度都会下降。

拆分策略基于学生选课的四类核心关注点：

1. **basic chunk**：课程名、教师、学分、类型（必修/选修）、分类、领域。回答"这是什么课"。
2. **schedule_capacity chunk**：校区、上课时间、地点、容量、已选人数、热度。回答"能不能选、难不难抢"。
3. **learning_profile chunk**：课程简介、考核方式、难度、作业量、是否考试、是否有小组作业。回答"学起来轻不轻松"。
4. **audience_tags chunk**：年级限制、专业限制、先修要求、适合人群、标签。回答"适不适合这个学生"。

500 门课 × 4 = 2000 条 chunk。每条 chunk 独立调 embedding API 生成 1152 维向量，写入 Milvus `course_chunks_real` collection。MySQL `course_chunks` 表存 chunk 的文本元数据和 course_id 映射。

检索流程：用户 query embedding 后在 Milvus 做 ANN 检索，命中若干 chunk。从 chunk 的 `course_id` 字段回溯到课程，然后去 MySQL `course_records` 拿完整课程信息。Milvus 不做事实判断——它只负责"这些 chunk 和 query 语义接近"，最终推荐展示的课程信息全部来自 MySQL。

导入脚本 `scripts/ingest_course_dataset.py` 支持 `--limit` 参数，先少量验证再全量导入。全量 500 门 = 2000 次 embedding API 调用，因为 DashScope embedding API 没有批量接口（每次只能传一条 text），所以导入耗时较长。

chunk 设计不是一次定终局。后续如果有真实 query 日志，可以分析命中分布：如果某类 chunk 命中率极低，说明字段组合可能需要调整。

### 可追问点

- 为什么不整行 embedding？
- chunk 设计怎么影响召回质量？
- MySQL 回表如何保持 Milvus 排序？
- 导入失败后如何校验 MySQL 和 Milvus 一致？
