# 大学校园智能体平台 · 面试 STAR 包装（2026-09-02 仓库核对版）

> 生成方式：interview-star-packaging 技能 + 5 个并行 subagent 对仓库（CLAUDE.md / docs/v2.0.0/notes/ / eval/reports/ / 前端组件）逐条考古核对。
> 使用规则：凡标 [待你补充] 的地方都是仓库查不到、但你可能手上有依据的——面试前补齐出处，否则不要背。
> 与旧文档关系：docs/interview-star-stories.md 是 v2 早期 8 个单点故事；本文按 2026.09（Phase4）现状整理成「一份简历块 + 一套完整口播」，数字已按最新仓库口径校正。

## 一句话电梯稿（≤20 字左右，挑一条背）

1.（推荐）「选课问答和报告评语，变成一句话的事」——先讲业务价值，技术名词后面再说。
2.「学生问一句、老师传一表，报告自动出」——点两端痛点，适合对教育/ToB 场景的岗位。
3.「把校园里最重复的选课答疑和写评语，做成对话」——口语感强，自我介绍开场用。

## S 情境

- 背景与约束：独立开发 2026.05–2026.08（仓库 81 个 commit，实际跨 04–09 月）；没有团队、没有真实用户，就用真实校园素材自证——广工学生手册 PDF、约 500 门真实公选课、脱敏成绩单（课程/学分/成绩保留、姓名学号抹掉）；LLM 走中转 API 有配额上限，所以默认验证必须 mock、能离线断言就不烧 token。
- 起点不是这张图：仓库最早是「多 Agent 电商推荐」练手（拿不到真实数据，自己也觉得"简陋 RAG、深度不够"），5 月换到校园场景——这里既有真实素材，又有真实痛点：公选课全靠盲选、几十页手册要自己翻、教师期末要手工逐份写成绩报告和评语。
- 因果一句话：正因为要一个"能用真实数据自证、单人 4 个月能交付"的多智能体项目，才把场景定在校园，把「学生端问答 + 教师端批量报告」做成双端主线。

## T 任务

- 一句话目标：把推荐 demo 升级成学生/教师双端可用、且"可测、可观测、可解释"的多智能体平台，覆盖选课推荐、知识问答、成绩报告、评价寄语四条业务主线 + 记忆/评测/监控地基。
- 职责范围：独立完成需求到部署全链路——业务重构、deepagents 编排、tool/skill 三层、RAG 分区与脱敏、记忆持久化、评测 runner 与 judge、SSE 协议、Next.js 前端、Docker 全家桶（7 个运行时服务）。
- 诚实分界（面试被问"从哪学的"要有说法）：
  - 编排/压缩/熔断/委派思路参考了本机 4 个开源项目：pi、claude-code、OpenMAIC、FastGPT；FastGPT 只在 docker-compose 里留过配置，没启用。
  - 全程用 LLM 结对提速（git 可查），但架构决策（拆不拆 agent、权限怎么给、评测怎么建）自己拍板并写复盘笔记落盘。
  - [待你补充] 电商初版是否照着教程/课程代码改造而来——回答"最早怎么入门的"要用。

## A 行动（重点：我改了什么、为什么这么改）

### 主线：不让 v1 白干，也不让它挡住 v2

- 原来：v1 只有"推荐接口 + 简陋 RAG"，功能单薄，加新场景基本要重写。
- 我做了什么：先花一周做 Phase0 go/no-go POC（验证 deepagents 能在中转 API + Docker 里跑通），再定升级路线：v1 的 supervisor 5-agent 推荐管线**不重写**，整个包成 recommend_courses 工具挂进新主 agent；main_agent 统一接 /chat，业务模块降级为"工具 + SKILL.md"，另起 tool/skill 两层目录收编能力。
- 为什么这样选：v1 已有 39 个单测和调好的管线，推倒重来是浪费；包成工具让 main_agent 拿到 deepagents 的路由/记忆/流式能力，又保住 v1 双模式灵活性——"单 agent 还是多 agent"的路线纠结，最后落在"统一入口 + 能力做工具"的折中上。

### 故事线一：路由翻车 → 教师端 4/4（Chat 智能体）

