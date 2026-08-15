# 长期记忆文件（系统级）

> 本文件是**系统级静态记忆**：项目背景、技能索引与记忆使用指导。
> **用户级记忆（偏好/事实/决定）一律写入 `chat_memory_entries` 表**（按 user_id 隔离，
> 由记忆提取管线自动沉淀），不写入本文件——本文件的写回已被 FilesystemPermission 代码级禁止。

## 项目背景

- 大学校园多智能体平台（v2.0.0）：统一 deepagent 工厂（`agent/main/factory.py`）
- 四个业务智能体：chat（统一对话入口）/ recommend（公选课推荐）/ report（教师端成绩单批量生成）/ evaluation（教师端评价生成 → 学生端同步）
- 工具注册走 ToolRegistry（`tools/registry.py`），能力原子化在 `tools/` 子包
- 技能文档在 `skills/*/SKILL.md`，SkillsMiddleware 渐进式加载
- 知识库：学生手册（public 分区）+ 个人成绩单（user 分区，脱敏），Milvus `document_chunks`

## 技能索引

- `recommend-courses`：公选课个性化推荐（recommend_courses 一键工具）
- `report-generation`：教师端成绩单批量生成（inspect_score_excels / render_report_batch）
- `evaluation-writing`：学业评价（快照→维度→雷达→评语，反幻觉五层）
- `knowledge-query`：知识库问答（query_knowledge）
- `web-search`：网页搜索（MCP 主路 + tavily 兜底）
- `writing`：论文/报告写作（writing_assistant）
- `image-generation`：图片生成（即梦 MCP）
- `deep-thinking`：独立深度思考
- `ppt-generation`：PPT 生成（Phase 3）

## 记忆使用指导

- 对话中的用户偏好/事实由 `chat_memory_entries` 承载，新会话首轮自动注入
- 本文件只维护系统级内容，修改需谨慎
