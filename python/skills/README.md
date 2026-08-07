# v2 Skills 技能目录

该目录存放 **SKILL.md 技能文档**（遵循 Agent Skills Specification），由 deepagents `SkillsMiddleware` 自动加载。

## 什么是 Skills

Skills 是 deepagents 的「渐进式披露」技能机制：

- 每个技能 = 一个子目录 + `SKILL.md` 文件（YAML frontmatter + Markdown 说明）
- `create_deep_agent(skills=["/skills/"])` 时自动扫描加载
- SkillsMiddleware 解析 frontmatter → 注入 system prompt（名称 + 描述 + allowed_tools）
- Agent 识别到匹配技能后，用 `read_file` 读完整 SKILL.md，按步骤执行

## 与 tools/ 的区别

| | `tools/`（原子能力） | `skills/`（技能文档） |
|---|---|---|
| 内容 | Python `@tool` 代码 | SKILL.md 说明文档 |
| 注册 | ToolRegistry（`tools/registry.py`） | SkillsMiddleware 自动扫描 |
| 使用 | Agent 直接调用执行 | Agent 阅读后按步骤执行 |
| 机制 | 工具调用（tool call） | 渐进式披露（先摘要后全文） |

## Phase 1 技能清单（已实装）

- `recommend-courses/SKILL.md` — 推荐课程流程（allowed_tools: `recommend_courses`）
- `document-ingestion/SKILL.md` — 文档摄入流程（allowed_tools: `parse_document`, `chunk_document`）

## Phase 2 技能骨架（待实装）

- `report-generation/SKILL.md` — 成绩单报告生成（allowed_tools: `compute_weighted_grade`）
- `evaluation-writing/SKILL.md` — 评价寄语生成（allowed_tools: `compute_weighted_grade`）

## Phase 3 技能骨架（待实装）

- `knowledge-query/SKILL.md` — 知识库问答（学生手册，纯检索）
- `web-search/SKILL.md` — 网页搜索（allowed_tools: `web_search`）
- `deep-thinking/SKILL.md` — 深度思考（纯推理，无 tool）
- `writing/SKILL.md` — 论文写作（allowed_tools: `writing_assistant`, `web_search`）
- `ppt-generation/SKILL.md` — PPT 生成（allowed_tools: `web_search`）

## 技能一览

| 技能 | Phase | 状态 | allowed_tools | 对应 tool(s) |
|-----|-------|------|---------------|-------------|
| `recommend-courses` | 1 | ✅ 实装 | `recommend_courses` | `tools/recommend/recommend_courses.py` |
| `document-ingestion` | 1 | ✅ 实装 | `parse_document, chunk_document` | `tools/documents/` |
| `report-generation` | 2 | ⏳ 骨架 | `compute_weighted_grade` | `tools/report/compute_weighted_grade.py` |
| `evaluation-writing` | 2 | ⏳ 骨架 | `compute_weighted_grade` | `tools/report/compute_weighted_grade.py` |
| `knowledge-query` | 3 | ⏳ 骨架 | （无） | 知识库检索 |
| `web-search` | 3 | ⏳ 骨架 | `web_search` | `tools/chat/web_search.py` |
| `deep-thinking` | 3 | ⏳ 骨架 | （无） | 纯推理 |
| `writing` | 3 | ⏳ 骨架 | `writing_assistant, web_search` | `tools/chat/` |
| `ppt-generation` | 3 | ⏳ 骨架 | `web_search` | 多 agent 协作 |
