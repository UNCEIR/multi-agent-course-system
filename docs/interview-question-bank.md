# 面试追问题库

练习方法：每题先给一句结论，再补一条代码或验证证据，最后主动说一个边界。不要把回答变成技术名词清单。

## 1. 项目真实性与边界

### Q1：这个项目到底解决什么问题？

**推荐回答**：它解决的是学生选公选课时“自然语言偏好 + 真实课程约束”难以同时处理的问题。学生说的是模糊需求，但系统最后必须返回真实课程、时间、容量和风险提醒。

**证据**：主接口是 `POST /api/v1/recommend`，响应里包含 `courses`、`recommendation_reasons`、`selection_warnings` 和 `agent_results`。

**边界**：当前没有真实学生行为闭环，更多是一个可演示、可扩展的工程项目。

### Q2：哪些是当前主线，哪些是 Legacy？

**推荐回答**：当前主线是 `python/` 下的公选课推荐链路；

**证据**：`docs/architecture.md` 和 `docs/code-walkthrough.md` 都以 `python/main.py`、`SupervisorOrchestrator`、课程 Agent 和课程数据仓储为主线。

**边界**：部分模型字段仍保留 `products` 等兼容字段，不能把它解释成当前业务仍在推荐商品。

## 2. Multi-Agent 设计

### Q3：为什么需要 Multi-Agent，不用单 Agent？

**推荐回答**：选课推荐不是单一生成任务，而是理解、召回、排序、硬约束过滤、风险判断和解释的组合。拆开后每一步的输入输出、失败回退和观测指标更清楚。整体策略是**规则保下限、LLM 提上限**：核心召回、硬约束过滤、初始评分走工程代码保证确定性，LLM 参与画像提取、排序优化、理由生成三个环节提供语义理解能力。5/25 架构审视的结论也印证了这一点——纯 LLM 方案在硬约束（校区、时间、考试）上会引入概率误差，纯规则方案又无法处理自然语言偏好，Multi-Agent 让每个环节选择最适合的实现方式。

**证据**：Supervisor 中 Phase 1 并行画像和宽召回，Phase 1.5 做硬约束过滤，Phase 2 并行重排和可行性检查，Phase 3 生成理由。

**边界**：不是所有场景都需要 Multi-Agent；如果只是 FAQ 问答，一个检索增强回答链路可能就够了。

### Q4：Supervisor 模式有什么好处？

**推荐回答**：这个项目流程依赖关系明确，集中式 Supervisor 更容易控制阶段顺序、降级和最终过滤，不需要 Agent 间自由交接控制权。项目同时保留了 ReAct 工具调用模式（`_react_recommend()`），通过 A/B 分流共存。Pipeline 阶段固定、延迟可预测，适合大部分正常请求；ReAct 由 LLM 决定工具调用顺序，适合异常场景（召回不足、硬过滤后课太少）。两种模式并存是因为正常路径不需要 LLM 决策开销，但异常路径需要灵活补救。

**证据**：主链路能在画像成功后补召回，并在重排前插入硬约束过滤，这些都适合集中编排。ReAct 模式代码在 `supervisor._react_recommend()`，通过 `ab_engine` 的 group 字段路由。

**边界**：ReAct 当前 A/B 实验里无 "react" group 注册，需手动在 `services/ab_test.py` 启用。如果是开放式多轮任务规划，Handoffs 或更动态的图编排可能更合适。

### Q5：Phase 1 为什么能并行？

**推荐回答**：宽召回可以先基于原始 prompt 和 context 开始，不必等画像。画像完成后再用结构化约束补一次召回，减少漏召回。

**证据**：`SupervisorOrchestrator` 使用 `asyncio.gather()` 同时执行学生画像和课程召回。

**边界**：如果后续召回完全依赖画像字段，这个并行收益会下降。不过当前架构通过 wide + refined 双路召回部分缓解了这一问题——wide 召回不等画像、基于原始 prompt 保广度，refined 召回等画像完成后用结构化约束补精度，两次结果合并去重。

## 3. 数据与召回

### Q6：为什么 MySQL 和 Milvus 都需要？

**推荐回答**：Milvus 解决语义相关性，MySQL 保证课程事实和结构化过滤。最终课程必须回 MySQL，不能只相信向量命中的文本片段。

**证据**：Milvus 返回 chunk/course ID 后，召回 Agent 会通过 MySQL 回表拿完整 `Course`。

**边界**：当前 MySQL 短文本查询比较轻量，长 prompt 主要靠 Milvus 和画像字段。

### Q7：为什么课程要拆四类 chunk？

