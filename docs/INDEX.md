# 文档索引

本文档说明 `docs/` 根目录下文档的分工，避免面试材料、架构说明和历史规划互相重复。

## 当前主线

| 文档 | 作用 | 适合什么时候读 |
| --- | --- | --- |
| `docs/interview-guide.md` | 面试准备主入口，给出讲法、训练路径和避坑清单 | 第一次准备项目介绍 |
| `docs/interview-star-stories.md` | STAR 故事库，包含 60 秒口播、3 分钟展开素材和可追问点 | 练项目经历表达 |
| `docs/resume-template.md` | 简历 bullet、项目标题和口播模板 | 写简历或投递前 |
| `docs/interview-question-bank.md` | 高频追问、推荐回答、代码/验证证据和真实边界 | 模拟面试或自测 |
| `docs/architecture.md` | 当前公选课 Multi-Agent 架构事实、设计取舍和限制 | 讲系统设计 |
| `docs/code-walkthrough.md` | 从入口到 Agent、召回、硬约束、流式输出的代码证据链 | 面试官要求看代码 |

## 历史参考

| 文档 | 定位 | 注意事项 |
| --- | --- | --- |
| `docs/plans/` | 方案和阶段计划 | 保留时间线，不替代当前面试主入口 |
| `docs/notes/` | 每轮任务复盘笔记 | 只作为证据来源，不搬空到面试材料 |

## 推荐阅读路径

### 30 分钟速读

1. 读 `docs/interview-guide.md`，掌握项目主叙事。
2. 读 `docs/resume-template.md`，确认哪些能写进简历。
3. 读 `docs/interview-question-bank.md` 的前 10 题，避免被基础问题卡住。

### 2 小时深读

1. 读 `docs/interview-star-stories.md`，挑 2 个故事练口播。
2. 读 `docs/architecture.md`，画出 Phase 1、Phase 1.5、Phase 2、Phase 3。
3. 读 `docs/code-walkthrough.md`，按请求链路找代码证据。
4. 对照 `docs/notes/` 中的验证记录，补充真实测试结果。

## 对外讲项目的统一口径

> 当前项目是学校公选课 Multi-Agent 推荐系统。它把学生自然语言选课需求转成结构化画像和硬约束，再用 MySQL、Milvus、Redis 从真实课程数据中召回候选，之后做候选内重排、硬约束/风险检查和推荐理由生成。历史电商规划只作为迁移背景，不作为当前主线。

## 写作原则

- 先写业务问题，再写架构。
- 多写“我改了什么”，少写“系统用了什么”。
- 有验证就写验证，没有验证就写“待补充”。
- Legacy 内容只说明来源，不混进当前主叙事。
- 追问回答要有证据：文件、接口、测试、日志或复盘笔记。
