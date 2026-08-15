"""Phase 0 POC: deepagents + 中转站 + Docker 三轴验证。

不依赖 v1 业务模块，仅复用 v1 的中转站配置（config.get_settings）。
对应 docs/v2.0.0/notes/2026-07-29-phase-0-deepagents-poc详细计划.md。

用法（本地）：
    cd python
    python scripts/poc_deepagents.py                 # 默认 thinking=on，带 tool
    python scripts/poc_deepagents.py --no-tool       # 第2步：纯 LLM 基线
    python scripts/poc_deepagents.py --no-thinking   # 第4步：thinking off 对照

退出码：0=成功；1=异常（含 tool-calling 未生效）。
"""
from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

# 与 v1 脚本（ingest_course_dataset.py）一致：把 python/ 加入 path 以便 import config
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from deepagents import create_deep_agent

from config import get_settings


@tool
def add(a: float, b: float) -> float:
    """Return the sum of two numbers. Use for any arithmetic addition."""
    return a + b


def build_poc_llm(*, enable_thinking: bool) -> ChatOpenAI:
    """复用 v1 的中转站配置（one.zhique.cn / qwen3.6-max-preview / verify_ssl）。

    与 services/llm_client.py:_create_chat_openai 保持一致的 SSL 处理。
    """
    s = get_settings()
    http_client = httpx.Client(verify=s.httpx_verify_ssl)
    http_async_client = httpx.AsyncClient(verify=s.httpx_verify_ssl)
    extra_body = {"enable_thinking": True} if enable_thinking else None
    return ChatOpenAI(
        api_key=s.llm_api_key,
        base_url=s.llm_base_url,
        model=s.llm_model,
        temperature=0.1,
        max_tokens=1024,
        http_client=http_client,
        http_async_client=http_async_client,
        extra_body=extra_body,
    )


def run_no_tool(llm: ChatOpenAI) -> int:
    """第2步：纯 LLM 调用，验证中转站基线连通 + 无 SSL 报错。"""
    print("=== 第2步：纯 LLM 调用（轴B基线）===")
    resp = llm.invoke("用一句中文说你好，并说明你是什么模型。")
    print("回答:", resp.content)
    print("=== 第2步：通过 ===")
    return 0


def run_with_tool(llm: ChatOpenAI) -> int:
    """第3步：带 tool 的 ReAct 循环，验证 tool-calling 双向兼容。"""
    print("=== 第3步：带 tool 的 ReAct 循环（轴B tool-calling）===")
    agent = create_deep_agent(
        model=llm,
        tools=[add],
        system_prompt=(
            "You are a POC assistant. For any arithmetic, you MUST call the `add` tool "
            "and report the tool's returned value. Do not compute arithmetic yourself."
        ),
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "用 add 工具算 3 + 5，然后用中文解释结果。"}]}
    )

    messages = result["messages"]
    print("=== 消息链 ===")
    tool_call_seen = False
    tool_result_seen = False
    final_refs_8 = False
    for m in messages:
        mtype = getattr(m, "type", type(m).__name__)
        content = str(getattr(m, "content", ""))
        tool_calls = getattr(m, "tool_calls", None)
        line = f"[{mtype}] {content[:160]}"
        if tool_calls:
            line += f"  tool_calls={tool_calls}"
            tool_call_seen = True
        print(line)
        # Tool message 内容应为 8
        if mtype == "tool":
            if "8" in content:
                tool_result_seen = True
        if mtype == "ai" and not tool_calls and "8" in content:
            final_refs_8 = True

    print("=== 判定 ===")
    print(f"  tool_call 触发: {tool_call_seen}")
    print(f"  tool_result 含 8: {tool_result_seen}")
    print(f"  最终回答引用 8: {final_refs_8}")

    if tool_call_seen and tool_result_seen and final_refs_8:
        print("=== 第3步：通过（tool-calling 双向兼容）===")
        return 0
    print("=== 第3步：未通过（tool-calling 单向或未生效）===")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 0 deepagents POC")
    parser.add_argument("--no-tool", action="store_true", help="第2步：仅纯 LLM 调用，不挂 tool")
    parser.add_argument("--no-thinking", action="store_true", help="第4步：关闭 enable_thinking 对照")
    args = parser.parse_args()

    enable_thinking = not args.no_thinking
    print(f"配置: enable_thinking={enable_thinking}, base_url={get_settings().llm_base_url}, "
          f"model={get_settings().llm_model}, verify_ssl={get_settings().httpx_verify_ssl}")

    try:
        llm = build_poc_llm(enable_thinking=enable_thinking)
        if args.no_tool:
            return run_no_tool(llm)
        return run_with_tool(llm)
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