- 原来：升级 deepagents 后真实链路 5 个 case 挂 4 个——LLM 看到"出报告/写评语"要么读完 SKILL.md 就停住，要么把成绩单当知识库问题去查。
- 我做了什么：修法不在工具端在 prompt 端。在 main_agent 的 system prompt 顶部加"教师端意图关键词路由表"，显式写"命中成绩单/评语/报告必须调 dispatch_module，禁止当检索"；把 dispatch_module 的 intent 做成 Literal 枚举（report/evaluation/ppt/image_generate）并锁进工具白名单；SSE 的 tool 事件带上 args，评测按 args.intent 映射工具链。
- 结果：真实链路 1/5 → 4/4；加 20 个 prompt 契约测试把"关键词→模块"映射锁死，防止以后改 prompt 误删关键段落。教训沉淀在 2026-08-18-chat-intent-4-badcase-fix.md。

### 故事线一续：user_id 从"靠 LLM 猜"变成框架注入

- 原来：user_id 只进日志，查成绩单/做推荐要靠 LLM 从对话里猜再塞进工具参数——不可靠，等于把越权代查的口子交给模型。
- 我做了什么：建 agent/main/context.py，端点用 user_context() 包裹整个 agent run，工具统一 get_current_user_id() 读取；把 user_id 从所有工具的 args_schema 删掉——参数面让 LLM 无从伪造，数据面按 user_id 分区隔离，双重杜绝。
- 为什么没选 middleware：先试了 AgentMiddleware 注入，但中间件拿不到 config、Runtime 也没有 config，放弃；ContextVar + 端点包裹在同一事件循环内 100% 可靠。
- 结果：越权代查在参数面被结构上禁掉；同一模式复用到 query_transcript、recommend_courses。

### 故事线二：推荐链路——先破除"假优化"，再做真优化（Recommend）

- 原来：推荐慢，我一度以为是轮次多（rounds 14→7 仍 169–206s）——这是假优化；翻日志才发现耗在 4 个**串行** LLM 调用上。
- 我做了什么：用 asyncio.gather 把 画像∥召回、重排∥可行性 并行（supervisor.py + react_tools 改组），206s→60s（-71%）；顺手修了一处"同步版并行是缩进在 break 后面的死代码、单测根本没跑到"的隐患。
- 第二个慢点：main_agent 读完 SKILL 后自己逐个调 7 个原子工具，>300s。我把 5 个阶段封装成一个 recommend_courses 一键工具、白名单收回原子工具、prompt 改成"直接调一键工具"，/chat 222s→152.8s。
- 稳定性：ReAct 空转轮次/无超时/重复调工具 → 加"空转即终止"、max_rounds 20→10、asyncio.wait_for 超时、ToolMessage 按 tool_calls 原始顺序回填（修掉 OpenAI 400）。
- 关键决策（都有笔记支撑）：
  - 硬约束（校区/时间/考试冲突）用确定性过滤放重排前，不靠 LLM——规则可解释、不会"悄悄放宽"；候选不足返回 hard_constraint_sparse 警告，不硬凑。
  - 召回做广度（关键词+热度，可缓存复用），重排做精度（画像 + Milvus 余弦融合），职责分开；规则分 0 时语义救不回来。
  - 语义阈值选 0.95 不选 0.9：实测"句式相同、关键词不同"的 query 余弦约 0.94 会误命中 0.9；宁可 miss 走全量召回，也不给错结果。实现是 Redis 集合桶 + 元数据 JSON + Python 端余弦比较（**注意不是 zset**，见文末核对表）。

### 故事线三：两类知识别再互相污染（RAG）

