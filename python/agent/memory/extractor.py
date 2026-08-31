# -*- coding: utf-8 -*-
"""跨会话记忆提取（pi 增量摘要移植）。

- 触发：未提取消息数 ≥ threshold 且距上次失败 ≥ 退避间隔
- 范围：seq > last_extracted_seq，oldest-first 分批（≤ max_messages）
- `<previous-summary>` = 该 user 最近 N 条记忆条目聚合文本（无新表）
- 幂等：全部 upsert 成功后才推进水位；失败记时间戳退避，不阻塞对话
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field, ValidationError

from ai.llm_client import build_chat_openai
from ai.llm_task_name import LLMTaskName

logger = logging.getLogger(__name__)


class MemoryEntry(BaseModel):
    kind: str = Field(..., pattern="^(preference|fact|decision)$")
    content: str = Field(..., min_length=2, max_length=500)


class MemoryExtractOutput(BaseModel):
    entries: list[MemoryEntry]


def _prompt() -> str:
    path = Path(__file__).resolve().parent / "prompts" / "memory_extract.txt"
    return path.read_text(encoding="utf-8")


def build_extract_llm():
    return build_chat_openai(
        temperature=0.2,
        max_tokens=2048,
        task_name=LLMTaskName.MEMORY_EXTRACT,
    )


class MemoryExtractWorker:
    """跨会话记忆提取工作器（forked subagent 语义）。

    独立 LLM 实例 + 独立校验/落库/水位推进，与主 agent 零共享
    （无 checkpointer、无 tool、不读主 agent 状态）。由 maybe_extract 在
    后台任务（asyncio.create_task）中调用，失败仅退避记录，绝不阻塞对话。
    """

    def __init__(self, llm=None):
        self._llm = llm or build_extract_llm()

    async def extract(
        self,
        *,
        repo,
        session_id: str,
        user_id: str,
        messages: list[dict],
        previous_entries: list[dict],
    ) -> bool:
        """单次提取：LLM → Pydantic 校验 → upsert 全部 → 推进水位。成功返回 True。"""
        previous_summary = (
            "\n".join(f"- ({e['kind']}) {e['content']}" for e in previous_entries[:30]) or "（无）"
        )
        payload = {
            "conversation": _messages_text(messages),
            "previous_memory": previous_summary,
        }
        content = (
            f"{_prompt()}\n\n<conversation>\n{payload['conversation']}\n</conversation>"
            f"\n\n<previous-memory>\n{payload['previous_memory']}\n</previous-memory>"
        )

        try:
            resp = await asyncio.wait_for(
                self._llm.ainvoke([HumanMessage(content=content)]), timeout=60.0
            )
            raw = _extract_json(str(resp.content or ""))
            if raw is None:
                raise ValueError("输出不是合法 JSON")
            parsed = MemoryExtractOutput.model_validate(raw)
        except (ValidationError, ValueError, asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001
            logger.warning("memory extract failed: %s", str(exc)[:150])
            repo.mark_extract_failure(session_id)
            return False

        for entry in parsed.entries:
            repo.upsert_memory_entry(user_id, entry.kind, entry.content, session_id)
        max_seq = messages[-1]["seq"] if messages else 0
        repo.update_extracted_seq(session_id, max_seq)
        return True


def _messages_text(messages: list[dict], max_chars: int = 8000) -> str:
    """消息序列化为纯文本（供摘要请求；截断防超长）。"""
    lines = []
    total = 0
    for m in messages:
        role = m.get("role", "?")
        content = str(m.get("content", "") or "")[:500]
        line = f"[{role}] {content}"
        total += len(line)
        if total > max_chars:
            lines.append("...（截断）")
            break
        lines.append(line)
    return "\n".join(lines)


def _extract_json(text: str) -> dict | None:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


async def maybe_extract(repo, *, session_id: str, user_id: str) -> bool:
    """阈值触发式提取（forked subagent：独立 MemoryExtractWorker）；返回是否执行了提取。匿名/未达标/退避中 → False。"""
    from config import get_settings

    if not user_id:
        return False
    settings = get_settings()
    threshold = settings.memory_extract_threshold_messages
    if repo.count_unextracted(session_id) < threshold:
        return False
    state = repo.get_extract_state(session_id)
    if state["last_failure_at"] and time.time() - state["last_failure_at"] < settings.memory_extract_retry_after_seconds:
        return False

    lock = repo.session_lock(session_id)
    async with lock:
        messages = repo.list_messages(session_id, after_seq=state["last_extracted_seq"], limit=settings.memory_extract_max_messages)
        if len(messages) < threshold:
            return False
        previous = repo.list_memory_entries(user_id, limit=30, max_chars=3000)
        worker = MemoryExtractWorker()
        ok = await worker.extract(
            repo=repo,
            session_id=session_id,
            user_id=user_id,
            messages=messages,
            previous_entries=previous,
        )
        if ok:
            # 提取成功后顺带执行 consolidation（同后台任务；失败仅告警不阻塞）
            try:
                from agent.memory.consolidation import ConsolidationWorker

                await ConsolidationWorker().consolidate(repo=repo, user_id=user_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("memory consolidate failed: %s", str(exc)[:150])
        return ok
