"""
可选：直连已配置的 OpenAI 兼容 LLM（如 DashScope compatible-mode），产生真实 token。

默认跳过（不占额度）。仅在显式开启时运行：

  # Windows PowerShell
  $env:ECOM_E2E_LLM="1"; pytest tests/test_llm_integration_smoke.py -m integration -v

  # bash
  ECOM_E2E_LLM=1 pytest tests/test_llm_integration_smoke.py -m integration -v

需先在环境中配置 ECOM_LLM_API_KEY、ECOM_LLM_BASE_URL、ECOM_LLM_MODEL（或通过 .env）。
"""

from __future__ import annotations

import os

import pytest
from langchain_core.messages import HumanMessage


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_openai_compatible_llm_smoke_when_e2e_enabled():
    if os.environ.get("ECOM_E2E_LLM", "").strip() != "1":
        pytest.skip(
            "默认跳过以避免计费；设置 ECOM_E2E_LLM=1 且配置 ECOM_LLM_* 后运行本测试。"
        )

    from ai.llm_client import build_chat_openai

    llm = build_chat_openai(temperature=0.0, max_tokens=16)
    response = await llm.ainvoke(
        [HumanMessage(content='只回复两个字母: OK')]
    )
    assert response.content is not None
    assert str(response.content).strip()
