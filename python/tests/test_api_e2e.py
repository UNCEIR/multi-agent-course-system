# -*- coding: utf-8 -*-
"""API 端到端测试 — 验证 /api/v1/chat 接口。

使用 FastAPI TestClient 对端点做端到端验证。
注意：需要 mock 底层 LLM 和 deepagents 避免真实调用。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_full_settings(tmp_path):
    """完整的 mock settings，兼容所有模块。"""
    with patch("config.get_settings") as mock:
        s = MagicMock()
        # LLM
        s.llm_api_key = "test-key"
        s.llm_base_url = "https://test.api/v1"
        s.llm_model = "deepseek-v4-flash"
        s.llm_enable_thinking = False
        s.httpx_verify_ssl = False
        # Memory / skill / checkpoint
        s.memory_dir = ""
        s.skills_dir = ""
        s.checkpoint_sqlite_path = str(tmp_path / "checkpoint.db")
        # Agent compaction
        s.agent_context_window_tokens = 128000
        s.agent_compaction_trigger_tokens = None
        s.agent_compaction_keep_tokens = 20000
        s.agent_compaction_trigger_messages = 8
        # LangSmith
        s.langchain_api_key = "test-ls-key"
        s.langchain_endpoint = "https://api.smith.langchain.com"
        s.langchain_tracing_v2 = True
        s.langchain_project = "multi-agent-course-system"
        # v1 config
        s.llm_temperature = 0.7
        s.llm_max_tokens = 4096
        s.redis_url = "redis://localhost:6379/0"
        s.feature_ttl_seconds = 86400
        s.course_recall_cache_enabled = True
        s.course_recall_cache_ttl_seconds = 900
        s.course_recall_cache_lock_ttl_seconds = 5
        s.course_recall_cache_wait_retries = 3
        s.course_recall_cache_wait_seconds = 0.1
        s.course_recall_cache_semantic_enabled = True
        s.course_recall_cache_semantic_threshold = 0.95
        s.course_recall_cache_semantic_max_candidates = 12
        s.course_recall_cache_semantic_min_prompt_chars = 8
        s.mysql_host = "localhost"
        s.mysql_port = 3306
        s.mysql_user = "root"
        s.mysql_password = "password"
        s.mysql_database = "test_db"
        s.mysql_pool_size = 10
        s.mysql_max_overflow = 20
        s.milvus_host = "localhost"
        s.milvus_port = 19530
        s.milvus_user = ""
        s.milvus_password = ""
        s.milvus_uri = ""
        s.milvus_collection = "product_embeddings"
        s.course_milvus_collection = "course_chunks_real"
        s.milvus_dimension = 1024
        s.milvus_metric_type = "COSINE"
        s.milvus_index_type = "AUTOINDEX"
        s.embedding_provider = "openai"
        s.embedding_dimension = 1024
        s.embedding_base_url = ""
        s.embedding_api_key = ""
        s.embedding_model = "text-embedding-v4"
        s.embedding_batch_size = 8
        s.embedding_timeout_seconds = 30.0
        s.ab_test_enabled = True
        s.ab_test_default_bucket_count = 100
        s.agent_timeout_user_profile = 5.0
        s.agent_timeout_product_recall = 6.0
        s.agent_timeout_product_rerank = 8.0
        s.agent_timeout_marketing_copy = 10.0
        s.agent_timeout_inventory = 5.0
        s.supervisor_max_retries = 2
        s.supervisor_global_timeout = 30.0
        s.stream_timeout_seconds = 60.0
        s.app_name = "multi-agent-course-system"
        s.debug = False
        mock.return_value = s
        yield s


@pytest.fixture
def mock_runtime_and_app(mock_full_settings):
    """Mock 整个 agent.runtime 模块 + api.chat.runtime，构建 TestClient。

    agent.runtime 在 agent/app.py 模块级导入（from agent import runtime），
    api.chat 也做同样导入。patch("agent.runtime", create=True) 确保 mock
    在 runtime 模块尚未导入时也能生效。
    """
    # 创建 mock runtime
    mock_runtime = MagicMock()
    mock_agent = MagicMock()
    mock_agent.ainvoke = MagicMock()

    async def fake_ainvoke(*args, **kwargs):
        return {
            "messages": [
                MagicMock(content="你好！我是学校公选课系统的智能助手，有什么可以帮你的吗？"),
            ]
        }

    mock_agent.ainvoke.side_effect = fake_ainvoke
    mock_runtime.main_agent = mock_agent
    # v1 单例也需要 mock 避免 runtime.init() 出错
    mock_runtime.supervisor = MagicMock()
    mock_runtime.rec_graph = MagicMock()
    mock_runtime.mysql_repo = MagicMock()
    # redis_repo.ping() 是 async 方法，需要 AsyncMock 或 async 函数
    mock_redis = MagicMock()
    async def fake_ping():
        return True
    mock_redis.ping = fake_ping
    mock_runtime.redis_repo = mock_redis
    mock_runtime.course_vector_repo = MagicMock()
    mock_runtime.metrics_collector = MagicMock()
    mock_runtime.ab_engine = MagicMock()
    mock_runtime.tool_registry = MagicMock()

    # 确保 LangSmith 环境变量在 app 导入前就位
    import os
    os.environ.setdefault("LANGSMITH_TRACING_V2", "false")
    os.environ.setdefault("LANGSMITH_API_KEY", "test-key")

    with (
        patch("agent.runtime", mock_runtime, create=True),
        patch("api.chat.runtime", mock_runtime),
    ):
        # 现在导入 agent.app，它内部会 from agent import runtime
        from agent.app import app
        client = TestClient(app)
        yield client


class TestChatEndpoint:
    """POST /api/v1/chat 端到端测试。"""

    def test_chat_basic_request(self, mock_runtime_and_app):
        """基本对话请求，验证返回结构。"""
        client = mock_runtime_and_app
        response = client.post(
            "/api/v1/chat",
            json={"message": "你好", "session_id": "test-session", "user_id": "test-user"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "reply" in data
        assert "session_id" in data
        assert "messages_count" in data
        assert data["session_id"] == "test-session"
        assert len(data["reply"]) > 0

    def test_chat_default_session_id(self, mock_runtime_and_app):
        """未传 session_id 时使用默认值 'default'。"""
        client = mock_runtime_and_app
        response = client.post(
            "/api/v1/chat",
            json={"message": "推荐课程"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "default"

    def test_chat_without_user_id(self, mock_runtime_and_app):
        """未传 user_id 时使用空字符串。"""
        client = mock_runtime_and_app
        response = client.post(
            "/api/v1/chat",
            json={"message": "你好", "session_id": "s1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "s1"
        assert "reply" in data

    def test_chat_empty_message_returns_422(self, mock_runtime_and_app):
        """空消息返回 422 验证错误。"""
        client = mock_runtime_and_app
        response = client.post(
            "/api/v1/chat",
            json={"message": "", "session_id": "s1"},
        )
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_chat_long_message_returns_422(self, mock_runtime_and_app):
        """超过 max_length 的消息返回 422。"""
        client = mock_runtime_and_app
        response = client.post(
            "/api/v1/chat",
            json={"message": "a" * 8193, "session_id": "s1"},
        )
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_chat_injects_user_id_into_config(self, mock_runtime_and_app):
        """同步 chat 端点把 user_id 注入 agent config。"""
        from unittest.mock import patch

        client = mock_runtime_and_app
        captured = {}

        async def fake_ainvoke_with_config(_input, config=None):
            captured["user_id"] = (config or {}).get("configurable", {}).get("user_id", "")
            return {"messages": [MagicMock(content="ok")]}

        mock_agent = MagicMock()
        mock_agent.ainvoke = fake_ainvoke_with_config
        with patch("api.chat.runtime.main_agent", mock_agent):
            response = client.post(
                "/api/v1/chat",
                json={"message": "你好", "session_id": "s1", "user_id": "u77"},
            )
        assert response.status_code == 200
        assert captured["user_id"] == "u77"

    def test_chat_response_model_matches(self, mock_runtime_and_app):
        """验证响应结构符合 ChatResponse 模型。"""
        client = mock_runtime_and_app
        response = client.post(
            "/api/v1/chat",
            json={"message": "测试", "session_id": "s1"},
        )
        assert response.status_code == 200
        data = response.json()
        # 验证字段类型
        assert isinstance(data["reply"], str)
        assert isinstance(data["session_id"], str)
        assert isinstance(data["messages_count"], int)
        # 验证 messages_count 非负
        assert data["messages_count"] >= 0

    def test_chat_invalid_method(self, mock_runtime_and_app):
        """GET 请求返回 405 Method Not Allowed。"""
        client = mock_runtime_and_app
        response = client.get("/api/v1/chat")
        assert response.status_code == 405

    def test_chat_wrong_content_type(self, mock_runtime_and_app):
        """非 JSON content-type 返回 422。"""
        client = mock_runtime_and_app
        response = client.post(
            "/api/v1/chat",
            data="not json",
            headers={"Content-Type": "text/plain"},
        )
        assert response.status_code == 422


class TestHealthEndpoint:
    """健康检查端点测试。"""

    def test_health_endpoint(self, mock_runtime_and_app):
        """GET /health 返回 200。"""
        client = mock_runtime_and_app
        response = client.get("/health")
        assert response.status_code == 200

    def test_api_health_endpoint(self, mock_runtime_and_app):
        """GET /api/v1/health 返回 200。"""
        client = mock_runtime_and_app
        response = client.get("/api/v1/health")
        assert response.status_code == 200


class TestJsonSerialization:
    """验证请求/响应的 JSON 序列化。"""

    def test_chat_request_json_schema(self):
        """验证 ChatRequest JSON Schema 包含必要字段。"""
        from api.chat import ChatRequest
        schema = ChatRequest.model_json_schema()
        props = schema.get("properties", {})
        assert "message" in props
        assert "session_id" in props
        assert "user_id" in props
        # message 字段有 minLength 约束
        assert props["message"].get("minLength") == 1

    def test_chat_response_json_schema(self):
        """验证 ChatResponse JSON Schema。"""
        from api.chat import ChatResponse
        schema = ChatResponse.model_json_schema()
        props = schema.get("properties", {})
        assert "reply" in props
        assert "session_id" in props
        assert "messages_count" in props

    def test_chat_request_serialization_roundtrip(self):
        """验证 ChatRequest 序列化/反序列化。"""
        from api.chat import ChatRequest
        original = ChatRequest(message="你好", session_id="s1", user_id="u1")
        json_str = original.model_dump_json()
        restored = ChatRequest.model_validate_json(json_str)
        assert restored.message == "你好"
        assert restored.session_id == "s1"
        assert restored.user_id == "u1"

    def test_chat_response_serialization_roundtrip(self):
        """验证 ChatResponse 序列化/反序列化。"""
        from api.chat import ChatResponse
        original = ChatResponse(reply="回复内容", session_id="s1", messages_count=5)
        json_str = original.model_dump_json()
        restored = ChatResponse.model_validate_json(json_str)
        assert restored.reply == "回复内容"
        assert restored.session_id == "s1"
        assert restored.messages_count == 5

    def test_json_file_fixture_valid(self):
        """验证 JSON 测试夹具文件格式正确。"""
        fixture_path = Path(__file__).resolve().parent / "endtoend" / "chat_test_cases.json"
        assert fixture_path.exists(), f"Fixture file not found: {fixture_path}"
        loaded = json.loads(fixture_path.read_text(encoding="utf-8"))
        assert isinstance(loaded, list)
        assert len(loaded) > 0
        for case in loaded:
            assert "name" in case
            assert "request" in case
            assert "expected" in case
            assert case["request"]["method"] in ("POST", "GET", "PUT", "DELETE")
            assert "path" in case["request"]

    def test_json_fixture_covers_basic_chat(self):
        """JSON fixture 包含基本对话测试用例。"""
        fixture_path = Path(__file__).resolve().parent / "endtoend" / "chat_test_cases.json"
        loaded = json.loads(fixture_path.read_text(encoding="utf-8"))
        names = [case["name"] for case in loaded]
        assert "chat_basic" in names
        assert "chat_empty_message" in names
        assert "chat_long_message" in names


class TestRecommendStreamEndpoint:
    """POST /api/v1/recommend/stream 统一流式入口测试。"""

    def test_recommend_stream_returns_done_event(self, mock_runtime_and_app):
        """消费流并断言事件序列与终 done（AGENTS.md 流式契约）。"""
        from unittest.mock import patch

        client = mock_runtime_and_app

        async def fake_unified(_request):
            yield {"event": "phase", "data": {"phase": "start"}}
            yield {
                "event": "done",
                "data": {
                    "courses": [],
                    "recommendation_reasons": [],
                    "selection_warnings": [],
                    "experiment_group": "pipeline",
                },
            }

        supervisor = MagicMock()
        supervisor.stream_recommend_unified = fake_unified
        metrics = MagicMock()

        with (
            patch("api.recommend.runtime.supervisor", supervisor),
            patch("api.recommend.runtime.metrics_collector", metrics),
        ):
            with client.stream(
                "POST",
                "/api/v1/recommend/stream",
                json={"user_id": "u1", "query": "不考试的课", "num_items": 2},
            ) as response:
                assert response.status_code == 200
                lines = [line for line in response.iter_lines() if line]
                events = [
                    line[len("event: "):]
                    for line in lines
                    if line.startswith("event: ")
                ]
        assert "done" in events
        assert events[0] == "phase"
        assert events[-1] == "done"

    def test_recommend_stream_error_event(self, mock_runtime_and_app):
        """统一流式出错走结构化 error 事件。"""
        from unittest.mock import patch

        client = mock_runtime_and_app

        async def fake_unified_error(_request):
            yield {
                "event": "error",
                "data": {"code": "BOOM", "message": "failed", "phase": "react"},
            }

        supervisor = MagicMock()
        supervisor.stream_recommend_unified = fake_unified_error
        metrics = MagicMock()

        with (
            patch("api.recommend.runtime.supervisor", supervisor),
            patch("api.recommend.runtime.metrics_collector", metrics),
        ):
            with client.stream(
                "POST",
                "/api/v1/recommend/stream",
                json={"user_id": "u1", "query": "测试", "num_items": 1},
            ) as response:
                assert response.status_code == 200
                lines = [line for line in response.iter_lines() if line]
                events = [
                    line[len("event: "):]
                    for line in lines
                    if line.startswith("event: ")
                ]
        assert events == ["error"]


class TestChatStreamEndpoint:
    """POST /api/v1/chat/stream SSE 端点测试。"""

    def test_chat_stream_emits_text_tool_done(self, mock_runtime_and_app):
        """消费流并断言 text/tool/done 事件与终 done。"""
        from unittest.mock import patch

        client = mock_runtime_and_app
        captured_config = {}

        async def fake_astream_events(_input, config=None, version=None):
            captured_config["user_id"] = (config or {}).get("configurable", {}).get("user_id", "")
            yield {
                "event": "on_tool_start",
                "name": "query_knowledge",
            }
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": MagicMock(content="你好")},
            }
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": MagicMock(content="，有什么可以帮你？")},
            }
            yield {"event": "on_tool_end", "name": "query_knowledge"}

        mock_agent = MagicMock()
        mock_agent.astream_events = fake_astream_events
        with patch("api.chat.runtime.main_agent", mock_agent):
            with client.stream(
                "POST",
                "/api/v1/chat/stream",
                json={"message": "你好", "session_id": "s1", "user_id": "u1"},
            ) as response:
                assert response.status_code == 200
                lines = [line for line in response.iter_lines() if line]
                events = [
                    line[len("event: "):]
                    for line in lines
                    if line.startswith("event: ")
                ]
                assert events[0] == "tool"
                assert "text" in events
                assert events[-1] == "done"
                data = lines[-1][len("data: "):]
                import json as _json
                payload = _json.loads(data)
                assert "你好" in payload["reply"]
                assert payload["session_id"] == "s1"
        # user_id 已注入到 agent config
        assert captured_config["user_id"] == "u1"

    def test_chat_stream_error_event(self, mock_runtime_and_app):
        """主 agent 流式异常走结构化 error 事件。"""
        from unittest.mock import patch

        client = mock_runtime_and_app

        async def fake_astream_events_error(_input, config=None, version=None):
            yield {"event": "on_custom", "name": "x"}
            raise RuntimeError("boom")

        mock_agent = MagicMock()
        mock_agent.astream_events = fake_astream_events_error
        with patch("api.chat.runtime.main_agent", mock_agent):
            with client.stream(
                "POST",
                "/api/v1/chat/stream",
                json={"message": "你好", "session_id": "s1"},
            ) as response:
                assert response.status_code == 200
                lines = [line for line in response.iter_lines() if line]
                events = [
                    line[len("event: "):]
                    for line in lines
                    if line.startswith("event: ")
                ]
        assert events == ["error"]