**推荐回答**：整行 CSV 字段太杂，直接 embedding 会让学习体验、时间容量、适合人群互相稀释。拆 chunk 后，用户不同类型的需求能命中更对应的文本。

**证据**：导入脚本会生成 `basic`、`schedule_capacity`、`learning_profile`、`audience_tags` 四类 chunk。

**边界**：chunk 设计不是一次定终局，后续可以根据真实 query 命中情况调整字段组合。

### Q8：Redis 缓存为什么只存 `course_id`？

**推荐回答**：缓存完整课程会带来课程容量和已选人数过期问题；缓存候选 ID 可以减少重复召回成本，同时命中后回 MySQL 保证事实最新。

**证据**：`CourseRecallCacheRepository` 缓存候选 ID 列表，命中后仍调用 MySQL 回表。

**边界**：如果 MySQL 压力也变大，可以再评估字段级缓存或更短 TTL，但不能牺牲课程事实准确性。

### Q9：语义缓存会不会导致错误复用？

**推荐回答**：有这个风险，所以语义命中必须保留相似度阈值、结构化条件和后续硬约束过滤。缓存只影响候选集，最终课程仍会经过 MySQL 回表和约束过滤。

**证据**：观测字段里有 `cache_match_type`、`cache_similarity`、`milvus_skipped`，硬约束过滤在重排前执行。

**边界**：语义缓存的阈值需要基于更多真实样例调参，目前还不是生产级自适应策略。

## 4. LLM 与幻觉控制

### Q10：怎么降低 LLM 推荐不存在课程的风险？

**推荐回答**：LLM 不负责创造课程，只负责画像抽取、候选内排序和基于输入字段写理由。最终课程来自 MySQL 回表。

**证据**：重排 Agent 要求只输出候选课程 ID；JSON 解析失败会走规则排序。

**边界**：LLM 仍可能给出不稳定排序，所以还需要规则兜底和低温/可控随机性优化。

### Q11：如果 LLM 返回格式不合法怎么办？

**推荐回答**：画像会尝试去掉 Markdown 代码块再解析 JSON，失败时走关键词启发式；重排失败走规则排序；理由失败用课程字段拼 fallback 理由。

**证据**：所有 Agent 继承 `BaseAgent`，并在各自实现里有 fallback 分支。

**边界**：fallback 能保证链路不中断，但推荐质量可能下降，需要在 `agent_results` 里暴露失败信息。

## 5. 硬约束与风险

### Q12：为什么硬约束要独立成 Phase 1.5？

**推荐回答**：明确条件不能只靠排序分数表达。用户说“只要西校区”时，不符合校区的课程不应该进入重排。

**证据**：`HardConstraintFilter` 在召回后、重排前执行；流式接口会输出 `phase15_complete`。

**边界**：硬约束提取本身仍可能漏，所以还保留 prompt 兜底和分类模糊匹配。

### Q13：爆满课程为什么不直接过滤？

**推荐回答**：爆满是风险，不一定是硬冲突。热门课可能非常匹配兴趣，所以保留并提醒学生优先抢、准备替代课更贴近真实选课。

**证据**：容量满员和紧张会进入 `selection_warnings`，时间/专业/先修不满足才偏硬过滤。

**边界**：如果学校规则明确满员不可选，也可以把它升级为硬约束。

### Q14：如果硬约束过滤后课程不够怎么办？

**推荐回答**：系统返回不足条数 warning，不偷偷放宽条件。这样用户知道是约束太强，而不是系统悄悄推荐不符合要求的课程。

**证据**：端到端验证中有 `requested_count_shortage` warning。

**边界**：后续可以增加“是否放宽某个条件”的交互式追问，但当前版本还没有。

## 6. 流式推荐与观测

### Q15：为什么要做 SSE 流式接口？

**推荐回答**：推荐链路阶段较多，同步接口只能等最终结果。SSE 可以让前端看到阶段进度和理由 token，演示时也更容易解释链路。

**证据**：流式事件包含 `start`、`phase1_complete`、`phase15_complete`、`phase2_complete`、`phase3_complete`、`done`。

**边界**：当前流式主要服务展示和交互体验，不等于全链路异步任务系统。

### Q16：为什么 Phase 3 超时从 token 流开始算？

**推荐回答**：如果从整个请求入口算，画像、召回、重排已经消耗了预算，理由生成一开始就可能被误判超时。Phase 3 token 流应该有自己的预算。

**证据**：流式修复后，测试和 Docker 验证都能正常输出理由 token 与 `done`。

**边界**：前置阶段仍需要独立超时和监控，不能只管 Phase 3。

## 7. 验证与不足

