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
| 10 | 路由 | 混合入口，统一 main agent 对话框 + 独立模块页 |
| 11+12 | 可靠性 | deepagents 内置 + v1 + 源码模式 |
| 13 | API 端点 | `/chat` 统一入口 + `/report` `/evaluation` `/documents/upload` 保留 `/recommend` |
| 14 | 课程富化 | MySQL 结构化（1.html 仅结构参考，实际大学公选课） |
| 15 | 迁移 | POC 先行 + 4 阶段 |

**智能体重构**：成绩统计智能体（`/report`，报告卡 + 成绩记载功能 + 流式评价叙述）+ 评价寄语 agent（`/evaluation`，comment_type 四种驱动）。两个独立智能体，对话不共享。

## 新增决策（2026-08-07 定稿）

### 决策 16：前端页面架构 —— 统一对话框 + 独立模块页
- **MainPage**（统一对话框入口）：main agent 提供 chat（知识库问答 + 网页搜索 + 深度思考 + 论文写作）+ recommend（路由到推荐 skill）+ report（路由到报告模块）+ evaluation（路由到评价模块）
- **ImageGeneratePage**（独立页）：图片生成多模态插件，独立于 main agent 的专门页面
- **PPTGeneratePage**（独立页）：PPT 生成系统，独立于 main agent 的专门页面
- **理由**：图片生成和 PPT 生成是深度交互场景（需要画布/预览/参数配置），不适合嵌入对话流；而 recommend/report/evaluation 是对话式查询场景，适合在对话中展示结果

### 决策 17：Main Agent 能力边界
- **chat agent 核心能力**：知识库问答（学生手册.pdf 知识库）+ 网页搜索（tavily）+ 深度思考（独立思考模式）+ 论文写作（writing_assistant tool）
- **独立模块**：课程推荐、报告生成、评价寄语、PPT 生成 → chat agent 仅负责意图识别 + 路由
- **图片生成**：从 chat agent 解耦，独立 Page 组件，经 MCP 调图片生成服务
- **理由**：职责分离 —— 对话式查询在 chat 中完成，深度交互在独立页面中完成

### 决策 18：论文写作功能
- main agent 新增 `writing_assistant` tool，LLM 驱动，支持多体裁/多风格论文写作
- 在 chat 对话框中自然交互：用户提出写作需求 → main agent 识别意图 → 调用 writing_assistant tool → 对话中生成论文
- **理由**：论文写作是对话式创作过程，适合在 chat 中完成，不需要独立页面

## Phase 概要

### Phase 0：deepagents POC（go/no-go 门）—— ✅ GO（2026-07-29）
- **目标**：验证 deepagents + 中转站（`one.zhique.cn` ChatOpenAI）+ Docker 兼容
- **交付**：POC 脚本（最小 main agent + 1 tool，经中转站调用）在 Docker 内跑通
- **门控**：失败 → 回退决策 2 备选（LangGraph 混合 / OpenAI Agents SDK）
- **结果**：三轴全绿（deepagents 0.6.12 可用 / 中转站 tool-calling 双向兼容 / Docker 构建运行通过）；v1 回归 44 通过 3 预存失败（A/B 路由问题，非依赖升级回归，见详细计划 §4.1）。**GO，进入 Phase 1**
- **详细 plan**：`notes/2026-07-29-phase-0-deepagents-poc详细计划.md`（已生成并执行）

### Phase 1：平台基座
- **目标**：搭建 deepagent 主 agent + tool 注册框架 + v1 包装 + MinIO + 文档流水线 + Skills 注册 + 记忆机制
- **交付**：
  - deepagents 主 agent + tool/subagent 注册表（Pydantic，MCP-ready），tools详情放在`python/tools/`。
  - v1 推荐链路包装为 `recommend_courses` tool（LangGraph subgraph）
  - MinIO 双角色（源文档 + 报告 artifact）
  - 文档流水线：走 FastGPT KB 二次开发（HTTP+MCP 调用）+ Python CSV/PDF/doc 解析兜底
  - Skills 技能文档目录（SKILL.md，deepagents SkillsMiddleware 自动加载），`python/skills/`已初始化完毕
  - **记忆管理提前实装 demo**：`MemoryMiddleware`（长期记忆，FilesystemBackend 真实 `AGENTS.md`）+ `SummarizationMiddleware`（compaction，阈值对齐决策 11 `contextWindow-13000`/`keepRecentTokens=20000`，落盘 `/conversation_history/{thread_id}.md`）+ `FilesystemMiddleware`（大 tool result 落盘）+ `SkillsMiddleware`（渐进式 skill 披露）+ `SqliteSaver`（thread_id 跨会话恢复，本地 sqlite），实装 `POST /api/v1/chat` 端点
  - 前端三个 Page 组件：`MainPage`（chat 统一入口）、`ImageGeneratePage`（图片生成）、`PPTGeneratePage`（PPT 生成）
  - 论文写作功能：`writing_assistant` tool 在 main agent 中
