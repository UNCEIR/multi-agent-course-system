# 文档索引

本文档说明 `docs/` 根目录下文档的分工，避免面试材料、架构说明和历史规划互相重复。v1 时代的文档已按 v2 现状重写（2026-08-19）。

## 当前主线

| 文档 | 作用 | 适合什么时候读 |
| --- | --- | --- |
| `docs/interview-guide.md` | 面试准备主入口：讲法、训练路径、按岗位切换侧重点 | 第一次准备项目介绍 |
| `docs/interview-star-stories.md` | 8 个 STAR 故事（v2 业务：main_agent 路由 / 评价反幻觉 / SSE 续传 / dispatch_module / zod 错误层 / CourseFields 抽取 / live eval 兑现 / dev proxy 502） | 练项目经历表达 |
| `docs/resume-template.md` | 三个方向的简历 bullet、项目标题和口播模板（按 v2 业务重写） | 写简历或投递前 |
| `docs/interview-question-bank.md` | 28 题高频追问（v2 业务 + 跨语言/MCP 工具） | 模拟面试或自测 |
| `docs/architecture.md` | v2 总体架构：4 边界 + main_agent + 4 业务模块 + 5 MCP + 数据架构 | 讲系统设计 |
| `docs/code-walkthrough.md` | v2 代码证据链：chat/stream → main_agent → 4 业务模块代码 | 面试官要求看代码 |
| `docs/supervisor-main-orchestration.md` | v1 supervisor 在 v2 中的角色：包装为 recommend_courses tool + pipeline/react 双模式 + SSE 协议升级 | 深入讲编排实现 |

## v2 子文档（`docs/v2.0.0/`）

| 文档 | 作用 | 适合什么时候读 |
| --- | --- | --- |
| `docs/v2.0.0/plan.md` | v2 总计划（Phase 0~4 概要 + 22 个决策索引） | 理解项目演进背景 |
| `docs/v2.0.0/eval-system.md` | 评测体系总述：6 个集 + 17 份 reports + 字段契约 + 实测记录 | 讲"如何验证系统" |
| `docs/v2.0.0/frontend-architecture.md` | 前端 Next.js 16 App Router 挂载链路 + SSE 消费 + 错误反馈层 + 测试基建 | 讲前端架构 |
| `docs/v2.0.0/rag-ingest.md` | 知识库 RAG 摄入流水线（决策 6 修订） | 讲 RAG 工程实现 |
| `docs/v2.0.0/skills-tools-architecture.md` | Skills + Tools 体系 | 讲 deepagents 框架应用 |
| `docs/v2.0.0/notes/` | 各阶段复盘笔记（路 1~7 + Phase 3 live eval 兑现 + chat_intent 修复 + NLU 调优 + SSE 续传 + 错误层） | 找具体决策的演化证据 |
| `docs/v2.0.0/plans/` | 详细 phase 计划（phase-1 / phase-2 / phase-3） | 了解当时怎么定的实施步骤 |

## 仓库根文档

| 文档 | 作用 | 适合什么时候读 |
| --- | --- | --- |
| `README.md` | Quick Start（venv + docker compose + ingest）+ 基本 API + 目录结构 + 前端架构图 + 基本排查命令 | 第一次跑项目 |
| `AGENTS.md` | 仓库指令（开发必读：命令/约束/契约）—— 包含主人约束、git bash 优先、Layout、Setup、Env、Constraints、API 契约、RAG、用户上下文注入、故障排查速查 | 任何任务前 |
| `CLAUDE.md` | 详细架构与历史决策 | 深入了解背景 |

## v1 历史归档（`docs/v1.0.0/`）

仅供对照参考，**不要照搬到 v2**：
- `docs/v1.0.0/2026-05-11-course-agent-redesign.md` — v1 agent 重构历史
- `docs/v1.0.0/2026-05-16-*.md` — v1 推荐管线 + 摄入
- `docs/v1.0.0/2026-05-17-*.md` — v1 supervisor vs LangGraph + streaming SSE 设计
- `docs/v1.0.0/2026-05-18-docker-stream-recommend-phase15.md` — v1 docker

## 推荐阅读路径

### 30 分钟速读
1. 读 `docs/interview-guide.md`，掌握 v2 项目主叙事（**不是 v1 supervisor，是 main_agent 路由 4 业务模块**）和按岗位侧重点。
2. 读 `docs/resume-template.md`，确认三个方向各能写什么、不能写什么。
3. 读 `docs/interview-question-bank.md` 的前 10 题，避免被基础问题卡住。

### 2 小时深读
1. 读 `docs/interview-star-stories.md`，挑 3 个故事练口播（建议：main_agent 路由 / 评价反幻觉 / SSE 续传）。
2. 读 `docs/architecture.md`，画出 main_agent + 4 业务模块 + 5 MCP 工具的依赖关系。
3. 读 `docs/code-walkthrough.md`，按 chat/stream 请求链路找代码证据。
4. 读 `docs/supervisor-main-orchestration.md`，理解 v1 supervisor 在 v2 中作为 recommend_courses tool 的角色。
5. 读 `docs/v2.0.0/eval-system.md` + `docs/v2.0.0/notes/2026-08-18-phase3-live-eval-fulfillment.md`，了解真实端测数据。
6. 对照 `docs/v2.0.0/plan.md` 的 Phase 0~4 概要，确认每个决策的当前状态。

### 投递前检查
1. 读 `docs/resume-template.md` 末"自我检查清单"，逐条确认简历 bullet 准确性。
2. 读 `docs/interview-question-bank.md` 全部 28 题，确认每题都有"证据 + 真实边界"。
3. 确认所有量化数字（"6/6 通过" "4/4 修复" "335 单测" "127 单测" "110K tokens"）都有 eval report / 复盘笔记 支撑。

## 对外讲项目的统一口径（v2）

> 当前项目是大学校园多智能体平台，v2 升级到 **main_agent（deepagents 框架）统一入口**。学生在对话框里说"我想要 AI 相关的公选课" → main_agent 识别推荐意图 → 调 `recommend_courses` 工具（内部 v1 supervisor 5 agent 流水线）→ 流式返回 5 门课 + 理由。**教师端**说"给张三写评语" → main_agent 路由到 `dispatch_module(evaluation)` → 后端 evaluation.service 走五层反幻觉管线 → 返回评语 + 雷达图。平台还提供成绩单报告（批量 Excel → 1.html → WeasyPrint PDF）、知识库问答（学生手册 public / 个人成绩单 user 分区）、网页搜索、图像生成、PPT 生成等。核心思路是：**deepagents 框架 + 业务模块解耦 + 知识库 RAG + MCP 工具桥接**。

## 写作原则

- 先写业务问题，再写架构。
- 多写"我改了什么"，少写"系统用了什么"。
- 量化数字（通过率 / 延迟 / tokens / 单测数）必须有 eval report 链接。
- 追问回答要有证据：文件、接口、测试、日志或复盘笔记 + eval report。
- 按面试方向切换侧重：AI Agent / 后端工程 / 推荐系统 / RAG。
- v1 时代的术语（"双模式 Pipeline/ReAct" "硬约束锁死"）仍可用，但要明确**它们是 v1 supervisor 内部实现**，不是 v2 main_agent 的能力。
