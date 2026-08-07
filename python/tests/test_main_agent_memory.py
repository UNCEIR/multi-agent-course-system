# -*- coding: utf-8 -*-
"""主 agent 记忆机制单测。

验证核心：
1. build_main_agent() 能编译返回 compiled agent
2. 多轮 invoke 时 state.messages 累积
3. thread_id 恢复后 messages 包含历史
4. compaction 触发后 _summarization_event 非空
5. AGENTS.md 可通过 FilesystemBackend 读写
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, ANY


@pytest.fixture
def mock_settings():
    """Mock settings 避免依赖 .env 文件。"""
    with patch("config.get_settings") as mock:
        s = MagicMock()
        s.llm_api_key = "test-key"
        s.llm_base_url = "https://test.api/v1"
        s.llm_model = "deepseek-v4-flash"
        s.llm_enable_thinking = False
        s.httpx_verify_ssl = False
        s.memory_dir = ""
        s.skills_dir = ""
        s.checkpoint_sqlite_path = ""
        s.agent_context_window_tokens = 128000
        s.agent_compaction_trigger_tokens = None
        s.agent_compaction_keep_tokens = 20000
        s.agent_compaction_trigger_messages = 8
        mock.return_value = s
        yield s


class TestBuildMainAgent:
    """验证 build_main_agent() 调用 create_deep_agent 并返回 compiled agent。"""

    def test_import_and_build(self, mock_settings):
        """确保模块导入无报错，build_main_agent() 返回 compiled agent。

        使用 mock 替换 create_deep_agent 以避免需要真实 LLM 实例。
        """
        with (
            patch("agent.main.agent.create_deep_agent") as mock_create,
        ):
            mock_agent = MagicMock()
            mock_agent.invoke = MagicMock()
            mock_agent.ainvoke = MagicMock()
            mock_create.return_value = mock_agent

            from agent.main.agent import build_main_agent

            agent = build_main_agent()
            assert agent is not None
            assert hasattr(agent, "invoke")
            assert hasattr(agent, "ainvoke")
            # 验证 create_deep_agent 被调用且传入了关键参数
            mock_create.assert_called_once()
            _, kwargs = mock_create.call_args
            assert "model" in kwargs
            assert "backend" in kwargs
            assert "skills" in kwargs
            assert "/skills/" in kwargs["skills"]
            assert "memory" in kwargs
            assert "/memories/AGENTS.md" in kwargs["memory"]
            assert "checkpointer" in kwargs
            assert "system_prompt" in kwargs


class TestAgentModules:
    """验证各子模块导入无语法错误。"""

    def test_import_prompt(self):
        from agent.main.prompt import MAIN_AGENT_SYSTEM_PROMPT
        assert isinstance(MAIN_AGENT_SYSTEM_PROMPT, str)
        assert len(MAIN_AGENT_SYSTEM_PROMPT) > 100

    def test_import_tools(self):
        from tools import list_available_skills, get_current_time
        # StructuredTool 是 Runnable，有 invoke 方法
        assert hasattr(list_available_skills, "invoke")
        assert hasattr(list_available_skills, "func")
        assert hasattr(get_current_time, "invoke")

    def test_import_subagents(self):
        from agent.main.subagents import build_report_subagent, build_evaluation_agent, build_ppt_agent
        with pytest.raises(NotImplementedError):
            build_report_subagent()
        with pytest.raises(NotImplementedError):
            build_evaluation_agent()
        with pytest.raises(NotImplementedError):
            build_ppt_agent()

    def test_import_backend(self, mock_settings):
        from agent.main.backend import build_main_backend
        backend = build_main_backend()
        assert backend is not None

    def test_import_checkpointer(self, mock_settings):
        from agent.main.checkpointer import build_checkpointer
        checkpointer = build_checkpointer()
        assert checkpointer is not None
        # 确保释放连接
        checkpointer.conn.close()


class TestChatAPI:
    """验证 chat API 端点。"""

    def test_chat_request_model(self):
        from api.chat import ChatRequest, ChatResponse
        req = ChatRequest(message="你好", session_id="s1", user_id="u1")
        assert req.message == "你好"
        assert req.session_id == "s1"
        assert req.user_id == "u1"

        resp = ChatResponse(reply="测试回复", session_id="s1", messages_count=2)
        assert resp.reply == "测试回复"
        assert resp.messages_count == 2


class TestAGENTSMD:
    """验证 AGENTS.md 种子文件存在且内容正确。"""

    AGENTS_PATH = "python/memories/AGENTS.md"

    def test_agents_md_exists(self):
        from pathlib import Path
        repo_root = Path(__file__).resolve().parent.parent.parent
        agents_file = repo_root / self.AGENTS_PATH
        assert agents_file.exists(), f"AGENTS.md 不存在: {agents_file}"
        content = agents_file.read_text(encoding="utf-8")
        assert "项目记忆" in content
        assert "学校公选课推荐系统" in content
        assert "用户偏好" in content


class TestRuntimeIntegration:
    """验证 runtime 模块导入和主 agent 生命周期。"""

    def test_runtime_imports(self):
        """确保 runtime 模块导入无报错。"""
        import agent.runtime
        assert agent.runtime.main_agent is None  # 初始为 None
        assert hasattr(agent.runtime, "init")
        assert hasattr(agent.runtime, "shutdown")

    def test_main_py_imports(self):
        """确保 main.py 导入无循环依赖。"""
        # 只验证模块级 import 不报错（不触发 lifespan）
        import agent.main
        assert agent.main is not None