- 原来：query_knowledge 一个工具同时搜公共手册 + 个人成绩单、共用 top_k=5——问手册时候选里混进成绩单 chunk，反之亦然；权限边界也糊。
- 我做了什么：拆成 query_handbook（强制 public 分区，top_k=5）和 query_transcript（强制 ContextVar 注入的本人 user_id，top_k=3，schema 不收 user_id，未登录直接 error），公共解析抽到 tools/knowledge/_common。top_k 各有依据：手册要跨章跨页取 5 条，个人查分要精度取 3 条；拆开后两类查询不再互相妥协。动机复盘见 2026-08-25-knowledge-tools-split.md。
- 分块：弃固定窗口，改 heading-aware 递归切分——按"第X章/节/条"切语义单元、剔目录行、小块合并保留标题前缀、超长再按中文分隔符递归——解决长文档语义单元被切碎、标题正文分离、目录污染 chunk 三个问题。
- 脱敏放 ingest 期而不是检索期：原文会持久化进 Milvus/MySQL 并落盘，检索期再脱敏兜不住存储侧泄露。姓名→[姓名]、学号掩码、班级→年级、日期→年，课程名/成绩保留（本人要查分）。
- 真实翻车：上传页显示成功但库根本没写——service 默认 repos=None、写入分支永远被跳过、chunks_count 只是解析数且无日志。我在 runtime.init 末尾注入 repos 并加 documents_service_repos_wired 日志；顺手修了 create_dataset 漏传 user_id 会把个人数据误落 public 的安全回归（document_records 补 user_id 列）。
- 课程数据（区别于上面两份文档）的向量化分块：ingest_course_dataset.py 的 _build_chunks 把每门公选课按语义拆成 4 类 chunk——basic（课名/教师/学分/类型/分类/方向）、schedule_capacity（校区/时间/地点/容量/热度）、learning_profile（描述/考核/难度/给分）、audience_tags（适合人群/tags）——chunk_id 带 chunk_type、metadata_json 带 tags，一起写 MySQL + Milvus（Milvus schema 有 chunk_type 字段）；召回时命中维度随结果返回、按 course_id 去重聚合。诚实边界：目前是按课程聚合，"按 chunk_type 硬过滤/建特性标签"还没作为强逻辑落地，但结构已就位，是可继续深化的点。

### 故事线四：长会话不丢、压缩失败不静默（Memory）

- 原来：摘要只活在 checkpointer 里，会话一重建就丢、不可审计。
- 我做了什么：子类化 SummarizationMiddleware 为 SummarizationSyncMiddleware，捕获压缩事件后把摘要写进 chat_session_compactions（prev_compaction_id 串前后链、first_kept_message_id 记截断点、usage_json、status、model），60s 防抖；写库失败只告警不阻塞对话。
- 失败不静默：真实故障是 deepagents 把 LLM 摘要失败吞成 "Error generating summary" 前缀字符串、不抛异常——这种"假摘要"会被当真的塞进上下文。我覆写 _create_summary/_acreate_summary 做前缀检测，命中就走规则截断（保留最近 20 条、每条前 200 字符）并落 status=fallback。
- 压缩时机单点化：token 数优先用逐消息落库的 usage_json.total_tokens，缺失才估算（中文按 1/2、其余按 1/4）；模型窗口从 config/model_catalog 查（qwen3 128K / qwen3-vl 32K，未收录回退 128K），判据收口成 should_compact(tokens >= window - reserve)，消除各处自写阈值打架。
- 增量双模板：首轮用六节 summarize 模板；二次压缩读上轮摘要填 summarization_update 的 previous-summary 占位，按 preserve/add/update 规则续写，不丢首轮结构。
- 隔离：chat_memory_entries 加 agent_name 列，增删改查全按它过滤——子 agent（recommend 等）用自己名字写记忆，main_agent 只注入 main_agent 行，防止互相覆盖与注入串扰；compactions/usage_json 落库顺带成为成本与监控的数据源。

### 故事线五：教师端报告"看似卡死"其实是一串真实故障（Report）

- 现象：上传后一直报"请先上传成绩单"；生成 OK 却下载 404；生成中 UI 冻结诱导用户取消。完整复盘见 2026-08-31-report-api-debug-retrospective.md。
- 我做了什么（按排查顺序）：
  1. 前端拿到的是裸 File 不是 originFileObj，filter 恒空 → 上传压根没调后端；改用 uid+File 自管（rawFilesRef）。
  2. 新表 report_uploads 只进了 init.sql，旧 MySQL 卷没建表 → 落库失败；加列存在性迁移守卫。
  3. 进度全堵根因：render_report_batch 是分钟级单工具调用，langgraph 期间没有 agent 事件，旧的"事件间隙 drain"转不动进度 → 改成后台常驻 drainer（asyncio.create_task 持续转发 student_done/progress），进度实时可见。
  4. Next.js dev 代理硬编码 30s proxyTimeout 掐断长 SSE → experimental.proxyTimeout 放大到 30min。
  5. python-api 没挂卷、本地兜底产物重建即丢；MinIO 的 _local_only 永久锁死不重试 → 本地兜底卷挂载 + MinIO 30s 冷却自愈。
  6. grade4-6.html 有 4 行 tr 在 table 外（非法 HTML）→ PDF 表格错位；移回表内 + 评语划线格用 repeating-linear-gradient 实现，每行文字落在横线上。
