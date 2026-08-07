# python/tools/ — 工具注册层与原子能力目录

## 分层

| 层 | 目录 | 内容 |
|----|------|------|
| 工具注册层 | `tools/` | ToolRegistry、CircuitBreaker、MCPClient |
| 原子能力 | `tools/*.py` | 单个 @tool 文件 |
| 子包 | `tools/documents/` | 文档解析 + 分块 |
| 子包 | `tools/recommend/` | 推荐工具（Phase 1 Step 3 实装） |

## 工具索引

| 工具 | 状态 | Phase | 类别 | .md 文档 |
|------|------|-------|------|----------|
| `list_available_skills` | `implemented` | 1 | `system/*` | [list_available_skills.md](list_available_skills.md) |
| `get_current_time` | `implemented` | 1 | `system/*` | [get_current_time.md](get_current_time.md) |
| `recommend_courses` | `stub` | 1 (Step 3) | `recommend/*` | [recommend_courses.md](recommend_courses.md) |
| `writing_assistant` | `stub` | 1 | `chat/*` | [writing_assistant.md](writing_assistant.md) |
| `web_search` | `stub` | 3 | `chat/*` | [web_search.md](web_search.md) |
| `image_generate` | `stub` | 3 | `image/*` | [image_generate.md](image_generate.md) |
| `code_interpreter` | `stub` | 3/4 | `code/*` | [code_interpreter.md](code_interpreter.md) |
| `mindmap_generator` | `stub` | 3/4 | `mindmap/*` | [mindmap_generator.md](mindmap_generator.md) |
| `compute_weighted_grade` | `stub` | 2 | `report/*` | [compute_weighted_grade.md](compute_weighted_grade.md) |
| `parse_document` | `stub` | 1 | `documents/*` | [documents/parser.md](documents/parser.md) |
| `chunk_document` | `stub` | 1 | `documents/*` | [documents/chunker.md](documents/chunker.md) |

## 基础设施

| 组件 | 状态 | Phase | .md 文档 |
|------|------|-------|----------|
| `ToolRegistry` | `implemented` | 1 | [registry.md](registry.md) |
| `CircuitBreaker` | `implemented` | 1 | [circuit_breaker.md](circuit_breaker.md) |
| `MultiServerMCPClient` | `stub` | 3 | [mcp_client.md](mcp_client.md) |

## 与 skills/ 的区别

| | `tools/`（原子能力） | `skills/`（技能文档） |
|---|---|---|
| 内容 | Python `@tool` 代码 | SKILL.md 说明文档 |
| 注册 | ToolRegistry | SkillsMiddleware 自动扫描 |
| 使用 | Agent 直接调用执行 | Agent 阅读后按步骤执行 |
| 机制 | 工具调用（tool call） | 渐进式披露（先摘要后全文） |

## 注册方式

所有工具在 `runtime.init()` 中通过 `ToolRegistry.register_many()` 批量注册，见 `python/agent/runtime.py`。主 agent 从 `tool_registry.get_all()` 获取工具列表。