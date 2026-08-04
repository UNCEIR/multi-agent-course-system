"""
v2 主 Agent 统一会话（Chat）预留包 — Phase 3 实现

当前状态：空包（骨架预留）。

Phase 3 目标：
  实现主 deep agent 统一会话入口，对应 /chat 端点。核心功能：

  1. 路由：根据用户意图选择 tool/subagent
     - 推荐课程 → recommend_courses tool
     - 成绩单报告 → 委派 report subagent
     - 评价寄语 → 委派 evaluation subagent
     - 学校制度/科研/活动等通用知识 → query_knowledge tool
     - 闲聊 → 直接回答

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
  - 通用知识 Q&A 走 query_knowledge tool（FastGPT KB 经 MCP 调用）
  - 网页搜索走 web_search tool（tavily）

参考文档：
  - docs/v2.0.0/notes/2026-07-27-设计决策问答记录.md 决策 10
  - docs/v2.0.0/notes/2026-07-28-设计决策补充说明.md 决策 10 补充
"""