### Q17：你怎么证明项目能跑？

**推荐回答**：我会分层证明：单测验证缓存、硬约束、流式事件；Docker 验证 `/health`、同步推荐和流式推荐；数据导入验证 MySQL 课程数、chunk 数和 Milvus 实体一致性。

**证据**：已有记录包括 `test_stream_recommend.py` 5 passed、缓存与硬约束相关测试 14 passed、Docker E2E 调用成功。

**边界**：这些是工程验证，不是线上业务效果验证。

### Q18：当前最大不足是什么？

**推荐回答**：我会说三个：时间冲突仍是轻量匹配，A/B 和 metrics 是进程内实现，真实学生行为画像还没有接入主链路。

**证据**：这些限制在架构文档和复盘笔记中都有明确记录。

**边界**：后续优化应该先做标准课表时间模型和实验结果持久化，再考虑更复杂的个性化行为特征。

## 8. ReAct 编排与双模式

### Q19：Pipeline 和 ReAct 什么时候用哪个？

**推荐回答**：大部分请求用 Pipeline——阶段固定、延迟可预测。ReAct 适合异常场景：召回不足、硬过滤后课程太少、推荐的课全爆满。正常请求 ReAct 走直线，等价于 Pipeline，只在异常时触发额外轮次。

**证据**：`supervisor._react_recommend()` 最多 10 轮（`max_rounds = 10`）；A/B 分流在 `recommend()` 入口判断 `experiment.get("group") == "react"` 路由到 ReAct 路径。

**边界**：ReAct 当前 A/B 未注册 "react" group，需在 `services/ab_test.py` 手动注册才能生效。

### Q20：硬约束工具为什么锁死？

**推荐回答**：硬约束是确定性需求——校区不对就是不对，不能让 LLM 商量。如果 LLM 跳过硬约束工具，编排器在循环结束时检测 `ReactState.hard_filtered` 标志，强制补调 `filter_hard_constraints`。

**证据**：`react_tools.py` 中 `ReactState` 维护 `hard_filtered: bool = False` 标志；`_react_recommend()` 循环结束后检查 `if executor.state.courses and not executor.state.hard_filtered and executor.state.profile`，条件满足则强制执行 `executor._tool_filter_hard_constraints()`。

**边界**：其他 6 个工具是可跳过的，LLM 可以决定不调。硬约束工具执行后如果 profile 中无有效约束，会直接置 `hard_filtered = True` 并放行全部课程。

## 9. LLM 语义初筛与评分

### Q21：LLM 语义初筛失败怎么退？

**推荐回答**：返回空列表，`raw_courses` 保持不变。Rerank 的 `_compute_score` 规则预筛作为兜底，候选只会因为规则排序丢掉低分课，不会因为 LLM 失败中断链路。

**证据**：`supervisor._llm_semantic_filter()` 返回空列表时不抛异常；调用侧 `if semantic_filtered:` 为 falsy 则保持 `raw_courses` 不变，继续进入 Phase 2。

**边界**：如果所有候选都低相关，规则预筛可能不如 LLM 选得准，但至少保证链路不断。

### Q22：为什么不全程 LLM？

**推荐回答**：500 门课×完整描述单次请求上万 token，经济性不可靠。而且硬约束（校区、时间、考试）需要确定性判断，LLM 会引入概率误差。我的策略是规则保下限，LLM 提上限。

**证据**：核心召回（MySQL 结构化查询 + Milvus 向量检索）、硬约束过滤（`HardConstraintFilter`）、初始评分（`_compute_score` 规则公式）链路是工程代码；LLM 参与画像提取（`StudentProfileAgent`）、排序优化（`CourseRerankAgent` LLM 路径）、理由生成（`RecommendationReasonAgent`）三个环节。

**边界**：全量 LLM 理论上语义理解更深，但成本和确定性是现实约束。

### Q23：`_compute_score()` 公式怎么设计的？Milvus 距离怎么融入？

**推荐回答**：`profile_score` 汇总 domain（+4.0）/category（+3.0）/campus（+2.0）/workload（+1.5）/exam（+1.5）/grade_friendly（+1.2）偏好匹配分，加上热度和基础加分项。最终 `final = profile_score * (1.0 + milvus_sim * 0.5)`，Milvus 相似度作为乘法放大器——向量命中的课程 profile 分被放大最多 50%。用乘法而不是加法，是因为想让向量高分和 profile 高分同时满足的课程更突出。

**证据**：`course_rerank_agent._compute_score()` 中 `milvus_weight = 0.5`，`return round(profile_score * (1.0 + milvus_sim * milvus_weight), 4)`。

