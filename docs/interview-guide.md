# 学校公选课 Multi-Agent 推荐系统 — 面试完全指南

本文档用于讲清楚这个项目：面向教务系统学生的公选课推荐 Agent 系统。

## 一分钟项目介绍

我做的是一个学校公选课 Multi-Agent 推荐系统。学生在教务系统里用自然语言描述需求，比如“不考试、作业少、给分友好、东校区、周三晚上不要有课、对艺术和心理学感兴趣”。系统会先用学生画像 Agent 抽取偏好，再用课程召回 Agent 结合 MySQL 和 Milvus 从公选课数据集中召回候选课，然后由课程重排 Agent 做个性化排序，选课可行性 Agent 检查容量、爆满、时间冲突、年级/专业/先修限制，最后推荐理由 Agent 生成可解释建议。

核心价值是把“搜课程”升级为“理解学生诉求后做决策”，并且结果可解释、可追踪、能落到真实课程 CSV 数据集。

## STAR 话术

**S 背景**

学校公选课选择通常有几个痛点：课程数量多，学生需求很模糊；同一门课既要看兴趣匹配，也要看时间、校区、考核方式、难度、作业量和容量；传统关键词搜索无法理解“给分友好、不考试、不要小组作业”这类隐性诉求。

**T 任务**

我的目标是把一个通用推荐项目改造成教务选课场景下的多 Agent 决策系统，让学生输入 prompt 后，系统能自动完成画像抽取、课程召回、个性化重排、选课风险判断和推荐理由生成。

**A 行动**

1. 设计了 Supervisor 编排架构，将复杂选课决策拆成学生画像、课程召回、课程重排、选课可行性、推荐理由 5 个 Agent。
2. 构建课程 RAG 数据层，将 `public_elective_courses.csv` 写入 MySQL 主表，并拆成 `basic`、`schedule_capacity`、`learning_profile`、`audience_tags` 四类 chunk 写入 Milvus。
3. 在召回阶段结合结构化筛选和语义检索：MySQL 处理校区、时间、分类等精确字段，Milvus 处理“轻松、给分友好、不要考试、艺术兴趣”等语义需求。
4. 在重排阶段用 LLM 综合学生画像和课程属性排序，并要求只从候选课程 ID 中选择，降低幻觉。
5. 在可行性阶段做容量、爆满、时间冲突、专业/年级/先修限制检查，输出风险提醒，而不是只给一个黑盒推荐列表。

**R 结果**

项目形成了从课程 CSV 到向量库、再到 Agent 推荐 API 的完整闭环。接口能返回课程列表、推荐理由、选课风险和每个 Agent 的执行轨迹，既能演示工程能力，也方便面试时讲解 RAG、Multi-Agent、Supervisor、结构化过滤和可解释推荐。

## 架构图

```text
学生 prompt
  |
  v
Supervisor
  |
  +-- Phase 1:
  |     学生画像 Agent || 课程召回 Agent
  |
  +-- Phase 2:
  |     课程重排 Agent || 选课可行性 Agent
  |
  +-- Phase 3:
        推荐理由 Agent
  |
  v
课程列表 + 推荐理由 + 风险提醒 + Agent 轨迹
```

## 关键文件

| 文件 | 说明 |
|---|---|
| `python/orchestrator/supervisor.py` | Supervisor 主编排逻辑 |
| `python/agents/student_profile_agent.py` | 从 prompt 抽取学生选课画像 |
| `python/agents/course_recall_agent.py` | MySQL + Milvus 课程召回 |
| `python/agents/course_rerank_agent.py` | LLM 课程精排 |
| `python/agents/course_feasibility_agent.py` | 容量、爆满、时间和限制条件检查 |
| `python/agents/recommendation_reason_agent.py` | 推荐理由生成 |
| `python/scripts/ingest_course_dataset.py` | 课程 CSV 入库和向量化 |
| `python/repositories/course_repository.py` | 课程 MySQL 主表与回表查询 |
| `python/repositories/course_vector_repository.py` | 课程 chunk 向量库访问 |

