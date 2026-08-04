"""
v2 deepagents Harness 预留包 — Phase 1 实现

当前状态：空包（骨架预留）。

Phase 1 目标：
  在此目录下实现 deepagents 的 Python 包装层，包括：
  - compaction：上下文压缩（阈值 contextWindow-13000，keepRecentTokens=20000）
  - session：会话管理与 checkpointing（Redis 后端，thread_id 恢复）
  - circuit_breaker：工具调用熔断（连续 3 次失败熔断）
  - 文件系统：deepagents 内置虚拟文件系统（中间产物落盘，防幻觉）

参考源码：
  - E:\\Agent\\pi\\packages\\agent\\src\\harness\\compaction\\
  - E:\\Agent\\pi\\packages\\coding-agent\\src\\core\\compaction\\
  - claude-code autoCompact / circuit breaker / AgentTool

架构决策：
  - 此包是 v2 的 agent 运行时层，与 v1 的 app/recommend/agents/base_agent.py 无关
  - v1 的 base_agent 保留在 app/recommend/agents/，v2 用 deepagents 内置机制
  - 两套机制并存，不共享基类
"""