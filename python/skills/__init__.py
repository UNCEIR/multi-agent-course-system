"""
v2 Skills 注册层预留包 — Phase 1 实现

当前状态：空包（骨架预留）。

Phase 1 目标：
  在此目录下实现 ToolRegistry，统一管理所有工具的生命周期：

  class ToolRegistry:
      def register(self, tool: BaseTool) -> None:          # 注册内置工具
      def register_mcp(self, server_url: str) -> None:      # 注册 MCP-backed 工具
      def get_all(self, allowed: list[str] | None = None) -> list[BaseTool]:  # 按 allowlist 过滤
      def get_tool(self, name: str) -> BaseTool | None:     # 按名称查找

  Skills 清单（v2.0.0）：
  - recommend_courses：v1 推荐链路的 tool 包装（LangGraph subgraph）
  - query_knowledge：FastGPT KB Q&A 检索
  - compute_weighted_grade：加权复合统计
  - transcript_parser：Excel 成绩单解析
  - report_renderer：Jinja2 + WeasyPrint PDF 渲染
  - evaluation_generator：评语生成
  - web_search：网页搜索（tavily）
  - mcp_client：FastGPT MCP 客户端

架构决策：
  - 原生工具（@tool）和 MCP 工具（langchain-mcp-adapters）统一注册
  - 权限门控通过 allowlist 参数实现（参考 OpenMAIC）
  - 工具注册在 app/runtime.init() 中完成，随应用启动注册
"""