- **验证**：`/recommend` 仍工作；文档上传→MinIO+MySQL/Milvus 入库；`/chat` 多轮对话 + 记忆 + compaction 正常
- **详细 plan**：`plans/phase-1-platform-base.md`（已生成，2026-08-05 grill-me 沉淀 33 个子决策）+ `plans/phase-1-coding-plan.md`（记忆机制实装计划，2026-08-07）

### Phase 2：报告 + 评价寄语场景（MVP 主交付）
- **目标**：两个学生场景智能体跑通
- **交付**：
  - **成绩统计智能体**（`/report`）：批量 Excel→单科 JSON→学生 JSON→Python 加权复合统计 + 填 1.html Jinja2 模板→WeasyPrint PDF（每学生独有下载链接）+ 成绩记载功能（score JSON→comment）+ 流式评价叙述
  - **评价寄语 agent**（`/evaluation`）：输入 studentList JSON（comment_type 四种 + teacherSubjectiveEvaluation + scoreList）→ LLM 按 comment_type 生成 comment
  - **前端**：MainPage 中嵌入 report/evaluation 对话入口，结果在对话框中展示
- **验证**：`/report` 返回每学生 PDF 链接、加权正确；`/evaluation` 返回 comment、数值引用正确
- **详细 plan**：`plans/phase-2-report-evaluation.md`（待生成）

### Phase 3：扩展 + PPT 场景
- **目标**：TS MCP 桥接 + 通用知识 Q&A + 可靠性加固 + PPT 生成系统
- **交付**：
  - 二次开发 FastGPT `mcp_server`，Python MCP client 接入
  - 主 agent 通用知识 Q&A（`query_knowledge` tool，学生手册 PDF 种子数据源）+ 网页搜索 MCP 工具（tavily）+ FastGPT MCP
  - 可靠性加固（compaction、subagent 隔离、circuit breaker、checkpointing）
  - **PPT 生成系统**（参考 OpenMAIC）：大学生课程小组 PPT 汇报场景，AI 生成 PPT 微课件自动生成系统（多 agent 协作，支持画布/动画/PPT，用户输入提示词选择类型如期末 PPT 课设/小组汇报）；`ppt_generate` 独立 Page 组件，DSL→PPTX 渲染（参考 OpenMAIC `pptxgenjs` + `lib/export/use-export-pptx.ts`）
  - **图片生成系统**：`image_generate` 独立 Page 组件，经 MCP 调图片生成服务
  - 记忆管理 Phase 3 待做：① 切 `RedisSaver`（`langgraph-checkpoint-redis` 已加 requirements，复用 v1 `redis_url`，自定义 namespace）；② summary_prompt 完全对齐决策 11 五字段；③ memory 提取用 forked subagent；④ consolidation；⑤ SSE 流式 `/chat`；⑥ 工具链路断裂兜底演示
- **验证**：`/chat` 路由正确；MCP 调通 FastGPT app；compaction/circuit breaker 生效；PPT 生成可用；图片生成可用
- **详细 plan**：`plans/phase-3-extensions.md`（待生成）

### Phase 4：深度增强（体现工程深度）
- **目标**：端到端评测 + monitor 在线表现 + 检索指标驱动调优 + 多模态 + agent harness 深化 + 兜底演示
- **交付**：
  - **端到端 agent 评测**：意图识别准确率、工具调用成功率、检索召回率/精度/F1/NDCG、幻觉率、端到端延迟；评测测试集 + 指标看板（复用 v1 `/metrics` + `prometheus-client`）
  - **monitor agent 在线表现**：`/metrics` 监控退化/异常 → 指标驱动检索策略调优（top_k/语义缓存阈值/分块策略/rerank 权重）
  - **多模态 LLM 接入**：通用 agent 加入图谱识别/图片识别（如课程图谱可视化、成绩趋势图识别）
  - **插件市场**：用户在 FastGPT 侧自建 agent/KB/插件，Python 主 agent 经 MCP 动态发现调用
  - **agent harness 深化**：think→act→observe 循环可视化、工具调用链路追踪（OpenTelemetry）、subagent 委派树可视化、checkpointing 恢复演示
  - **工具链路断裂兜底演示**：故意断工具（FastGPT KB 不可用）→ circuit breaker 熔断 → Python 兜底脚本 → 部分结果保留 → checkpointing 恢复 → 降级运行
  - **幻觉兜底演示**：LLM 试图自算统计 → schema 约束拦截 → 引用文件数值 → compaction 摘要落盘 → subagent 隔离
