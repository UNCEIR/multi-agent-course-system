# 学校公选课 Multi-Agent 推荐系统改造设计

## 目标

将原多 Agent 电商推荐项目改造成面向教务系统在校生的学校公选课推荐系统。用户以自然语言 prompt 描述兴趣、时间、难度、考核、绩点友好度、校区等需求，系统通过多 Agent 协同从公选课数据集中召回、重排并解释推荐结果。

## 数据入库形式

课程 CSV 不直接整行写入向量库，而是采用结构化库和向量库分层：

- MySQL `course_records` 保存完整课程记录，包含课程名、教师、学分、分类、领域、校区、时间、容量、热度、考核方式、难度、作业量、适合人群、标签等字段。
- MySQL `course_chunks` 保存课程语义分块，保留 `chunk_id`、`course_id`、`chunk_type`、`content` 和元数据。
- Milvus `course_chunks` 或 `course_chunks_real` 保存每个 chunk 的 embedding，向量主键为 `course_id:index:chunk_type`。
- 查询时先通过学生 prompt 进行语义召回，拿到 chunk_id 后解析 course_id，再回 MySQL 获取完整课程信息。

默认 chunk 类型：

- `basic`：课程名称、教师、学分、课程分类、领域。
- `schedule_capacity`：校区、上课时间、地点、容量、已选人数、热度、抢课建议。
- `learning_profile`：课程简介、考核方式、难度、作业量、给分友好度、考勤、考试、小组作业。
- `audience_tags`：年级限制、专业限制、先修要求、适合人群、标签、历年热度。

## Agent 设计

主链路采用 Supervisor 编排 5 个专业步骤（其中 4 个为课程决策 Agent，1 个为最终解释 Agent）：

1. 学生画像 Agent：从 prompt 和 context 抽取兴趣领域、时间约束、校区偏好、考核偏好、难度偏好、给分诉求和避雷条件。
2. 课程召回 Agent：结合 MySQL 结构化筛选与 Milvus 语义召回，形成候选课程池。
3. 课程重排 Agent：用 LLM 结合学生画像、课程属性、时间容量和学习负担进行精排。
4. 选课可行性 Agent：检查容量、热度、限制条件和时间冲突风险，输出可推荐课程、预警和抢课建议。
5. 推荐理由 Agent：对入选课程生成面向学生的解释，强调匹配点、风险点和选课策略。

## API 设计

保留 `POST /api/v1/recommend` 入口，业务语义改为课程推荐。请求支持：

- `user_id`：教务系统学生 ID。
- `prompt` / `query`：学生自然语言需求。
- `num_items`：推荐课程数量。
- `context`：结构化约束，如 `campus`、`avoid_time_slots`、`preferred_domains`、`difficulty_preference`。

响应核心字段：

- `courses`：推荐课程列表。
- `recommendation_reasons`：每门课推荐理由。
- `selection_warnings`：爆满、容量紧张、时间冲突、限制条件等提醒。
- `agent_results`：各 Agent 执行结果，便于面试讲解和排障。

## 改造范围

本轮按方案 2 执行：

- Python 主链路彻底课程化。
- README 和 `docs/interview-guide.md` 完全改成公选课推荐主题。
- 保留旧电商模块作为历史对照，不作为主 API 链路。
- Java/Go 暂不做大规模包名重构，避免扩大风险。

## 验证

- 更新或新增课程主链路测试。
- 运行 Python 单元测试中与 Supervisor 和课程 Agent 相关的用例。
- 检查 README 与面试文档不再以电商、商品、库存、营销作为主叙事。
