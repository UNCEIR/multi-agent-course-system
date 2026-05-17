# write-note-for-project Skill 创建复盘

## 背景与问题

- 本轮用户希望创建一个名为 `write-note-for-project` 的 Cursor Skill，把“每次对话读取 todo 并输出项目复盘笔记”的流程固化下来。
- 目标输出位置是 `E:\Agent\multi-agent-course-system\docs\notes`，笔记格式为 Markdown。
- 该需求属于工作流规范沉淀，不涉及业务运行逻辑。

## 总体架构方案

- 采用项目级 Skill，放置在 `.cursor/skills/write-note-for-project/SKILL.md`，使该能力随仓库生效。
- Skill 通过 frontmatter 声明 `name` 和 `description`，描述中覆盖触发场景：debug、实现、测试、评审、分析和项目任务复盘。
- 主体按“执行时机、工作流程、笔记模板、质量要求”组织，避免把复盘逻辑散落在对话约定里。

## 细节实现

- 新增文件：`.cursor/skills/write-note-for-project/SKILL.md`。
- 保留用户给出的原始要求作为“用户要求原文”，避免改变核心语义。
- 工作流程要求先读取 `tasks/todo.md`，如根目录存在 `todo.md` 也一并读取；随后根据真实执行情况写入 `docs/notes/`。
- 模板要求覆盖背景问题、总体架构方案、细节实现、Debug 结论、测试验证、经验与后续。
- 质量要求明确禁止编造测试结果，并提醒避免记录密钥、令牌和完整 `.env` 内容。

## Debug 结论

- 本轮没有业务 bug 或运行时故障。
- 排查重点是项目中是否已有 `.cursor/skills/**/SKILL.md`，结果为当前仓库尚无项目级 Skill。
- 已创建缺失的 Skill 目录和主文件。

## 测试与验证

- 已读取 `tasks/todo.md`，确认本轮遵守项目复盘前置上下文要求。
- 已读取生成后的 `.cursor/skills/write-note-for-project/SKILL.md`，确认内容写入成功。
- 已执行 `ReadLints` 检查该 Skill 文件，结果为未发现 linter 错误。
- 未执行 Python 单元测试；原因是本轮只新增 Cursor Skill 文档，不涉及 Python 业务代码。

## 经验与后续

- Skill 的描述需要同时写清“做什么”和“何时使用”，否则后续自动触发不稳定。
- 对用户提供的规范性原文，应在 Skill 中保留原文，再补充可执行流程和验证清单。
- 后续如果要把该流程变成强制仓库规则，可以再同步到 `.cursor/rules/`，但本轮仅按用户要求创建 Skill。
