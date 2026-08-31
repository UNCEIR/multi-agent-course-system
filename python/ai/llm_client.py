from __future__ import annotations

import httpx
from langchain_openai import ChatOpenAI

from config import get_settings
from ai.llm_task_name import LLMTaskName


def build_chat_openai(
    *,
    temperature: float,
    max_tokens: int,
    streaming: bool = False,
    task_name: LLMTaskName | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    enable_thinking: bool | None = None,
) -> ChatOpenAI:
    settings = get_settings()
    llm = _create_chat_openai(
        temperature=temperature,
        max_tokens=max_tokens,
        streaming=streaming,
        model=model,
        base_url=base_url,
        api_key=api_key,
        enable_thinking=enable_thinking,
    )
    if task_name is not None:
        # 用 pydantic 的 name 字段命名 trace（LangSmith 的 run name 取自
        # get_name()），同时保持返回类型为 BaseChatModel——deepagents 无法
        # 解析 with_config 产生的 RunnableBinding。
        llm.name = task_name.value
    return llm


def build_tool_calling_llm(
    tools: list[dict],
    *,
    temperature: float = 0.1,
    max_tokens: int = 4096,
    task_name: LLMTaskName | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    enable_thinking: bool | None = None,
) -> ChatOpenAI:
    llm = _create_chat_openai(
        temperature=temperature,
        max_tokens=max_tokens,
        model=model,
        base_url=base_url,
        api_key=api_key,
        enable_thinking=enable_thinking,
    )
    if task_name is not None:
        # _ChatModelBinding.get_name() 委托给内部 bound，故在 bind 前命名。
        llm.name = task_name.value
    return llm.bind_tools(tools, tool_choice="auto")


def _create_chat_openai(
    *,
    temperature: float,
    max_tokens: int,
    streaming: bool = False,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    enable_thinking: bool | None = None,
) -> ChatOpenAI:
    settings = get_settings()
    extra_body = {}
    # Phase 2 扩展：enable_thinking 可逐调用覆盖（None 时沿用全局开关）
    if enable_thinking is None:
        enable_thinking = settings.llm_enable_thinking
    # 必须显式传布尔值：qwen3 在 DashScope 兼容模式下，省略该字段时默认仍走 thinking，
    # 只有显式 false 才会真正关闭思考链（实测省略时耗时反而更长）。
    extra_body["enable_thinking"] = bool(enable_thinking)

    verify = settings.httpx_verify_ssl
    # P0 修复：显式设置超时。缺失时实际超时由 openai SDK 默认值决定（数百秒量级），
    # 会绕过 agent_timeout_* 与 supervisor_global_timeout，表现为 SSE 链路静默挂死、前端空流。
    # 用 getattr + 类型校验兜底：部分测试以 MagicMock 模拟 settings 且不含这些字段，
    # 此时回退为 None（不显式限制），保证既有调用点行为不回归。
    timeout_seconds = getattr(settings, "llm_timeout_seconds", None)
    has_timeout = isinstance(timeout_seconds, (int, float))
    timeout = None
    if has_timeout:
        connect_seconds = getattr(settings, "llm_connect_timeout_seconds", None)
        timeout = httpx.Timeout(
            float(timeout_seconds),
            connect=float(connect_seconds) if isinstance(connect_seconds, (int, float)) else 5.0,
        )
    http_client = httpx.Client(verify=verify, timeout=timeout)
    http_async_client = httpx.AsyncClient(verify=verify, timeout=timeout)

    llm_max_retries = getattr(settings, "llm_max_retries", None)
    if not isinstance(llm_max_retries, int):
        llm_max_retries = None  # None → 沿用 langchain / openai SDK 默认

    return ChatOpenAI(
        api_key=api_key if api_key is not None else settings.llm_api_key,
        base_url=base_url if base_url is not None else settings.llm_base_url,
        model=model if model is not None else settings.llm_model,
        temperature=temperature,
        max_tokens=max_tokens,
        streaming=streaming,
        extra_body=extra_body or None,
        max_retries=llm_max_retries,
        # 注意字段名是 request_timeout 而非 timeout：ChatOpenAI 无 timeout 字段，
        # 传 timeout= 会被 pydantic 静默忽略、超时完全不生效（排查时极易踩坑）。
        # 必须在此显式传：openai SDK 会用自身默认超时覆盖传入 httpx client 的配置。
        request_timeout=float(timeout_seconds) if has_timeout else None,
        http_client=http_client,
        http_async_client=http_async_client,
    )
