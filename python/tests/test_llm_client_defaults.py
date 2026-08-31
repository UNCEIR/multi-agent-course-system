# -*- coding: utf-8 -*-
"""A6 回归：llm_client 覆盖参数扩展后默认行为零变化。

- 不传覆盖参数 → 全部取 settings（既有 15+ 调用点行为不变）
- 传覆盖参数 → model/base_url/api_key/enable_thinking 生效（Phase 2 视觉/填表等复用）
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.language_models import BaseChatModel

from ai.llm_client import build_chat_openai
from ai.llm_task_name import LLMTaskName


@pytest.fixture
def llm_settings():
    settings = MagicMock()
    settings.llm_enable_thinking = False
    settings.httpx_verify_ssl = True
    settings.llm_api_key = "default-key"
    settings.llm_base_url = "https://default.invalid/v1"
    settings.llm_model = "default-model"
    # P0：LLM 请求级超时（缺失时会绕过全部业务层超时，导致 SSE 链路静默挂死）
    settings.llm_timeout_seconds = 20.0
    settings.llm_connect_timeout_seconds = 5.0
    settings.llm_max_retries = 1
    with patch("ai.llm_client.get_settings", return_value=settings):
        yield settings


@pytest.mark.unit
def test_defaults_unchanged(llm_settings):
    """不传覆盖参数 → 与扩展前完全一致（model/base_url/api_key 取 settings）。"""
    llm = build_chat_openai(
        temperature=0.1,
        max_tokens=2048,
        task_name=LLMTaskName.REPORT_HTML_FILL,
    )

    assert isinstance(llm, BaseChatModel)
    assert llm.model_name == "default-model"
    assert llm.openai_api_key.get_secret_value() == "default-key"
    assert llm.openai_api_base == "https://default.invalid/v1"
    assert llm.max_tokens == 2048
    assert llm.temperature == 0.1
    assert llm.get_name() == LLMTaskName.REPORT_HTML_FILL.value


@pytest.mark.unit
def test_overrides_apply(llm_settings):
    """传覆盖参数 → 生效且不影响既有默认调用。"""
    llm = build_chat_openai(
        temperature=0.1,
        max_tokens=4096,
        model="vision-model",
        base_url="https://vision.invalid/v1",
        api_key="vision-key",
    )

    assert llm.model_name == "vision-model"
    assert llm.openai_api_key.get_secret_value() == "vision-key"
    assert llm.openai_api_base == "https://vision.invalid/v1"
    assert llm.max_tokens == 4096


@pytest.mark.unit
def test_enable_thinking_override(llm_settings):
    """enable_thinking 可逐调用覆盖（全局开、本调用关）。"""
    llm_settings.llm_enable_thinking = True  # 全局开启

    llm = build_chat_openai(
        temperature=0.1,
        max_tokens=1024,
        enable_thinking=False,
    )
    # 关闭时显式注入 False（qwen3 省略该字段仍会走 thinking，耗时反而更长）
    assert llm.extra_body.get("enable_thinking") is False


@pytest.mark.unit
def test_timeout_and_retries_applied(llm_settings):
    """P0 回归：LLM 调用必须带显式 timeout 与受控重试。

    缺失 timeout 时实际超时由 openai SDK 默认值决定（数百秒量级），会绕过
    agent_timeout_* / supervisor_global_timeout，表现为链路挂死且无任何日志。
    """
    llm = build_chat_openai(temperature=0.1, max_tokens=1024)
    # 字段名是 request_timeout（ChatOpenAI 无 timeout 字段，传 timeout= 会被静默忽略）
    assert llm.request_timeout == 20.0  # 取自 settings.llm_timeout_seconds
    assert llm.max_retries == 1  # 取自 settings.llm_max_retries


@pytest.mark.unit
def test_vision_model_setting_wired():
    """vision_model settings 字段存在且可用（A3：qwen3-vl-plus复用文本 key）。"""
    settings = MagicMock()
    settings.llm_enable_thinking = False
    settings.httpx_verify_ssl = True
    settings.llm_api_key = "shared-key"
    settings.llm_base_url = "https://shared.invalid/v1"
    settings.llm_model = "text-model"
    settings.vision_model = "qwen3-vl-plus"
    with patch("ai.llm_client.get_settings", return_value=settings):
        llm = build_chat_openai(
            temperature=0.1,
            max_tokens=1024,
            model=settings.vision_model,
            task_name=LLMTaskName.VISION_ANALYZE,
        )
    assert llm.model_name == "qwen3-vl-plus"
    assert llm.openai_api_key.get_secret_value() == "shared-key"  # 与文本模型同 key
    assert llm.openai_api_base == "https://shared.invalid/v1"  # 同 base_url
    assert llm.get_name() == LLMTaskName.VISION_ANALYZE.value
