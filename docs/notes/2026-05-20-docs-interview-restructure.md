# 面试文档体系重构复盘

## 背景与问题

- 本轮要解决的问题：`docs/` 根目录下的面试、简历、架构、代码讲解和项目计划文档存在叙事重复，且部分历史电商内容容易和当前公选课 Multi-Agent 主线混在一起。
- 触发原因或用户诉求：用户要求按 interview-star-packaging、brainstorming、grill-me 三类方法，把文档重构成更清晰的面试/设计/追问体系。
- 影响范围：仅 Markdown 文档和 `tasks/todo.md`，不修改业务代码，不提交 git commit。

## 总体架构方案

- 涉及模块：`docs/interview-guide.md`、`docs/resume-template.md`、`docs/architecture.md`、`docs/code-walkthrough.md`、`docs/project-plan.md`，以及新增的 `docs/INDEX.md`、`docs/interview-star-stories.md`、`docs/interview-question-bank.md`。
- 文档分工：
  - `interview-guide.md`：面试准备主入口，负责阅读路径、主叙事和训练方式。
  - `interview-star-stories.md`：集中承载 STAR 故事、60 秒口播和可追问点。
  - `resume-template.md`：只放简历 bullet、项目标题和口播模板，减少与主入口重复。
  - `architecture.md`：保留当前架构事实，补充设计取舍、失败回退和已知限制。
  - `code-walkthrough.md`：强化从 API 入口到 Agent、召回、硬约束、流式输出的代码证据链。
  - `project-plan.md`：标注为 Legacy 电商历史规划，只解释迁移背景。
- 关键设计取舍：不搬空 `docs/notes`，只参考必要复盘事实；未知指标不编造，统一写“待补充”或明确边界。

## 细节实现

- 修改或分析的关键文件：
  - `docs/interview-guide.md`：从“面试完全指南”改为导航型主入口。
  - `docs/resume-template.md`：删除大量追问重复内容，保留三类岗位导向 bullet 和口播模板。
  - `docs/architecture.md`：补充 Phase 1.5 硬约束、SSE 流式接口、Redis 语义缓存、失败回退和可追问点。
  - `docs/code-walkthrough.md`：按执行顺序组织代码文件，并说明每段代码支撑哪个面试故事。
  - `docs/project-plan.md`：重写为 Legacy 文档，避免电商规划混入当前项目主叙事。
  - `tasks/todo.md`：追加本轮执行清单与 Review。
- 核心逻辑：把“主入口、STAR 故事、简历模板、架构事实、代码证据、追问题库、Legacy 历史参考”拆成独立文档，避免同一段话在多个文件里反复出现。
- 兼容性与风险控制：只改 Markdown；文档中对真实未验证指标保持克制，不写 CTR、P99 或高并发等无法证明的数据。

## Debug 结论

- 根因：旧文档的功能边界不清，`interview-guide.md` 和 `resume-template.md` 同时承载 STAR、追问、简历和技术亮点；`project-plan.md` 虽已标注 Legacy，但仍保留大量电商主叙事，容易误导阅读顺序。
- 排查过程：先读取 `tasks/todo.md` 和 5 个目标文档，再读取必要复盘笔记核对硬约束、流式推荐、Redis 缓存和容器导入验证事实。
- 解决方式：新增索引与素材文档，重写目标文档职责，并在 Legacy 文档中明确当前主线跳转。

## 测试与验证

- 已执行：
  - `ReadLints` 检查本轮编辑的 8 个 docs 文档，最终无 markdownlint 警告。
  - `rg "\[[^\]]+\]\([^)]+\)" docs --glob "*.md"` 检查 Markdown 链接写法，未发现本轮根目录文档中的 Markdown 链接问题。
  - `rg "^\|---|^\|----|^### 代码承担的职责$|^### 支撑的面试故事$" docs --glob "*.md"` 复查表格分隔行和重复小标题，匹配仅来自既有 `docs/notes` 历史复盘，未命中本轮编辑的根目录文档。
- 结果：本轮新增/重构文档格式检查通过；`tasks/todo.md` 仍保留历史多一级标题和重复 Review 的 markdownlint 警告，未进行全文件结构重构。
- 未执行及原因：未运行 Python 单元测试或 Docker 验证，因为本轮只改 Markdown 文档，不影响业务代码。原计划的 Python 链接解析脚本因 PowerShell 引号转义失败，未采用其结果，改用 `rg` 轻量检查。

## 经验与后续

- 本轮经验：面试文档不能把所有内容堆进一个“大而全”文件；主入口应负责导航，证据、故事、追问和简历应分层承载。
- 后续建议：
  - 如果继续完善面试材料，可以把真实演示截图、接口返回样例和测试命令单独整理成 `docs/interview-demo-checklist.md`。
  - 如果要彻底消除 `tasks/todo.md` 的 markdownlint 警告，需要单独重构历史任务文件的标题层级，不建议混入本轮文档体系重构。