- 结果：后端 381 passed（新增 upload CRUD/状态机/整批超时/长工具实时转发/批次 403 归属/班级覆盖/merged_batch_id 回填/minio 冷却等）；前端 132/132 + lint + build 过；真实链路 eval 37 份学生 PDF 全量生成（单批 12–15 分钟有 latency 记录佐证，是"慢"不是 bug）。
- 诚实边界：真实 LLM + WeasyPrint 的端到端 PDF 渲染只在容器里验证过，本机用 mock 覆盖各层契约；这轮改动上线前应重建容器复测。

### 故事线六：评语反幻觉——为什么不用 ReAct（Evaluation）

- 原来/风险：让 LLM 自由写评语，容易"自造"学生没选的课、编分数。
- 我做了什么：改成五层确定性直接管线——快照学生成绩单（MySQL）→ 5 维雷达方案（3 维固定 gpa/学分/均衡 + 2 维 LLM）→ LLM 写评语（4 种 comment_type 驱动）→ 引用核验硬闸 → 落库。核验闸是关键：评语里每个数字必须能在快照里溯源，引用不存在的值就拦截重试，重试不过走规则兜底。
- 为什么不用 ReAct：ReAct 把调用顺序交给 LLM，但反幻觉防控要求顺序确定——先拿事实、再生成、最后核验，所以用直接管线而不是自由工具调用。
- 结果：真实链路 6/6 通过（学生 71 门课 / 144.5 学分 / 加权 85.85，评语引用数值全部真实可溯源）；另有幻觉反例 case 集支撑"幻觉拦截"口径（统计口径见核对表）。

### 故事线七：可测可观测，自证"不是能跑，是可回归"（评测 + LangSmith）