- **验证**：评测指标可观测；多模态可用；插件动态发现；harness 可视化；断裂/幻觉兜底演示通过
- **详细 plan**：`plans/phase-4-depth-enhancement.md`（待生成）

## 贯穿原则（跨 Phase 持续遵守）

### 原则 1：agent 编排 vs 能力分离
- `agent/` 只做编排（路由/委派/调度/对话管理），不持有具体能力实现。
- `tools/` 放原子能力（PDF 解析、分块、向量化、渲染、搜索、插件），以 `@tool` 装饰器 + Pydantic `args_schema` 暴露。**ToolRegistry/CircuitBreaker/MCPClient 也放 `tools/`**（工具注册发现层）。
- `skills/` 放 **SKILL.md 技能文档**（deepagents SkillsMiddleware 自动加载的渐进式披露指令），每个技能一个子目录 + `SKILL.md`，不是 Python 代码层。
- 原则：每个 tool 独立 `.md` 说明文档，每个 skill 独立 `SKILL.md` 指令文档，CLAUDE.md 只记索引。

### 原则 2：deepagents 优先，FastGPT 拖拽并存
- Phase 1-2 先用 deepagents 框架编码实现（`create_deep_agent` + `@tool` + ToolNode）。
- Phase 3 起引入 FastGPT 拖拽构建，作为同业务的备选/增强实现。
- 两者不冲突，通过 feature flag 切换（`config/settings.py` 中 `knowledge_provider` 等开关）。
- 拖拽产物（FastGPT app/workflow）对应 Python tool 的配置映射，在 `tools/` 中维护映射表。

### 原则 3：通用 chat 插件体系（2026-08-07 修订）
- main agent（MainPage 对话框）内嵌能力：
  - **知识库问答**：学生手册.pdf 知识库查询
  - **网页搜索**：tavily 实时搜索
  - **深度思考**：独立思考模式分析复杂问题
  - **论文写作**：`writing_assistant` tool，支持多体裁/多风格
  - **课程推荐**：路由到 `recommend-courses` skill
  - **报告生成**：路由到 report 模块
  - **评价寄语**：路由到 evaluation 模块
- 独立 Page 组件（非对话框内）：
  - **图片生成**：`ImageGeneratePage`，经 MCP 调图片生成服务
  - **PPT 生成**：`PPTGeneratePage`，DSL→PPTX 渲染管线
- 插件走 ToolRegistry 注册 + allowlist 门控，支持 MCP 动态发现接入外部插件。

### 原则 4：前端页面架构（2026-08-07 新增）
- 三个 Page 组件：
  - `MainPage`：统一对话框入口，承载 chat（知识库问答+网页搜索+深度思考+论文写作）+ recommend + report + evaluation
  - `ImageGeneratePage`：图片生成独立页面（深度交互场景，需画布/参数配置）
  - `PPTGeneratePage`：PPT 生成独立页面（深度交互场景，需画布/动画/模板选择）
- 导航栏：左侧菜单栏或顶部 Tab 切换三个页面
- v1 兼容：保留 `/recommend` 独立推荐页作为快速入口

## 待决开放项

1. **Excel→JSON 解析方式**：openpyxl（格式固定）vs LLM 提炼（格式多变）——需看实际 Excel 样本
2. **FastGPT KB 存储拓扑**：自带 Mongo vs 复用 MySQL/Milvus/MinIO——Phase 1 集成时研究配置再决
3. **种子文档集**：大小/格式/来源（内容与大学挂钩）

## 后续步骤

1. ✅ 总 plan 完成（本文件）
2. ✅ 决策笔记同步（07-27/07-28）
3. ✅ CLAUDE.md 深度要求 + plan 模式自动参考规则
4. ⏭ **按每个 Phase 单独生成详细 plan.md**（`plans/phase-N-*.md`，含具体文件、函数、步骤）
5. ⏭ 据详细 plan **分阶段编码**，每阶段验证闭环跑通后再进下一阶段
6. Phase 0 POC 优先（go/no-go 门）——deepagents 兼容性是最大未验证风险