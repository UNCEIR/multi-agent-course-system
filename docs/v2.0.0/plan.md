# v2.0.0 实施总计划

> 本文件是 v2.0.0 升级的**总计划**，按 Phase 概要组织。具体设计决策与论证细节见 `notes/`，每个 Phase 的**详细实施计划**将单独生成（见"后续步骤"），再据详细计划分阶段编码。
>
> 维护：本文件只记 Phase 级概要与索引，决策细节变更请同步 `notes/` 与对应 Phase 详细 plan。

## 背景

- **v1.0.0 现状**：学校公选课 Multi-Agent 推荐系统已工作（固定 Pipeline + ReAct 双模式、SupervisorOrchestrator、MySQL+Milvus+Redis、7 个 ReAct 工具、A/B 实验）。本质是"一个推荐接口 + 简陋 RAG"，多 agent 活性不足、项目深度不够。
- **v2.0.0 愿景**（见 `需求.md`）：新业务广度 + 知识库基础设施 + Agent 工程深度 + Skills 系统 + 跨语言 + 框架选型。
- **目标**：先建平台基座，用"成绩单报告 + 评价寄语"两个学生场景验证。

## 设计决策索引（细节见 notes）

15 个决策 + 智能体重构已定稿，详见：
- `notes/2026-07-27-设计决策问答记录.md` —— 决策问答记录（问题/选项/用户选择）
- `notes/2026-07-28-设计决策补充说明.md` —— 决策补充论证（决策 2/6/8 + 决策 5 修订 + 智能体重构等）

**决策速览**：
| # | 决策 | 选择 |
|---|------|------|
| 1 | 首要交付物 | 平台基座 + 成绩单报告验证 |
| 2 | 编排基座 | deepagents（A+B 统一，建在 LangGraph 之上） |
| 3 | 框架 | deepagents |
| 4 | v1 共存 | 包装为 subgraph，暴露为 tool |
| 5 | 成绩单报告 | 批量 Excel→1.html 模板→WeasyPrint PDF（每学生独有链接） |
| 6 | MinIO/文档流水线 | 双角色 + API 化摄入 + 通用知识 Q&A；KB 走 FastGPT 二次开发 |
| 7 | Skills 系统 | 原生 tools + Jinja2 HTML→WeasyPrint PDF |
| 8 | 跨语言 TS | MCP 桥接（v2 先接 FastGPT mcp_server） |
| 9 | 报告获取推荐 | 共享 tool `recommend_courses` |
| 10 | 路由 | 混合入口 `/recommend`+`/report`+`/evaluation`+`/chat` |
| 11+12 | 可靠性 | deepagents 内置 + v1 + 源码模式 |
| 13 | API 端点 | `/report` `/evaluation` `/chat` `/documents/upload` 保留 `/recommend` |
| 14 | 课程富化 | MySQL 结构化（1.html 仅结构参考，实际大学公选课） |
| 15 | 迁移 | POC 先行 + 4 阶段 |

**智能体重构**：成绩统计智能体（`/report`，报告卡 + 成绩记载功能 + 流式评价叙述）+ 评价寄语 agent（`/evaluation`，comment_type 四种驱动）。两个独立智能体，对话不共享。

## Phase 概要

### Phase 0：deepagents POC（go/no-go 门）—— ✅ GO（2026-07-29）
- **目标**：验证 deepagents + 中转站（`one.zhique.cn` ChatOpenAI）+ Docker 兼容
- **交付**：POC 脚本（最小 main agent + 1 tool，经中转站调用）在 Docker 内跑通
- **门控**：失败 → 回退决策 2 备选（LangGraph 混合 / OpenAI Agents SDK）
- **结果**：三轴全绿（deepagents 0.6.12 可用 / 中转站 tool-calling 双向兼容 / Docker 构建运行通过）；v1 回归 44 通过 3 预存失败（A/B 路由问题，非依赖升级回归，见详细计划 §4.1）。**GO，进入 Phase 1**
- **详细 plan**：`notes/2026-07-29-phase-0-deepagents-poc详细计划.md`（已生成并执行）

### Phase 1：平台基座
- **目标**：搭建 deepagents 主 agent + tool 注册框架 + v1 包装 + MinIO + 文档流水线 + Skills 注册
- **交付**：
  - deepagents 主 agent + tool/subagent 注册表（Pydantic，MCP-ready）
  - v1 推荐链路包装为 `recommend_courses` tool（LangGraph subgraph）
  - MinIO 双角色（源文档 + 报告 artifact）
  - 文档流水线：走 FastGPT KB 二次开发（HTTP+MCP 调用）+ Python CSV/PDF/doc 解析兜底
  - Skills 注册层（原生 tool + MCP-ready）
- **验证**：`/recommend` 仍工作；文档上传→MinIO+MySQL/Milvus 入库
- **详细 plan**：`plans/phase-1-platform-base.md`（待生成）

### Phase 2：报告 + 评价寄语场景（MVP 主交付）
- **目标**：两个学生场景智能体跑通
- **交付**：
  - **成绩统计智能体**（`/report`）：批量 Excel→单科 JSON→学生 JSON→Python 加权复合统计 + 填 1.html Jinja2 模板→WeasyPrint PDF（每学生独有下载链接）+ 成绩记载功能（score JSON→comment）+ 流式评价叙述
  - **评价寄语 agent**（`/evaluation`）：输入 studentList JSON（comment_type 四种 + teacherSubjectiveEvaluation + scoreList）→ LLM 按 comment_type 生成 comment
  - 前端两个独立 agent 页面
- **验证**：`/report` 返回每学生 PDF 链接、加权正确；`/evaluation` 返回 comment、数值引用正确；两 agent 独立对话不共享
- **详细 plan**：`plans/phase-2-report-evaluation.md`（待生成）

### Phase 3：扩展
- **目标**：TS MCP 桥接 + `/chat` 统一入口 + 通用知识 Q&A + 可靠性加固
- **交付**：
  - 二次开发 FastGPT `mcp_server`，Python MCP client 接入
  - `/chat` 主 agent 路由 [推荐 tool | 报告 | 评价寄语 | query_knowledge]
  - 主 agent 通用知识 Q&A（`query_knowledge` tool）+网页搜搜mcp工具搜索能力+fastgpt的mcp
  - 可靠性加固（compaction、subagent 隔离、circuit breaker、checkpointing）
- **验证**：`/chat` 路由正确；MCP 调通 FastGPT app；compaction/circuit breaker 生效
- **详细 plan**：`plans/phase-3-extensions.md`（待生成）

## 待决开放项

1. **Excel→JSON 解析方式**：openpyxl（格式固定）vs LLM 提炼（格式多变）——需看实际 Excel 样本
2. **FastGPT KB 存储拓扑**：自带 Mongo vs 复用 MySQL/Milvus/MinIO——Phase 1 集成时研究配置再决
3. **种子文档集**：大小/格式/来源（内容与大学挂钩）

## 后续步骤

1. ✅ 总 plan 完成（本文件）
2. ✅ 决策笔记同步（07-27/07-28）
3. ⏭ **按每个 Phase 单独生成详细 plan.md**（`plans/phase-N-*.md`，含具体文件、函数、步骤）
4. ⏭ 据详细 plan **分阶段编码**，每阶段验证闭环跑通后再进下一阶段
5. Phase 0 POC 优先（go/no-go 门）——deepagents 兼容性是最大未验证风险
