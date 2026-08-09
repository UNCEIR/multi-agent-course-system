# 统一 Deepagent 工厂与当前阶段边界

## 背景与问题

- 当前工作区原有改动把异步 checkpointer、chat 端点和测试迁移混在一起，旧测试仍断言同步工厂和占位 subagent 行为。
- 需求目标是所有业务 Agent 都通过统一 deepagent 工厂创建，并按场景加载对应信息；当前阶段明确不接 FastGPT。

## 总体架构方案

- `python/agent/main/factory.py` 统一组装模型、backend、skills、memory、compaction、checkpointer 和工具列表。
- `python/agent/main/specs.py` 用 `AgentSpec` 声明 main、recommendation、report、evaluation、PPT 五类场景的 prompt、技能、记忆和工具 allowlist。
- `agent.py` 与 `subagents.py` 仅保留场景入口，避免每个 Agent 重复创建 deepagents middleware。

## 细节实现

- `build_main_agent()`、`build_recommendation_agent()`、`build_report_agent()`、`build_evaluation_agent()`、`build_ppt_agent()` 均委托 `build_deep_agent()`。
- 场景工具从 `runtime.tool_registry` 按 allowlist 获取；main Agent 保持全量注册工具，报告 Agent 只声明成绩统计工具。
- FastGPT/MCP 没有接入 runtime 或当前工厂装配链路；旧文档中的 FastGPT 计划被当前执行边界覆盖。

## 测试与验证

- `python -m compileall -q agent/main agent/app.py ai/llm_task_name.py tests/test_agent_factory.py`：通过。
- `python -m pytest tests/test_agent_factory.py tests/test_tool_registry.py -q`：16 passed。
- 旧 `test_main_agent_memory.py` 未按旧断言修复；它仍 patch 已迁移的内部符号、同步调用异步工厂，并要求占位 Agent 抛 `NotImplementedError`，这些失败记录为旧测试与新架构不一致，而不是回退生产代码的理由。
