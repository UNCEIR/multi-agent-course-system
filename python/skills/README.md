# v2 Skills 技能目录（模块化结构）

该目录存放 **SKILL.md 技能文档**（遵循 Agent Skills Specification + 模块化目录规范），由 deepagents `SkillsMiddleware` 自动加载。

## 什么是 Skills

Skills 是 deepagents 的「渐进式披露」技能机制：

- 每个技能 = 一个子目录 + `SKILL.md` 主入口（YAML frontmatter + 索引）
- `create_deep_agent(skills=["/skills/"])` 时自动扫描加载（**只扫描一级子目录中含 SKILL.md 的目录**，`_shared/` 不会被加载为独立技能）
- SkillsMiddleware 解析 frontmatter → 注入 system prompt（名称 + 描述 + allowed_tools）
- Agent 识别到匹配技能后，按 SKILL.md 的 Architecture 路由清单用 `read_file` 渐进加载子模块

## 模块化目录规范（SKILL.md 变目录，逻辑下沉）

```
skills/<skill-name>/
├── SKILL.md              # 主入口：frontmatter（不变）+ Description + Trigger + Architecture（[Load] 路由清单）
├── rules/                # 边界防守：约束/纪律（防幻觉、身份、兜底、格式）
├── commands/             # 执行步骤：触发场景、流程顺序、工具调用序列
└── scripts/              # 编排契约示例：多工具调用序列（不重复单工具 docstring）
```

- **加载约定**：SKILL.md 用 `[Load Rules: xxx](./rules/xxx.md)` / `[Load Command: xxx](./commands/xxx.md)` / `[Load Script: xxx](./scripts/xxx.md)` 标记引导 agent 按需 read_file（与 SkillsMiddleware 渐进披露兼容，省 token）
- **共享规则**：`skills/_shared/rules/`（identity / facts / fallback / grounding），各 skill 用相对路径 `../_shared/rules/*.md` 引用——该目录无 SKILL.md，不会被扫描为独立技能
- **scripts/ 边界**：只放"多工具编排序列示例"（端到端调用 JSON），单工具参数以工具 docstring 为准——避免与 tools/ 注释重复
- **能力分离**：skills/ 只放指令文档；真实执行能力一律在 `tools/`（@tool 原子能力）

## 与 tools/ 的区别

| | `tools/`（原子能力） | `skills/`（技能文档） |
|---|---|---|
| 内容 | Python `@tool` 代码 | SKILL.md 模块化指令文档 |
| 注册 | ToolRegistry（`tools/registry.py`） | SkillsMiddleware 自动扫描 |
| 使用 | Agent 直接调用执行 | Agent 阅读后按步骤执行 |
| 机制 | 工具调用（tool call） | 渐进式披露（先摘要后按需加载子模块） |

## 技能一览（模块化状态）

| 技能 | Phase | 状态 | 子模块 | 对应 tool(s) |
|-----|-------|------|--------|-------------|
| `recommend-courses` | 1 | ✅ 实装（模块化） | rules×3 + commands×3 + scripts×1 | `tools/recommend/` |
| `document-ingestion` | 1 | ✅ 实装（模块化） | rules×1 + commands×1 + scripts×1 | `tools/documents/` |
| `report-generation` | 2 | ✅ 实装（模块化） | rules×1 + commands×3 + scripts×1 | `tools/report/` |
| `evaluation-writing` | 2 | ✅ 实装（模块化） | rules×1 + commands×2 + scripts×1 | `tools/evaluation/` |
| `web-search` | 2 | ✅ 实装（模块化） | commands×1 + scripts×1 | `tools/chat/web_search.py` |
| `image-generation` | 2 | ✅ 实装（模块化） | rules×1 + commands×2 + scripts×2 | `tools/image/` |
| `writing` | 2 | ✅ 实装（模块化） | rules×1 + commands×1 + scripts×1 | `tools/chat/writing_assistant.py` |
| `knowledge-query` | 3 | ✅ 实装（模块化） | rules×1 + commands×1 + scripts×1 | `tools/knowledge/` |
| `deep-thinking` | 3 | ✅ 实装（模块化） | commands×1 | 纯推理 |
| `ppt-generation` | 3 | ⏳ 骨架（模块化占位，PPT 后续 phase） | rules×1 + commands×1 + scripts×1 | `ppt_generate`（待实装） |

共享规则：`_shared/rules/{identity, facts, fallback, grounding}.md`
