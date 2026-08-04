import os
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from services.tracing import configure_langsmith_tracing, get_tracing_status


@dataclass
class _FakeSettings:
    langchain_api_key: str = ""
    langchain_endpoint: str = ""
    langchain_tracing_v2: bool = True
    langchain_project: str = ""


_ALL_NAMESPACES = ("LANGCHAIN", "LANGSMITH")
_ALL_BASE_NAMES = ("API_KEY", "ENDPOINT", "PROJECT", "TRACING_V2")


@pytest.fixture(autouse=True)
def _clean_langsmith_env():
    """每个测试前清理所有 LANGCHAIN_* / LANGSMITH_* 环境变量，避免相互影响。"""
    keys = []
    for ns in _ALL_NAMESPACES:
        for name in _ALL_BASE_NAMES:
            keys.append(f"{ns}_{name}")
    original = {k: os.environ.get(k) for k in keys}
    for k in keys:
        os.environ.pop(k, None)
    yield
    for k in keys:
        os.environ.pop(k, None)
        if original.get(k) is not None:
            os.environ[k] = original[k]


def test_configure_langsmith_tracing_maps_settings_to_both_namespaces():
    """验证 settings 中的 langchain_* 字段会被映射为 LANGCHAIN_* 和 LANGSMITH_* 双命名空间。"""
    fake_settings = _FakeSettings(
        langchain_api_key="sk-test-key",
        langchain_endpoint="https://test.langsmith.com",
        langchain_project="test-project",
        langchain_tracing_v2=True,
    )

    with patch("services.tracing.get_settings", return_value=fake_settings):
        configured = configure_langsmith_tracing()

    # 双命名空间都写入
    assert configured["LANGCHAIN_API_KEY"] == "sk-test-key"
    assert configured["LANGSMITH_API_KEY"] == "sk-test-key"
    assert configured["LANGCHAIN_TRACING_V2"] == "true"
    assert configured["LANGSMITH_TRACING_V2"] == "true"
    # os.environ 也被写入
    assert os.environ["LANGCHAIN_API_KEY"] == "sk-test-key"
    assert os.environ["LANGSMITH_API_KEY"] == "sk-test-key"


def test_configure_langsmith_tracing_respects_existing_env():
    """验证外部已设置的环境变量不会被覆盖（setdefault 语义）。"""
    fake_settings = _FakeSettings(
        langchain_api_key="sk-from-env-file",
        langchain_endpoint="https://test.langsmith.com",
        langchain_project="test-project",
        langchain_tracing_v2=True,
    )
    os.environ["LANGCHAIN_API_KEY"] = "sk-from-host"

    with patch("services.tracing.get_settings", return_value=fake_settings):
        configured = configure_langsmith_tracing()

    assert configured["LANGCHAIN_API_KEY"] == "sk-from-env-file"
    assert os.environ["LANGCHAIN_API_KEY"] == "sk-from-host"


def test_configure_langsmith_tracing_disabled_without_api_key():
    """验证没有 api_key 时不会写入 API_KEY env，但 tracing 开关仍会写入。"""
    fake_settings = _FakeSettings(
        langchain_api_key="",
        langchain_endpoint="https://test.langsmith.com",
        langchain_project="test-project",
        langchain_tracing_v2=True,
    )

    with patch("services.tracing.get_settings", return_value=fake_settings):
        configured = configure_langsmith_tracing()

    assert "LANGCHAIN_API_KEY" not in configured
    assert "LANGSMITH_API_KEY" not in configured
    assert configured["LANGCHAIN_TRACING_V2"] == "true"
    assert os.environ.get("LANGCHAIN_TRACING_V2") == "true"


def test_get_tracing_status_enabled():
    """验证 tracing 激活后 get_tracing_status 返回 enabled=True。"""
    os.environ["LANGSMITH_TRACING_V2"] = "true"
    os.environ["LANGSMITH_API_KEY"] = "sk-test"
    os.environ["LANGSMITH_PROJECT"] = "my-project"

    status = get_tracing_status()

    assert status["enabled"] is True
    assert status["tracing_v2"] == "true"
    assert status["project"] == "my-project"
    assert status["api_key_configured"] is True


def test_get_tracing_status_disabled_without_api_key():
    """验证 tracing_v2=true 但无 api_key 时 enabled=False。"""
    os.environ["LANGSMITH_TRACING_V2"] = "true"
    # 不设置 API_KEY

    status = get_tracing_status()

    assert status["enabled"] is False
    assert status["tracing_v2"] == "true"
    assert status["api_key_configured"] is False


def test_get_tracing_status_falls_back_to_langchain_namespace():
    """验证 LANGSMITH_* 未设置时 fallback 到 LANGCHAIN_*。"""
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = "sk-fallback"
    os.environ["LANGCHAIN_PROJECT"] = "lc-project"

    status = get_tracing_status()

    assert status["enabled"] is True
    assert status["project"] == "lc-project"
    assert status["api_key_configured"] is True
