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
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field, ValidationError

from ai.llm_client import build_chat_openai
from ai.llm_task_name import LLMTaskName

logger = logging.getLogger(__name__)


def _utcnow_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def memory_expires_at(kind: str, ttl_days: int | None):
    """按 kind 计算记忆过期时间：fact 永不过期；preference/decision 设 TTL；ttl<=0 也不过期。

    返回 naive UTC datetime（与存储层保持一致），过期后读取/注入自动隐藏。
    """
    if kind == "fact" or not ttl_days or ttl_days <= 0:
        return None
    return _utcnow_naive() + timedelta(days=int(ttl_days))


def memory_ttl_days(settings) -> int:
    """读取配置的记忆 TTL（天）；缺失/非法回退 30。"""
    try:
        val = getattr(settings, "memory_entry_ttl_days", 30) or 30
        return int(val)
    except (TypeError, ValueError):
        return 30


class MemoryEntry(BaseModel):
    kind: str = Field(..., pattern="^(preference|fact|decision)$")
    content: str = Field(..., min_length=2, max_length=500)


class MemoryExtractOutput(BaseModel):
    entries: list[MemoryEntry]
    # C1：被本次改口直接推翻的旧记忆 content 原样列表（仅当精确出现在 <previous-memory> 中才可删除）
    supersede: list[str] = Field(default_factory=list)


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
        ttl_days: int | None = None,
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

        new_entries = [(e.kind, e.content) for e in parsed.entries]
        new_expires = [memory_expires_at(e.kind, ttl_days) for e in parsed.entries]
        supersede = [str(s).strip() for s in parsed.supersede if s and str(s).strip()]
        # 安全护栏（C1）：只允许删"模型确实看到且原样精确命中"的旧条目，防幻觉误删
        prev_contents = {unicodedata.normalize("NFKC", str(e.get("content", ""))).strip() for e in previous_entries}
        whitelisted = [s for s in supersede if unicodedata.normalize("NFKC", s) in prev_contents]
        if whitelisted:
            repo.replace_memory_entries(
                user_id,
                delete_contents=whitelisted,
                upsert_entries=new_entries,
                upsert_expires=new_expires,
                agent_name="main_agent",
            )
        else:
            for entry in parsed.entries:
                repo.upsert_memory_entry(
                    user_id,
                    entry.kind,
                    entry.content,
                    session_id,
                    agent_name="main_agent",
                    expires_at=memory_expires_at(entry.kind, ttl_days),
                )
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


# ── 信号即时提取（B）：本地正则预筛 + 同 user 限频（进程内）──────────────
_user_last_extract_at: dict[str, float] = {}


def _signal_hit(user_text: str | None, settings) -> bool:
    """本地零成本预筛：强改口组始终生效；弱披露组默认关闭。"""
    if not user_text:
        return False
    from agent.memory.signals import has_disclosure_signal, has_retraction_signal

    if has_retraction_signal(user_text):
        return True
    if getattr(settings, "memory_extract_disclosure_signal_enabled", False) and has_disclosure_signal(user_text):
        return True
    return False


def _user_extract_allowed(user_id: str, min_interval: int) -> bool:
    if min_interval <= 0:
        return True
    last = _user_last_extract_at.get(user_id)
    if last is None:
        return True  # 从未提取过 → 放行（不能用 0.0 兜底：刚开机时 monotonic < min_interval 会误拦截首次）
    return time.monotonic() - last >= min_interval


def _mark_user_extract(user_id: str) -> None:
    _user_last_extract_at[user_id] = time.monotonic()


async def maybe_extract(repo, *, session_id: str, user_id: str, user_text: str | None = None) -> bool:
    """阈值/信号双门触发式提取（forked subagent：独立 MemoryExtractWorker）。

    返回是否执行了提取。匿名/未达标/退避中/限频内 → False。
    - 攒批门：未提取消息数 ≥ memory_extract_threshold_messages（默认 10 ≈ 5 轮）
    - 信号门（B）：当轮 user 文本命中强改口信号（或开启的披露信号），且未提取 ≥1、
      同 user 距上次提取 ≥ memory_extract_min_interval_seconds（默认 60s）→ 立即提取，不等攒批
    """
    from config import get_settings

    if not user_id:
        return False
    settings = get_settings()
    threshold = int(settings.memory_extract_threshold_messages)
    min_interval = int(getattr(settings, "memory_extract_min_interval_seconds", 60))
    signal_hit = _signal_hit(user_text, settings)

    # 廉价预检（锁外）：无信号且未达阈值 → 直接跳过，不做 LLM
    if not signal_hit and repo.count_unextracted(session_id) < threshold:
        return False
    state0 = repo.get_extract_state(session_id)
    if state0["last_failure_at"] and time.time() - state0["last_failure_at"] < settings.memory_extract_retry_after_seconds:
        return False

    lock = repo.session_lock(session_id)
    async with lock:
        # 锁内重读状态：上一轮后台提取可能刚推进水位（避免重复取同一批喂 LLM）
        state = repo.get_extract_state(session_id)
        messages = repo.list_messages(
            session_id,
            after_seq=state["last_extracted_seq"],
            limit=settings.memory_extract_max_messages,
        )
        unextracted = len(messages)
        batch_ready = unextracted >= threshold
        immediate_ok = signal_hit and unextracted >= 1 and _user_extract_allowed(user_id, min_interval)
        if not batch_ready and not immediate_ok:
            return False
        if immediate_ok:
            _mark_user_extract(user_id)
        previous = repo.list_memory_entries(user_id, limit=100, max_chars=3000)
        worker = MemoryExtractWorker()
        ok = await worker.extract(
            repo=repo,
            session_id=session_id,
            user_id=user_id,
            messages=messages,
            previous_entries=previous,
            ttl_days=memory_ttl_days(settings),
        )
        if ok:
            # 提取成功后顺带执行 consolidation（同后台任务；失败仅告警不阻塞）
            try:
                from agent.memory.consolidation import ConsolidationWorker

                await ConsolidationWorker().consolidate(repo=repo, user_id=user_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("memory consolidate failed: %s", str(exc)[:150])
        return ok
