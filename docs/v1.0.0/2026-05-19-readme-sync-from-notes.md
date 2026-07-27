# README 根据近期 notes 同步优化

## 背景与问题

- 用户要求仅更新 `README.md`，依据 `docs/notes` 近期迭代补充说明，并整体写得更简洁。
- 原 README 偏长，且未覆盖 Phase 1.5 硬约束、语义缓存、流式 API、`ECOM_HTTPX_VERIFY_SSL`、MySQL 3307 映射等已实现能力。

## 总体架构方案

- 保留「快速启动 → 架构 → API → 排错 → 文档」主线，删重复段落与冗长示例。
- 从 notes 抽取可对外说明的契约：编排阶段、硬/软约束、Redis 精确+语义缓存、可观测字段、环境坑位。

## 细节实现

- **仅修改** `README.md`。
- 合并原「项目解决什么问题」「核心能力」「Redis」「数据库」为更短的「架构概览」「核心模块」「数据与分块」。
- 更新 Mermaid 含 Phase 1.5；API 表增加 `/recommend/stream`；FAQ 改为表格。
- 补充 `AGENTS.md`、`docs/notes/` 索引；.env 双文件与 LLM/Embedding 双协议说明。

## Debug 结论

- 无代码 bug；属文档对齐任务。

## 测试与验证

- 未执行自动化测试（仅 Markdown）。
- 已与 `python/main.py` 路由、`docker-compose.python.yml` 端口、`AGENTS.md` 及 2026-05-18/19 notes 人工对照。

## 经验与后续

- README 宜与 `AGENTS.md` 分工：README 面向上手与架构一览，细节与踩坑以 `AGENTS.md` + `docs/notes/` 为准。
- 若再增加 `/stream_recommend` 等别名路由，需同步 API 表。
