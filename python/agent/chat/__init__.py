"""
v2 主 Agent 统一会话（Chat）预留包 — Phase 3 实现

当前状态：空包（骨架预留）。

Phase 3 目标：
  实现主 deep agent 统一会话入口，对应 /chat 端点。核心功能：

  1. 路由：根据用户意图选择 tool/subagent
     - 推荐课程 → recommend_courses tool
     - 成绩单报告 → 委派 report subagent
     - 评价寄语 → 委派 evaluation subagent
     - 学校制度/规章/流程 → query_handbook tool（公开手册分区）
     - 本人成绩单/某科成绩 → query_transcript tool（个人分区，强权限隔离）
     - 闲聊 → 直接回答
     - **2026-08-25 重构**：query_knowledge 拆成 query_handbook / query_transcript 两个独立工具，
       按问题域分发，避免 top_k 候选集污染 + 权限边界模糊（详见 docs/.../2026-08-25-knowledge-tools-split.md）

  2. 路由机制：主 agent LLM 推理意图 → deepagents 原生 task/tool 调用委派
     - 用 TodoWrite 规划多步（参考 claude-code assembleToolPool）
     - 不确定时澄清

  3. 流式输出：SSE 事件类型（token / tool_call / tool_result / final）
     - 复用 v1 stream_token_markup_parser 的标记解析模式

  4. 会话管理：
     - compaction（阈值 contextWindow-13000，keepRecentTokens=20000）
     - 结构化摘要（Goal/Progress/Key Decisions/Next Steps/Critical Context）
     - checkpointing（Redis 后端，thread_id 恢复）

架构决策：
  - 混合入口：/chat 走主 agent 路由，/recommend /report /evaluation 直达专用端点
  - 各端点独立 session，不共享对话
  - 通用知识 Q&A 走 query_handbook（公开）+ query_transcript（个人）两个独立工具
  - 网页搜索走 web_search tool（tavily）

参考文档：
  - docs/v2.0.0/notes/2026-07-27-设计决策问答记录.md 决策 10
  - docs/v2.0.0/notes/2026-07-28-设计决策补充说明.md 决策 10 补充
  - docs/v2.0.0/notes/2026-08-25-knowledge-tools-split.md
"""