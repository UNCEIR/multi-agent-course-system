# 01 — 真值边界

> 核心规则：每条关于项目的声明，必须归类到五个等级之一。写简历/口播时，只用「可以写」和「谨慎写」的内容。

## 分类标准

| 等级 | 定义 | 简历可用？ | 口播可用？ |
| --- | --- | --- | --- |
| 🟢 **可以写** | 有代码+测试+验证三重证据 | ✅ 直接用 | ✅ 直接用 |
| 🟡 **谨慎写** | 代码存在但未在本次环境完整验证，或需要限定词 | ✅ 加限定词 | ✅ 加"当前""本次环境" |
| 🟠 **补证据后写** | 逻辑合理但缺测试/Docker 验证/压测数据 | ❌ 先补证据 | ❌ 先补证据 |
| 🔴 **不能写** | 不属实或严重夸大 | ❌ 永远不写 | ❌ 永远不写 |
| ⚪ **无法判断** | 信息不足，无法确定 | ❌ 标注待补充 | ❌ 标注待补充 |

---

## 一、项目定位类

| # | 声明 | 等级 | 判定依据 |
| --- | --- | --- | --- |
| 1.1 | "学校公选课 Multi-Agent 推荐系统" | 🟢 可以写 | 代码完整存在，功能可运行 |
| 1.2 | "面向约 500 门真实公选课" | 🟢 可以写 | CSV 数据集 + ingest 脚本存在 |
| 1.3 | "学生用自然语言描述选课偏好" | 🟢 可以写 | `POST /api/v1/recommend` 接受自然语言 prompt |
| 1.4 | "已上线/已部署到生产环境" | 🔴 不能写 | 仅本地 Docker 环境，无生产部署证据 |
| 1.5 | "服务了 N 名学生/产生了 N 次推荐" | 🔴 不能写 | 无真实用户数据 |
| 1.6 | "个人项目，2026 年 5-6 月开发" | 🟢 可以写 | Git 历史和 notes 时间线可证明 |
| 1.7 | "解决了学生选课信息过载问题" | 🟡 谨慎写 | 方案设计合理但无真实用户验证，加"旨在解决" |

---

## 二、Multi-Agent 架构类

| # | 声明 | 等级 | 判定依据 |
| --- | --- | --- | --- |
| 2.1 | "实现了 5 个专业 Agent" | 🟢 可以写 | `agents/` 目录下 5 个 Agent 文件 |
| 2.2 | "Supervisor 集中式编排" | 🟢 可以写 | `supervisor.py` 的 `recommend()` 方法 |
| 2.3 | "支持 Pipeline 和 ReAct 双模式" | 🟢 可以写 | `supervisor.py` 中 `recommend()` 和 `_react_recommend()` 双路径 |
| 2.4 | "ReAct 模式已上线 A/B 实验" | 🟡 谨慎写 | 代码存在但当前 A/B 未注册 react group。加"代码已实现，待注册实验组" |
| 2.5 | "Agent 之间有对话协商" | 🔴 不能写 | 当前是 Supervisor 调度，Agent 间无直接通信 |
| 2.6 | "Phase 1 画像和召回并行执行" | 🟢 可以写 | `asyncio.gather()` 在 supervisor.py 中 |
| 2.7 | "每个 Agent 有独立 fallback 机制" | 🟢 可以写 | `BaseAgent._fallback()` + tenacity 重试 |
| 2.8 | "Agent 失败不阻断整条链路" | 🟢 可以写 | `AgentResult(success=False)` 返回降级结果，不抛异常 |
| 2.9 | "规则保下限、LLM 提上限" | 🟢 可以写 | 硬约束用纯规则、画像/排序/理由用 LLM，设计明确 |
| 2.10 | "ReAct 模式 LLM 最多 20 轮工具调用" | 🟢 可以写 | `react_tools.py` 中 `max_iterations=20` |
| 2.11 | "ReAct 硬约束工具锁死不可跳过" | 🟢 可以写 | `_react_recommend()` 循环结束后强制执行硬约束 |

---

## 三、硬约束过滤类

