# -*- coding: utf-8 -*-
"""集成测试 — 真实调用 build_main_agent() + 真实 LLM，零 mock。

验证 agent 管线（deepagents + middleware + backend + checkpointer + LLM）
能正常串联，不做任何 mock。

标记为 @pytest.mark.slow，默认 pytest -m "not slow" 会跳过。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from config import get_settings


@pytest.mark.slow
@pytest.mark.integration
class TestAgentRealIntegration:
    """使用真实 build_main_agent() + 真实 LLM，端到端验证。"""

    @pytest.fixture(autouse=True)
    def _prepare_env(self, tmp_path):
        """每个测试用例前准备独立的测试目录，并临时覆盖 settings 路径字段。"""
        self.test_root = tmp_path / "agent_test"
        self.memories_dir = self.test_root / "memories"
        self.skills_dir = self.test_root / "skills"
        self.memories_dir.mkdir(parents=True, exist_ok=True)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        agents_md = self.memories_dir / "AGENTS.md"
        if not agents_md.exists():
            agents_md.write_text(
                "# 项目记忆\n\n大学校园多智能体平台\n\n## 用户偏好\n（暂无）\n",
                encoding="utf-8",
            )

        # 保存原始值，测试后恢复
        self._s = get_settings()
        self._orig = {
            "memory_dir": self._s.memory_dir,
            "skills_dir": self._s.skills_dir,
            "checkpoint_sqlite_path": self._s.checkpoint_sqlite_path,
            "agent_compaction_trigger_messages": self._s.agent_compaction_trigger_messages,
        }

        self._s.memory_dir = str(self.memories_dir)
        self._s.skills_dir = str(self.skills_dir)
        self._s.checkpoint_sqlite_path = str(self.test_root / "checkpoint.db")
        # 关闭 compaction，避免测试中触发摘要干扰验证
        self._s.agent_compaction_trigger_messages = None

        yield

        for k, v in self._orig.items():
            setattr(self._s, k, v)

    def _skip_if_no_llm(self):
        if not self._s.llm_api_key or not self._s.llm_base_url:
            pytest.skip("LLM 环境未配置（缺少 llm_api_key 或 llm_base_url）")

    async def test_build_and_invoke(self):
        """真实构建 agent 并调用 ainvoke，验证 LLM 返回非空回复。"""
        self._skip_if_no_llm()

        from agent.main.agent import build_main_agent

        agent = await build_main_agent(tools=[])
        assert agent is not None
        assert hasattr(agent, "ainvoke")

        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "你好，请简单介绍一下你自己"}]},
            config={"configurable": {"thread_id": "test-real-integration"}},
        )
        messages = result.get("messages", [])
        assert len(messages) >= 2, f"预期至少 2 条消息，实际 {len(messages)}"

        self._print_reply("单轮对话", messages[-1])

    async def test_multi_turn_conversation(self):
        """多轮对话验证消息累积和上下文保持。"""
        self._skip_if_no_llm()

        from agent.main.agent import build_main_agent
        agent = await build_main_agent(tools=[])

        # 第一轮：告诉名字
        result1 = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "你好，我的名字叫张三"}]},
            config={"configurable": {"thread_id": "test-multi-turn"}},
        )
        count1 = len(result1.get("messages", []))

        # 第二轮：问名字（同一 thread_id 应记住上下文）
        result2 = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "我刚才说自己叫什么名字？"}]},
            config={"configurable": {"thread_id": "test-multi-turn"}},
        )
        count2 = len(result2.get("messages", []))
        assert count2 > count1, f"第二轮消息数({count2})应大于第一轮({count1})"

        self._print_reply("多轮对话", result2["messages"][-1])

    async def test_agent_with_tools(self):
        """传入真实工具列表时 agent 能正常处理工具调用。"""
        self._skip_if_no_llm()

        from tools.system import get_current_time, list_available_skills
        from agent.main.agent import build_main_agent

        agent = await build_main_agent(tools=[get_current_time, list_available_skills])
        assert agent is not None

        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "现在几点了？请用工具查询"}]},
            config={"configurable": {"thread_id": "test-tools-real"}},
        )
        messages = result.get("messages", [])
        assert len(messages) >= 2

        self._print_reply("工具调用", messages[-1])

    @staticmethod
    def _print_reply(scenario: str, msg):
        if hasattr(msg, "content"):
            content = msg.content or ""
        elif isinstance(msg, dict):
            content = msg.get("content", "")
        else:
            content = str(msg)
        preview = content[:300].replace("\n", " ")
        print(f"\n── [{scenario}] LLM 回复 ──\n{preview}\n───")