**边界**：0.5 系数是经验值，没有基于大量真实 query 调参。低年级（大一、大二）遇到超高热度课（`popularity_level >= 4`）会额外扣 2.0 分，避免推荐抢不到的课。

## 10. 语义缓存与 Embedding 优化

### Q24：语义缓存误命中的根因？

**推荐回答**：1024 维向量对句式模板的区分度不足。"我对计算机感兴趣"和"我对心理学感兴趣"8 个字中 7 个相同，余弦相似度 ~0.94，超过原始阈值 0.9。

**证据**：阈值修复在 `settings.py` 中 `course_recall_cache_semantic_threshold: float = 0.95`（0.9→0.95）；`course_recall_agent.py` 的 `_execute()` 入口统一计算 embedding 后传入语义缓存探测，确保 prompt 始终纳入 payload。

**边界**：0.95 是经验阈值，更理想的方案是关键词提取 + 向量双重判断。

### Q25：阈值为什么选 0.95？

**推荐回答**：经验性选择。0.9 太松，句式相似但关键词不同的 query 会误命中。1.0 太严，几乎等于精确匹配，语义缓存失去意义。0.95 在当前样本中能区分大部分关键词差异，但不是科学调参的结果。

**证据**：实际测试中 "计算机 vs 心理学" cosine ~0.94 < 0.95 → miss，不再误命中。

**边界**：需要更多真实 query 样本做系统调参。当前阈值仅在有限测试集上验证，生产环境可能需要按场景动态调整。

### Q26：embedding 调用从 3 次降 1 次的具体做法？

**推荐回答**：缓存未命中路径中，语义缓存探测、Milvus 检索、缓存索引写入各自调一次 embedding——同一个 query，结果完全一样。修复是在 `_execute()` 入口统一算一次，把向量传给三个消费者。每个消费方法新增 `query_embedding` 参数，传了就用，不传才自己算。

**证据**：`course_recall_agent._execute()` 顶部 `query_embedding = self.vector_repo.embedding_client.embed_text(query)` 统一计算；`_try_semantic_cache()`、`_semantic_course_ids()`、`_index_semantic_cache()` 三个方法均接受 `query_embedding` 参数，不再各自调用 embedding API。

**边界**：embedding client 仍有两个实例（`main.py` 全局单例和 recall agent 自建各一个），未合并为单例，但每次请求内不再重复调用。

## 11. 可行性与前端

### Q27：priority_advice LLM 化和规则的 fallback？

**推荐回答**：最多 12 门课送 LLM 生成个性化抢课建议（考虑年级优先权、容量比例、替代课）。超过 12 门的走规则 batch。`_parse_advice_json` 返回空 dict 时不抛异常，静默回退——排查时需看 `llm_advice_parse_empty` 日志。

**证据**：`course_feasibility_agent._llm_priority_advice()` 中 LLM 初始化 `max_tokens=4096`；解析失败时 `_parse_advice_json` 返回空 dict，外层回退到 `_rule_priority_advice_batch()`。

**边界**：Docker 环境下 LLM 调用可能因超时失败，自动退回规则路径。静默回退意味着不看日志无法区分 LLM 成功和失败。

### Q28：类别模糊匹配修复前后的差异？

**推荐回答**：修复前，`"理工"` 子串不在 `"自然科学与工程技术"` 中，合规课程被误过滤。修复后，`student_profile_agent.py` 的 `category_rules` 增加了别名映射（如 `"理工类"→"自然科学与工程技术类"`、`"理工科"→"自然科学与工程技术类"`、`"文科"→"人文与社会科学类"`），prompt 中的口语表达会映射到 DB 中的 canonical 分类名。

**证据**：`student_profile_agent.py` 的 `_extract_prompt_hard_constraints` 中 `category_rules` 字典包含 `"自然科学"`、`"工程技术"`、`"理工类"`、`"理工科"`、`"工科类"`、`"社科"` 等关键词到规范分类名的映射。

**边界**：别名表仍是静态的，新增分类名需手动维护。当前映射覆盖了常见口语表达，但无法处理完全未预见的说法。

## 12. 反向自测

- [ ] 回答里是否先讲业务问题，再讲技术实现？
- [ ] 是否至少给出一个文件、接口、测试或日志证据？
- [ ] 是否承认了真实边界，而不是把演示项目说成生产平台？
- [ ] 是否避免了未验证指标？
- [ ] 是否能在 60 秒内讲完答案？
- [ ] 能说清 Pipeline 和 ReAct 的区别和适用场景
- [ ] 能解释语义缓存误命中的根因和修复方案
- [ ] 能画出评分职责分离前后的变化