| # | 声明 | 等级 | 判定依据 |
| --- | --- | --- | --- |
| 3.1 | "校区、考试偏好等做确定性过滤" | 🟢 可以写 | `HardConstraintFilter` 纯规则实现 |
| 3.2 | "硬约束过滤在 LLM 重排之前执行" | 🟢 可以写 | Phase 1.5 在 Phase 2 之前 |
| 3.3 | "过滤后候选不足时返回警告，不悄悄放宽" | 🟢 可以写 | `hard_constraint_sparse` / `hard_constraint_no_match` 警告 |
| 3.4 | "类别模糊匹配准确率 100%" | 🔴 不能写 | 已知有子串匹配局限，"理工"不匹配"自然科学与工程技术" |
| 3.5 | "自然语言→硬约束提取准确率 > 90%" | ⚪ 无法判断 | 无标注测试集量化评估 |

---

## 四、召回与数据架构类

| # | 声明 | 等级 | 判定依据 |
| --- | --- | --- | --- |
| 4.1 | "MySQL+Milvus+Redis 三层数据架构" | 🟢 可以写 | 三个 Repository 文件均在 `repositories/` |
| 4.2 | "MySQL 存储 500 门课程结构化字段" | 🟢 可以写 | `course_records` 表，ingest 脚本 |
| 4.3 | "Milvus 存储 2000 条向量块（1024 维）" | 🟢 可以写 | `course_chunks_real` 集合，4 类 chunk × 500 门 |
| 4.4 | "四类 chunk 避免语义稀释" | 🟢 可以写 | basic/schedule_capacity/learning_profile/audience_tags 分块逻辑 |
| 4.5 | "Redis 缓存候选 ID，不缓存完整对象" | 🟢 可以写 | `CourseRecallCacheRepository` 只存 course_id 列表 |
| 4.6 | "语义缓存：同 bucket 内 cosine ≥ 0.95 复用" | 🟢 可以写 | `course_recall_cache_repository.py` 语义缓存逻辑 |
| 4.7 | "分布式锁防缓存击穿（setnx）" | 🟢 可以写 | `course_recall_cache_repository.py` 第 234 行 |
| 4.8 | "宽召回 + 精召回双路合并" | 🟢 可以写 | Phase 1 先宽召回（无画像）再精召回（有画像） |
| 4.9 | "embedding 调用从 3 次降为 1 次" | 🟢 可以写 | `course_recall_agent.py` 第 38 行入口计算，传递给三个消费者 |
| 4.10 | "语义缓存在本次环境验证通过" | 🟡 谨慎写 | 代码存在但需确认当前 Docker 环境 Redis 正常 |
| 4.11 | "缓存命中率 > 80%" | 🔴 不能写 | 无真实流量统计 |

---

## 五、排序与评分类

| # | 声明 | 等级 | 判定依据 |
| --- | --- | --- | --- |
| 5.1 | "召回阶段仅用关键词匹配+热度评分" | 🟢 可以写 | `_score_candidates()` 不使用 profile |
| 5.2 | "重排阶段融合 profile 偏好+Milvus COSINE" | 🟢 可以写 | `_compute_score()` 公式 |
| 5.3 | "评分职责分离是有意设计" | 🟢 可以写 | CLAUDE.md 明确标注此设计决策 |
| 5.4 | "Milvus 相似度作为乘法放大器" | 🟢 可以写 | `final = profile_score * (1.0 + milvus_sim * 0.5)` |
| 5.5 | "LLM 候选内重排显著优于纯规则排序" | ⚪ 无法判断 | 无 A/B 对比实验的指标数据 |

---

## 六、可行性检查类

| # | 声明 | 等级 | 判定依据 |
| --- | --- | --- | --- |
| 6.1 | "容量/时间冲突风险检查" | 🟢 可以写 | `CourseFeasibilityAgent` 实现 |
| 6.2 | "LLM 生成个性化抢课建议" | 🟢 可以写 | `priority_advice` 字段 |
| 6.3 | "超过 12 门课时仅前 12 门走 LLM" | 🟢 可以写 | `max_tokens=4096` 限制 |
| 6.4 | "LLM 建议解析失败时回退规则兜底" | 🟢 可以写 | `_parse_advice_json()` 失败→空 dict→规则兜底 |
| 6.5 | "抢课建议准确率 > 80%" | ⚪ 无法判断 | 无标注测试集 |