- 原来：只有手写冒烟，接口经常"假闭环"（E2E 才戳穿 images 字段定义了但没接线）。
- 我做了什么：搭 eval_sets/*.jsonl（字段契约对齐 RAGAS/LangSmith）+ eval/runner.py，分三层验证：
  1. 离线断言层：exact/code 类断言（tool_chain/意图/numeric/reference/recall 等，多断言权重求和），mock LLM 跑 smoke、不耗额度——改动后可确定性回归。
  2. --live 真实端点端测：chat/report/evaluation/kb/web_search/image 等，报告带 LangSmith run_id 回链，落 eval/reports/。
  3. LLM-as-judge 三执行器：faithfulness 只对 kb_retrieval（逐句对照 reference.contexts，无上下文直接 judge_failed）、answer_relevancy 全集、rubric 按 case 规则打 G-Eval 分。
- 检索质量量化：实现 _ndcg_at_k/_f1_at_k（live kb 透出 rank/score 后计算），NDCG 惩罚"相关项排后"、F1@k 平衡 P/R。
- LangSmith 接线：三个 AOP 单点全覆盖（LLM 统一走 build_chat_openai、embedding 迁 OpenAIEmbeddings+@traceable、tracing 写 LANGCHAIN/LANGSMITH 双命名空间）；judge 结果经 attach_judge_scores 回写 dataset，供 LangSmith evaluator 消费。
- 踩坑：Docker 没 --build 跑旧代码；get_env_var 的 lru_cache 让配置改不生效——把 configure 提前到 main.py 顶部。
- 诚实边界：judge 三执行器代码就绪但真实 judge 还没跑（reports 里 judge_results 全 0、rubric 字段全空），默认不跑是为省配额——这是"已实装、未 full 验证"，别吹成"已上线"。

### 故事线八：SSE 断点续传——自己给自己挖坑又填上（流式）

- 原来：EventBuffer 用进程内 self._counter += 1，每次请求新实例 → 同 thread_id 跨请求 id 从 0 重复，续传无从谈起。
- 我做了什么：改 Redis INCR 全局单调 + LPUSH/LTRIM 环形缓冲（100 条、TTL 30min），Redis 不可用降级本地计数；4 个端点统一 EventBuffer + sse_with_id + parse_last_event_id，事件带 id:、done 附 last_event_id、读 Last-Event-ID 先 replay_from 回放；前端 consumeSSEWithRetry 指数退避 500ms→1s→2s（最多 3 次），自动带 Last-Event-ID。
- 协议纪律：必须 done 收尾、失败走结构化 error、不许静默断流——不然用户分不清"结束/卡死/失败"（130s+ 无 done 那次其实是 LLM 配额耗尽）。
- 取消 vs 自动重连：同一个 AbortController，catch 里 signal.aborted 直接 return 不重试，sleep 也监听 abort——用户主动取消和网络断线必须区分。
- 前端体验：chat 页 for await chatStreamWithRetry 消费流，done 事件按 agent_tree 契约渲染 AgentActivityTimeline（think/act/observe）+ CourseGraph（nodes/edges 来自 tools/mindmap/course_graph.py）；用 rAF 节流把每 token setSegments 的 O(N) 浅拷贝改 O(1)，长流不卡。
- 结果：端测验证断线后首条新事件 id=54 > 53，不丢事件；EventBuffer 后端单测 + 前端 retry 单测覆盖"abort 后不重试"等边界。

### 关键决策速记（每条一句话，被追问时展开）

| 决策 | 为什么没选另一个 |
|---|---|
| v1 supervisor 包成工具而非重写 | v1 有 39 单测与调好的管线，包工具可同时拿到 deepagents 能力 |
| 主 agent 统一入口 | 一个入口多场景可扩展，业务模块以工具/SKILL 挂载，换实现不动主 prompt |
| dispatch_module 只确认不执行 | 路由与执行解耦，LLM 只选 Literal intent，避免让模型决定复杂执行链 |
| user_id 用 ContextVar 注入 | 放工具参数 = 交给 LLM 猜且可伪造；框架注入后按分区隔离 |
| 硬约束确定性过滤先于重排 | 校区/时间/考试是事实规则，LLM 软排序不可解释还会悄悄放宽 |
| 召回/重排职责分离 | 召回做广度可缓存，重排做精度；规则分 0 时语义救不回 |
| 语义缓存阈值 0.95 | 0.94 误命中实证；宁可 miss 全量召回不给错结果 |
| query_handbook/query_transcript 拆开 | 混搜 top_k 让两类查询互相妥协、权限语义糊；5/3 各归其位 |
| 脱敏在 ingest 期 | 原文持久化进存储，检索期兜不住存储侧泄露 |
| 压缩失败用前缀检测+规则截断 | deepagents 把失败吞成字符串不抛异常，只能检测前缀；宁降级不中断会话 |
| 压缩判据单点 should_compact | 模型窗口随 model_catalog 走，消除各处自写阈值打架 |
| 评语用确定性直接管线而非 ReAct | 反幻觉要求顺序确定：先事实→再生成→后核验 |
| 记忆按 agent_name 隔离 | 子 agent 语义不同，user 级全局表会互相覆盖 |
| SSE 用 Redis INCR + 环形缓冲 | 跨实例/重启 id 唯一；进程内计数同 thread 跨请求会重复 |

## R 结果（可验证；数字均按仓库最新口径）

- 功能闭环：学生端（选课推荐/手册问答/个人成绩查分）+ 教师端（批量成绩单 → 逐学生 PDF 报告 + 雷达画像评价寄语），前端 12 个静态路由全挂载。
- 质量：后端单测 460+（2026-09-02 实测 `pytest -m "not slow"` 收集 464/468，4 个 slow 跳过；简历雏形写的 446 偏旧，建议改口 460+）；前端单测 130+（报告页闭环后 132/132）。
- 评测资产：9 个评测集 / 78 case / 23 份报告（雏形"8 集 74 case / 22 份"是 image_recognize 集落库前的快照，口径一致）；chat_intent 教师端真实链路 1/5 → 4/4；评价寄语真实链路 6/6；报告真实链路 37 份学生 PDF 全量生成（2/2 批次）。
- 性能：推荐链路 206s→60s（-71%，串行 LLM 改并行）；/chat 222s→152.8s（7 个原子工具封装成 1 个一键工具）；语义缓存命中跳过 Milvus 召回。
- 工程资产：81 commits；Python 约 2.4 万行；前端 TS/TSX 约 6.7 千行；Docker 7 个运行时服务。
- 仍不完善（诚实、短）：LLM-as-judge 三执行器已实装但真实 judge 未 full 跑（rubric 待 authoring）；无 CI/CD，回归靠本地全绿；压缩阈值从开源项目移植、未按本项目真实上下文调参；推荐 A/B 的 react 组默认关闭（名存实亡，仅保留可选）。

## 口播版（60～90 秒，可照念）

> 我做了一个大学校园多智能体平台，一个人从需求到部署，前后 4 个月。做它的原因很直接：公选课靠盲选、学生手册要自己翻、老师期末要手工给每个学生写成绩报告和评语——这三件事都重复、都费时，而校园里正好有真实的课程、手册和脱敏成绩单能让我验证效果。
>
> 整个系统我拆成学生、教师两端。学生端用自然语言问选课、查手册、查自己的成绩；教师端批量上传成绩单，一键生成逐学生的 PDF 报告和带雷达画像的评价寄语。技术上是一条主线：用 deepagents 建一个统一主 agent 做意图路由，把 29 个工具挂上去，用户身份通过框架的 ContextVar 注入，不让模型猜 user_id，从参数和数据两个面杜绝越权。
>
> 讲两个我印象最深的翻车。第一个是路由：升级框架后真实链路 5 个 case 挂 4 个，模型看到"出报告"反而去查知识库——修法不在工具端，在提示词端，我加了教师端意图路由表并用契约测试锁死，修到 4/4。第二个是长任务进度：教师端批量出报告要十几分钟，进度事件没独立转发，界面像卡死一样诱导用户取消，我改成后台常驻转发进度、放大开发代理超时、修复 MinIO 本地兜底不重试的问题，闭环才真正打通。
>
> 结果上，后端 460+ 单测、前端 130+ 单测，9 个评测集 78 个 case 23 份报告；评价寄语真实链路 6/6 无幻觉，报告链路 37 份学生 PDF 全量生成；推荐链路从 206 秒优化到 60 秒。
>
> 诚实说，LLM-as-judge 的三个裁判执行器我写完了，但真实裁判还没全量跑，因为要省 API 配额；项目也没有 CI，回归目前靠本地测试全绿——这两块是我知道的技术债，接下来会补。

## 展开版（2～3 分钟，在口播版上多讲 2 个细节 + 1 条反思）

> 讲法：口播版前两段照念，从"讲两个翻车"处替换成下面更细的版本，最后落到反思。

先说推荐链路那个"假优化"的教训：系统慢，我一开始以为是模型思考轮次太多，把轮次从 14 压到 7，结果还是 170~200 秒——这是典型的没看数据就动手。后来翻日志才发现，耗时根本不在轮次，在 4 个 LLM 调用是串行的。我把画像和召回、重排和可行性用 asyncio.gather 并行，直接 206 秒降到 60 秒。这件事让我养成一个习惯：先定位瓶颈再优化，不靠猜。

第二个细节是知识库的权限拆分。最早一个工具同时搜公共手册和个人成绩单，问手册的时候候选里会混进别人的成绩单片段，权限边界也很模糊。我把它拆成两个工具：查手册固定走公共分区取 5 条，查成绩单只允许查当前登录人自己的分区取 3 条，而且工具参数里根本不出现 user_id，身份从框架的 ContextVar 注入——这样模型既猜不到也传不了别人的身份，越权在结构上就不存在。为了验证这个，我的评测集里有专门的权限反例 case。

再补一个我自己踩的流式坑：断点续传的 id 一开始用进程内计数器，每次请求都是新实例，同一个会话的 id 会从 0 重新数，续传根本没法做。我改成 Redis 自增 + 环形缓冲，客户端断线重连时带上最后收到的 id，服务端把缺失事件回放出来。容器里实测：53 个事件后断线，重连从 54 继续，一个不丢。

反思：这个项目最大的价值不是功能多，而是我学会了怎么证明系统没坏——离线断言、真实链路、LLM 裁判三层验证，外加 LangSmith 全链路 trace。如果再来一次，我会先补 CI：现在"本地绿不代表容器绿"，Docker 忘加 --build 跑旧代码这种问题，我踩过不止一次。

## 避免"报菜名"的替换表（针对雏形原文）

| 雏形里的空泛说法 | 建议改成的动作句 |
|---|---|
| 基于 deepagents 构建主智能体统一路由，注册 29 个工具 | 真实链路 5 个 case 挂 4 个后，我在 prompt 顶部加教师端意图路由表并锁进白名单，修到 4/4 |
| 用户身份由框架层 ContextVar 注入，杜绝越权代查 | 工具参数里不再出现 user_id，身份从框架注入，模型既猜不到也传不了别人的身份 |
| 多 Agent 并行编排（5 个子智能体） | 画像/召回/重排/可行性从 4 个串行 LLM 改成并行，206s→60s |
| 语义缓存使用 redis 的 zset 存储，余弦 >0.95 复用 | 阈值从 0.95 起，是因为 0.94 的句式相似查询会误命中 0.9 阈值；命中只跳过召回，结果仍走硬约束与重排 |
| 数据合并完整性校验（缺科禁止渲染） | 缺科直接禁止渲染，因为"缺科也出报告"等于把错误数据交给家长/学生 |
| 引用核验硬闸，违规重试后规则兜底 | 评语里每个数字必须能在成绩单快照里溯源，核验不过重试、再不过走规则兜底 |
| 幻觉 case 拦截率 100% | 6/6 真实评语全部可溯源（71 门课/144.5 学分/85.85）；另有幻觉反例 case 集验证拦截逻辑（口径见核对表） |
| chunk 采用 heading-aware 递归切分 | 按第X章/节/条切语义单元并剔目录行，解决长文档被固定窗口切碎、标题正文分离 |
| 对话压缩写后同步持久化 | 摘要原来只活在 checkpointer，会话重建就丢；我落库成 compaction 链并记截断点，失败还能审计 |
| 压缩失败经前缀检测走规则截断兜底不静默 | 框架会把摘要失败吞成 Error generating summary 字符串，我检测前缀后规则截断并落 fallback 状态 |
| SSE 事件 ID 单调递增 + Last-Event-ID 断点续传 | id 原来进程内自增、跨请求从 0 重复；改 Redis 自增+环形缓冲，断线重连实测从 54 续传不丢事件 |

## 简历 bullet 对齐（把雏形 8 条压成 5~6 条，动词开头、带数字、全可溯源）

> 简历段建议用这个版本替换原 8 条（太长会被面试官跳读；更细的动作句留给口播）。

```
大学校园多智能体平台（独立开发）                2026.05–2026.08
- 基于 deepagents 自建主 agent 统一对话入口：真实链路路由失败 1/5 → 4/4（prompt 意图路由表 + 契约测试锁死），
  29 个工具注册、用户身份 ContextVar 注入，从参数与数据面杜绝越权代查。
- 推荐链路 5-agent 编排：4 个串行 LLM 改并行 206s→60s；硬约束确定性过滤 + 召回/重排职责分离；
  Redis 语义缓存（余弦>0.95 命中跳过召回，阈值由 0.94 误命中实证决定）。
- 教师端批量成绩单→PDF 报告与雷达评价寄语：缺科禁止渲染、评语数字必须可溯源（反幻觉硬闸），
  真实链路 37 份学生 PDF 全量生成、评价 6/6 无幻觉。
- RAG 按权限分区：手册(public/top_k=5)与个人成绩单(本人分区/top_k=3)拆工具，脱敏在摄入期完成；
  长会话压缩写后同步落库 + 失败前缀检测规则兜底，不静默。
- 三层评测体系（离线断言→真实链路→LLM-as-judge）+ LangSmith trace：9 集 78 case / 23 份报告；
  后端单测 460+、前端 130+；SSE 断点续传（Redis 单调 ID + Last-Event-ID，实测断线不丢事件）。
```

## 数字真实性核对表（面试前必须过一遍，别背没出处的数）

| 雏形数字 | 仓库证据（2026-09-02 核对） | 建议口径 / 动作 |
|---|---|---|
| chat_intent 正确率 94% | 仓库查无此数；现有 smoke 24/24(mock)、教师端真实链路 4/4、早期 live 17/20=85% | 改口"教师端真实链路 4/4、24 case 评测全过"；若 94% 另有出处，[待你补充] |
| 1/5 → 4/4 | 属实（08-17 live pass_rate=0.2 → 08-18 修后 4/4，报告落盘） | 直接用 |
| 29 个工具 | runtime 27 + documents 2 ≈ 29；主 agent 白名单现为 21 | 简历写"注册 29 个"没问题，被追问时能说出白名单 21 的口径差异 |
| Redis zset 存语义缓存 | 仓库无 zadd/zrange；实际是集合桶+元数据 JSON+Python 余弦线性比较 | 改成"Redis + Python 端余弦比较"；zset 说法删掉或补出处 |
| 课程推荐 RAG 拆 4 类 chunk | 属实：python/scripts/ingest_course_dataset.py::_build_chunks 拆 basic / schedule_capacity / learning_profile / audience_tags 四类，chunk_type+tags 入 MySQL/Milvus，召回按 course_id 聚合 | 可写"课程按 4 类语义分块入库（含 tags 元数据）"；别说"已按 chunk_type 硬过滤建标签"——目前按课程聚合，维度过滤未强落地 |
| 报告 37 份 PDF 全量正确生成 | 属实（report_math_live 2/2 批次、37 学生，单批 12~15min） | 直接用 |
| 幻觉拦截率 100% / 通过率 98% | 支撑证据是 6/6 真实链路 + 反幻觉硬闸设计 + 反例 case；98% 具体口径仓库未见 | 改口"真实链路 6/6、评语数值全部可溯源"；100%/98% 保留需[待你补充]统计口径 |
| 后端单测 446 | 2026-09-02 实测 not slow 收集 464/468 | 改口"460+"（446 是较早口径，会被当场戳穿过时） |
| 8 个评测集 74 case / 22 份报告 | 现 9 集 78 case / 23 份（74 与 22 是 image_recognize 落库前快照，口径一致） | 改口"9 集 78 case / 23 份报告"最稳 |
| 端到端 p95 22.8s→14.5s | 仓库无 22.8；相近证据：chat_intent live p50=14.5s/p95=25.7s；推荐 206s→60s | [待你补充] 该数字端点/采样/冷热缓存口径；找不到就用"推荐 206s→60s + chat p50=14.5s" |
| 前端 130+ 单测 | 报告页闭环后 npm test 132/132；更早口径 127 | 写"130+"并说清是 2026-08-31 后口径 |

## 可追问点 + 一句答法（模拟面试用）

1. 路由为什么不让 main_agent 直接委派子 agent？→ 路由与执行解耦：LLM 只选 Literal intent，模块怎么执行由后端管线决定，换实现不动主 prompt。
2. ContextVar 注入 user_id 会不会串号/跨任务失效？→ 端点在同一个事件循环内包裹调用，可靠；asyncio.gather 子任务不共享 ContextVar，所以 embedding 缓存改用了 dict+Lock。
3. 语义缓存 0.95 阈值命中率够吗？→ 阈值来自 0.94 误命中实证，宁可 miss 全量召回也不给错；monitor 已预留降到 0.9 的调参建议。
4. 缓存命中后还走重排吗？→ 只省 Milvus 召回，候选仍走硬约束/重排/可行性，不会把坏结果固化进缓存。
5. 评测集怎么防过拟合/污染？→ 诚实答：目前是手写 case 集，还没拆 dev/test 留存，是已知技术债（可追问点的价值就在这里）。
6. judge 用主模型当裁判有没有自评偏差？→ 有，所以默认不跑省配额；理想是换更便宜的模型做对照，尚未落地。
7. 环形缓冲 max=100，超长流断线回放不全怎么办？→ 100 条/TTL 30min 覆盖单轮典型规模；超长流兜底是整轮重试，边界已在单测覆盖。
8. 37 份 PDF 生成要 12~15 分钟，为什么不并行更快？→ 已用信号量控制并发防 LLM 限流；真实瓶颈是外部 LLM 单次 10~60s，且评语质量优先于吞吐。

## 自测（是否还像背文档）

- [x] 开场 30 秒内出现了"选课盲选/手册自己翻/老师手工写报告评语"的业务问题（见口播版第一段）
- [x] 至少 1 处写清了"改之前 vs 改之后"（多处：路由 1/5→4/4、推荐 206s→60s、id 跨请求重复→Redis 续传）
- [x] 至少 1 个句子主语是"我"且带动作（全文以"我做了什么/我改成"为主语）
- [x] 没有连续 3 个纯技术名词无解释（技术名词都跟了"为什么"或"解决什么"）
- [x] 有结果 + 诚实说明未量化/未完成之处（judge 未 full 跑、无 CI、p95 数字待补出处）

## [待你补充] 汇总（共 4 处，补齐前不要背对应句子）

1. chat_intent "94%" 的统计口径与出处（若沿用）。
2. 幻觉拦截率 100% / 寄语通过率 98% 的评测统计口径（仓库只有 6/6 live 与反例 case）。
3. 端到端 p95 22.8s→14.5s 的端点、采样次数、冷/热缓存口径。
4. 电商初版是否照教程/课程改造（回答"怎么入门"用）。