## 高频面试题

### Q1：为什么这个项目适合 Multi-Agent？

因为公选课推荐包含多个相对独立的判断维度：学生画像、课程语义召回、个性化排序、选课可行性和推荐解释。每个子任务需要不同的上下文和判断标准。拆成多个 Agent 后，职责更清晰，也更容易并行、降级和排查问题。

### Q2：为什么不用一个大 prompt 直接让 LLM 推荐？

一个大 prompt 有三个问题：

1. 容易幻觉，LLM 可能推荐数据集中不存在的课程。
2. 难以接入结构化约束，比如容量、时间冲突、年级限制。
3. 不利于工程化监控，无法知道失败发生在画像、召回、排序还是解释阶段。

本项目先从真实数据集中召回候选课程，再让 LLM 只在候选集内重排，能显著降低幻觉。

### Q3：课程数据为什么要拆 chunk？

整行 CSV 太长且字段语义混杂，直接 embedding 会让“时间容量”“学习体验”“适合人群”等语义互相稀释。拆成 chunk 后，用户问“不要考试、作业少”会更容易命中 `learning_profile`；问“周三晚上不要、东校区”会更容易命中 `schedule_capacity`。

### Q4：MySQL 和 Milvus 各自负责什么？

Milvus 负责语义召回，解决自然语言需求和课程描述之间的模糊匹配。MySQL 负责完整课程记录、结构化过滤和回表展示，比如校区、时间、容量、教师、学分、限制条件等。

### Q5：Supervisor 是怎么并行的？

Phase 1 中，学生画像和课程召回可以并行，因为召回可以先基于原始 prompt 做宽召回。画像完成后，如果抽取出强约束，再补一次结构化召回。Phase 2 中，课程重排和选课可行性检查也可以并行，因为它们都只依赖候选课程池。最后推荐理由依赖最终课程列表，所以串行执行。

### Q6：如何处理爆满课程？

爆满课程不一定直接删除。比如它非常符合学生兴趣，可以保留但加高风险提醒，告诉学生“开选后优先抢，并准备替代课程”。这比简单过滤更符合真实教务场景，因为热门课本身可能就是学生最想要的课。

### Q7：如何处理时间冲突？

如果学生在 prompt 或 context 中明确给出避开时段，例如 `avoid_time_slots=["周三第9-10节"]`，选课可行性 Agent 会把命中该时段的课程作为硬冲突过滤掉，并在 `filtered_courses` 中记录原因。

### Q8：如何降低 LLM 幻觉？

四个手段：

1. LLM 重排只允许输出候选课程 ID。
2. 输出必须是 JSON 数组，解析失败走规则排序。
3. 推荐理由只能基于输入课程字段生成。
4. 最终课程都来自 MySQL 回表结果，而不是 LLM 自由生成。

### Q9：冷启动怎么处理？

学生没有历史行为时，系统直接使用 prompt 和 context。公选课推荐天然适合 prompt-first，因为学生当次需求往往比历史偏好更重要，比如这学期只想找“不考试、周四下午”的课。

### Q10：如果没有向量库还能运行吗？

可以降级。课程召回 Agent 会尝试 Milvus 语义召回，失败时记录 warning，然后使用 MySQL 结构化召回或内置 mock 课程兜底。这样演示时不会因为向量服务不可用导致整个系统崩溃。

### Q11：A/B 测试在这个项目里怎么用？

可以对比不同推荐策略：

- control：规则排序
- treatment_llm：LLM 精排
- treatment_vector：增强语义召回

指标可以是点击详情率、加入选课计划率、最终选中率、退课率、学生满意度等。当前代码保留了实验分桶框架，便于面试讲工程扩展。

### Q12：这个项目和普通 RAG 的区别是什么？

普通 RAG 主要是“检索资料后回答问题”。本项目是“检索课程后做决策”。它不仅要找相关课程，还要排序、过滤时间冲突、判断容量风险，并生成可执行建议，所以 RAG 只是课程召回 Agent 内部的一部分。

## 可讲的技术亮点