---

## 七、流式推荐类

| # | 声明 | 等级 | 判定依据 |
| --- | --- | --- | --- |
| 7.1 | "支持 SSE 流式推荐" | 🟢 可以写 | `stream_recommend()` 方法 + `StreamingResponse` |
| 7.2 | "token 级 `[COURSE:id:name]` 标记解析" | 🟢 可以写 | `StreamTokenMarkupParser` 状态机 |
| 7.3 | "Phase 3 独立超时保护（60s）" | 🟢 可以写 | `stream_timeout_seconds` 配置 |
| 7.4 | "signed-events 支持（HMAC 签名）" | 🟢 可以写 | 请求参数 `signed_events=true`，密钥来自 Redis |
| 7.5 | "SSE 流式在本次环境端到端验证通过" | 🟡 谨慎写 | 需确认当前 Docker 环境，建议补一次 curl 验证 |

---

## 八、A/B 测试类

| # | 声明 | 等级 | 判定依据 |
| --- | --- | --- | --- |
| 8.1 | "实现了 Thompson Sampling 动态分流" | 🟢 可以写 | `ab_test.py` 中 Beta 分布采样 |
| 8.2 | "一致性哈希保证同用户同组" | 🟢 可以写 | MD5(`user_id:experiment_id`) 取模 |
| 8.3 | "注册了 3 个实验" | 🟢 可以写 | `rec_strategy`/`react_vs_pipeline`/`copy_style` |
| 8.4 | "A/B 实验有统计显著结论" | 🔴 不能写 | 无足够样本量做统计检验 |
| 8.5 | "react_vs_pipeline 实验正在运行" | 🟡 谨慎写 | 已注册但 supervisor 未路由到它。加"代码已实现，待激活" |

---

## 九、工程实践类

| # | 声明 | 等级 | 判定依据 |
| --- | --- | --- | --- |
| 9.1 | "Docker Compose 一键部署" | 🟢 可以写 | `docker-compose.python.yml` |
| 9.2 | "39 个单测全部通过" | 🟢 可以写 | pytest 输出，`docs/resume-template.md` 已验证 |
| 9.3 | "Docker E2E 接口验证通过" | 🟢 可以写 | `docs/resume-template.md` 已验证 |
| 9.4 | "代码覆盖率 > 80%" | 🔴 不能写 | 未运行过覆盖率统计，不能编造数字 |
| 9.5 | "支持 CI/CD" | 🔴 不能写 | CLAUDE.md 明确标注"无 CI/CD" |
| 9.6 | "生产级代码质量" | 🟡 谨慎写 | 有 Agent 基类/降级/日志，但无 lint/CI/压测。加"工程化程度较高" |
| 9.7 | "P99 延迟 < 2s" | 🔴 不能写 | 无压测数据 |

---

## 十、LLM 与 Embedding 类

| # | 声明 | 等级 | 判定依据 |
| --- | --- | --- | --- |
| 10.1 | "LLM 用 OpenAI 兼容协议" | 🟢 可以写 | ChatOpenAI client，`/compatible-mode/v1` |
| 10.2 | "Embedding 用 DashScope 原生 API" | 🟢 可以写 | 自定义 `EmbeddingClient`，`/api/v1` |
| 10.3 | "Embedding 模型：tongyi-embedding-vision-plus" | 🟢 可以写 | 配置中指定 |
| 10.4 | "LLM 和 Embedding 协议不能混用" | 🟢 可以写 | CLAUDE.md 明确警告 |
| 10.5 | "语义缓存阈值 0.95（从 0.9 提高）" | 🟢 可以写 | CLAUDE.md 记录了修复过程 |

---

## 快速检查：简历 bullet 自检清单

逐条对照你的简历 bullet，确认每条属于哪个等级：

- [ ] 每条 bullet 有 🟢 或 🟡 等级支撑
- [ ] 没有 🔴 等级的声明
- [ ] 🟡 等级的声明加了限定词（"当前""本次环境""代码已实现"）
- [ ] ⚪ 等级的声明已标注"待补充"
- [ ] 能用代码文件+行号回答"你怎么证明？"
