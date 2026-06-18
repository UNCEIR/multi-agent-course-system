# 文档索引

本文档说明 `docs/` 根目录下文档的分工，避免面试材料、架构说明和历史规划互相重复。

## 当前主线

| 文档 | 作用 | 适合什么时候读 |
| --- | --- | --- |
| `docs/interview-guide.md` | 面试准备主入口，给出讲法、训练路径、按岗位切换侧重点 | 第一次准备项目介绍 |
| `docs/interview-star-stories.md` | 8 个 STAR 故事，含 60 秒口播、3 分钟展开和可追问点 | 练项目经历表达 |
| `docs/resume-template.md` | 三个方向的简历 bullet、项目标题和口播模板 | 写简历或投递前 |
| `docs/interview-question-bank.md` | 28 题高频追问、推荐回答、代码/验证证据和真实边界 | 模拟面试或自测 |
| `docs/architecture.md` | 双模式编排、评分职责分离、三层数据架构、降级策略 | 讲系统设计 |
| `docs/code-walkthrough.md` | 从入口到 Agent、ReAct 工具、召回、硬约束、流式输出的代码证据链 | 面试官要求看代码 |
| `docs/supervisor-main-orchestration.md` | 流式推荐接口编排细节：召回打分、硬过滤规则、marker parser、SSE 事件 | 深入讲编排实现 |

## LLM Intern 项目包装（`docs/llm-intern/`）

按 llm-intern 方法论对项目进行系统化真值边界、证据契约和 JD 匹配度评估。**不替代已有文档**，补充结构化分析层。

| 文档 | 作用 | 适合什么时候读 |
| --- | --- | --- |
| `docs/llm-intern/README.md` | 包装目录入口，fit verdict 速览，与已有文档的关系 | 第一次了解 llm-intern 包装 |
| `docs/llm-intern/01_truth_boundary.md` | 逐条声明真值边界分类（可以写 / 谨慎写 / 补证据后写 / 不能写 / 无法判断） | 写简历/口播前逐条检查 |
| `docs/llm-intern/02_evidence_contract.md` | 9 条核心声明的证据契约（代码:行号→测试→风险→安全措辞） | 被追问时找证据 |
| `docs/llm-intern/03_fit_verdict.md` | 按 5 个 LLM 实习方向评估项目匹配度 + 描述切换建议 | 投不同方向时切换侧重点 |
| `docs/llm-intern/04_upgrade_plan.md` | 16 项证据升级计划（半天→1天→3天→1周）+ 优先级矩阵 | 投递截止前快速补短板 |

## 历史参考

| 文档 | 定位 | 注意事项 |
| --- | --- | --- |
| `docs/plans/` | 方案和阶段计划 | 保留时间线，不替代当前面试主入口 |
| `docs/notes/` | 每轮任务复盘笔记（26 篇，5/11-5/28） | 只作为证据来源，不搬空到面试材料 |

## 推荐阅读路径

### 30 分钟速读

1. 读 `docs/interview-guide.md`，掌握项目主叙事和按岗位侧重点。
2. 读 `docs/resume-template.md`，确认三个方向各能写什么、不能写什么。
3. 读 `docs/interview-question-bank.md` 的前 10 题，避免被基础问题卡住。

### 2 小时深读

1. 读 `docs/interview-star-stories.md`，挑 3 个故事练口播。
2. 读 `docs/architecture.md`，画出 Phase 1→1.5→1.75→2→3 和 ReAct 分支。
3. 读 `docs/code-walkthrough.md`，按请求链路找代码证据。
4. 读 `docs/supervisor-main-orchestration.md`，理解召回打分和硬过滤规则。
5. 对照 `docs/notes/` 中的验证记录，补充真实测试结果。

### 投递前检查（llm-intern 路径）

1. 读 `docs/llm-intern/01_truth_boundary.md`，逐条确认简历 bullet 在 🟢/🟡 等级。
2. 读 `docs/llm-intern/03_fit_verdict.md`，按目标岗位切换项目描述侧重点。
3. 读 `docs/llm-intern/04_upgrade_plan.md`，挑半天/一天能完成的升级项快速补齐。

## 对外讲项目的统一口径

> 当前项目是学校公选课 Multi-Agent 推荐系统。系统把学生自然语言选课需求转成结构化画像和硬约束，用 MySQL、Milvus、Redis 从 500 门真实课程中召回候选，经过确定性硬约束过滤和 LLM 语义初筛后做候选内重排，最后生成可解释推荐理由。编排支持固定 Pipeline 和 ReAct 工具调用两种模式，通过 A/B 实验分流。核心思路是规则保下限、LLM 提上限。

## 写作原则

- 先写业务问题，再写架构。
- 多写"我改了什么"，少写"系统用了什么"。
- 有验证就写验证，没有验证就写"待补充"。
- 追问回答要有证据：文件、接口、测试、日志或复盘笔记。
- 按面试方向切换侧重：AI Agent / 后端工程 / 推荐系统。