### 1. 课程数据建模

`course_records` 保存完整课程，`course_chunks` 保存分块文本，Milvus 保存 chunk embedding。这样兼顾结构化约束和语义检索。

### 2. Prompt 到结构化画像

学生画像 Agent 将自然语言转成：

```json
{
  "preferred_domains": ["人文艺术"],
  "preferred_campus": ["东校区"],
  "avoid_time_slots": ["周三第9-10节"],
  "exam_preference": "不考试",
  "workload_preference": "少",
  "grade_friendly_preference": "高"
}
```

后续 Agent 不需要反复理解原始大段文本，而是直接消费结构化画像。

### 3. 可解释推荐

最终响应不是只返回课程 ID，而是返回：

- 为什么匹配
- 有什么风险
- 是否需要优先抢
- 是否建议准备替代课程

这让项目更贴近真实教务系统。

### 4. 稳定性设计

所有 Agent 继承 `BaseAgent`，具备统一的耗时记录、重试和 fallback。某个 Agent 失败时，Supervisor 可以用默认结果继续返回，而不是让整条链路崩溃。

## 简历项目描述

```text
学校公选课 Multi-Agent 推荐系统 | 个人项目 | 2026.05
• 设计并实现面向教务系统的公选课推荐 Agent 系统，支持学生通过自然语言 prompt 描述兴趣、时间、校区、考核方式和学习负担偏好
• 采用 Supervisor 模式编排学生画像、课程召回、课程重排、选课可行性和推荐理由 5 个 Agent，实现并行召回、精排和可解释决策
• 基于 MySQL + Milvus 构建课程 RAG 数据层，将公选课 CSV 拆分为 basic、schedule_capacity、learning_profile、audience_tags 四类语义 chunk
• 使用 LLM 将学生需求结构化为选课画像，并在候选课程集合内完成个性化重排，结合 JSON 校验和候选 ID 约束降低幻觉
• 实现容量爆满、时间冲突、年级/专业/先修限制等选课风险判断，输出推荐理由和抢课建议

技术栈：FastAPI · LangGraph · Multi-Agent · Milvus · MySQL · Redis · Docker · OpenAI-Compatible LLM
```

## 面试追问回答

### “你这个项目真的需要 Agent 吗？”

需要，但不是为了炫技。因为选课推荐有多个专业判断步骤：理解学生、检索课程、排序、检查可行性、解释结果。每一步都可以独立失败、独立降级、独立优化，这正是 Multi-Agent 的价值。

### “为什么课程召回还要 MySQL？”

向量库适合语义相关性，不适合做严格条件判断。比如“东校区”“周三第9-10节”“容量 100”“年级限制”这类字段，MySQL 更准确。两者结合才可靠。

### “怎么证明推荐结果可信？”

结果可信主要来自三点：课程来自真实 CSV 入库，不由 LLM 编造；排序只在候选课程内完成；可行性 Agent 会把容量、冲突和限制条件透明地返回给学生。

### “如果学生 prompt 很短怎么办？”

如果学生只说“推荐几门轻松的公选课”，系统会从 `learning_profile` chunk 召回作业量、考试、难度相关课程，并用默认画像补全缺失字段。缺失约束不会强行猜测。

### “如果学生需求互相矛盾怎么办？”

比如既要“爆满热门课”又要“稳定选上”，系统不会强行给一个完美答案，而是保留匹配课程并给出风险提醒，建议准备替代课程。这比隐藏冲突更符合实际选课场景。

## 面试前检查清单

- [ ] 能讲清楚为什么课程 CSV 要拆 chunk
- [ ] 能画出 Supervisor + 5 Agent 架构
- [ ] 能解释 MySQL 与 Milvus 的分工
- [ ] 能说明如何约束 LLM 不推荐不存在的课程
- [ ] 能说出时间冲突、容量爆满、先修限制怎么处理
- [ ] 能跑通 `scripts/ingest_course_dataset.py`
- [ ] 能调用 `/api/v1/recommend` 演示 prompt 到课程推荐结果
