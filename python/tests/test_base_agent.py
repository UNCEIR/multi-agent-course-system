"""Unit tests for BaseAgent — retry, timeout, fallback, metrics."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.recommend.agents.base_agent import BaseAgent
from models.schemas import AgentResult


class _TestAgent(BaseAgent):
    def __init__(self, execute_fn=None, **kwargs):
        super().__init__(name="test_agent", **kwargs)
        self._execute_fn = execute_fn or (lambda **kw: AgentResult(agent_name="test_agent", success=True))

    async def _execute(self, **kwargs):
        result = self._execute_fn(**kwargs)
        if asyncio.iscoroutine(result) or hasattr(result, "__await__"):
            result = await result
        return result


class TestBaseAgent:
    @pytest.mark.unit
    async def test_successful_execution(self):
        """Agent returns successful result with latency recorded."""
        agent = _TestAgent()
        result = await agent.run()

        assert result.success is True
        assert result.agent_name == "test_agent"
        assert result.latency_ms > 0

    @pytest.mark.unit
    async def test_latency_ms_recorded(self):
        """Latency is measured and attached to result."""
        agent = _TestAgent()
        result = await agent.run()
        assert result.latency_ms is not None
        assert result.latency_ms >= 0

    @pytest.mark.unit
    async def test_call_count_incremented(self):
        """call_count increments on every run."""
        agent = _TestAgent()
        assert agent._call_count == 0
        await agent.run()
        assert agent._call_count == 1
        await agent.run()
        assert agent._call_count == 2

    @pytest.mark.unit
    async def test_retry_on_failure_then_succeed(self):
        """Retries on first failure, succeeds on second attempt."""
        call_count = 0

        async def flaky_execute(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("temporary failure")
            return AgentResult(agent_name="test_agent", success=True)

        agent = _TestAgent(execute_fn=flaky_execute, max_retries=2)
        result = await agent.run()

        assert result.success is True
        assert call_count == 2

    @pytest.mark.unit
    async def test_fallback_after_all_retries(self):
        """After all retries exhausted, fallback result is returned."""
        async def always_fail(**kwargs):
            raise RuntimeError("persistent failure")

        agent = _TestAgent(execute_fn=always_fail, max_retries=2)
        result = await agent.run()

        assert result.success is False
        assert result.confidence == 0.0
        assert "persistent failure" in result.error
        assert agent._error_count == 1

    @pytest.mark.unit
    async def test_error_rate_calculation(self):
        """Error rate is correctly computed."""
        async def always_fail(**kwargs):
            raise RuntimeError("fail")

        agent = _TestAgent(execute_fn=always_fail, max_retries=1)

        assert agent.error_rate == 0.0

        await agent.run()
        assert agent.error_rate == 1.0

        # Second failure keeps rate at 1.0
        await agent.run()
        assert agent.error_rate == 1.0

    @pytest.mark.unit
    async def test_custom_timeout_and_retries(self):
        """Custom timeout and max_retries are stored on the agent."""
        agent = _TestAgent(timeout=3.0, max_retries=5)
        assert agent.timeout == 3.0
        assert agent.max_retries == 5

    @pytest.mark.unit
    async def test_no_fallback_on_retry_success(self):
        """If retry succeeds, fallback is never called."""
        agent = _TestAgent(max_retries=3)
        fallback_spy = MagicMock(wraps=agent._fallback)
        agent._fallback = fallback_spy

        await agent.run()
        fallback_spy.assert_not_called()

    @pytest.mark.unit
    async def test_timeout_returns_fallback(self):
        """单次 LLM 调用超时走 fallback（success=False）。"""
        async def slow_execute(**kwargs):
            await asyncio.sleep(0.2)
            return AgentResult(agent_name="test_agent", success=True)

        agent = _TestAgent(execute_fn=slow_execute, timeout=0.05, max_retries=1)
        result = await agent.run()

        assert result.success is False
        assert result.confidence == 0.0

    @pytest.mark.unit
    async def test_execute_faster_than_timeout(self):
        """执行快于 timeout 时正常返回成功结果。"""
        async def fast_execute(**kwargs):
            await asyncio.sleep(0.01)
            return AgentResult(agent_name="test_agent", success=True)

        agent = _TestAgent(execute_fn=fast_execute, timeout=0.5, max_retries=1)
        result = await agent.run()

        assert result.success is True
