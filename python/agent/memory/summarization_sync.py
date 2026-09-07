# -*- coding: utf-8 -*-
"""压缩 middleware 子类（Phase 4 P0-A，评审 v1.2 修正）。

职责：
1. 写后同步（A6）：deepagents `SummarizationMiddleware` 触发压缩后，把摘要复制进
   `chat_session_compactions` 表（先落库成功再推进；失败仅告警不阻塞主流程）。
2. fallback（A4）：LLM 摘要失败被 langchain 吞成 `"Error generating summary: ..."`
   前缀字符串返回、不会冒泡 —— 主检测点 = 覆写 `_create_summary` 检查返回前缀，
   命中则规则式截断（保留最近消息）+ status='fallback'，绝不静默。
3. 双模板（A5）：单模板无法注入 `<previous-summary>` —— `_create_summary` /
   `_acreate_summary`（异步实时路径）共用 `_resolve_summary_prompt` 二选一：首轮用六节
   `summarize.txt`，已有 compaction 用 `summarization_update.txt`
   （preserve/add/update/可删规则 + <previous-summary> 占位）。
4. 防抖：同 session 60s 内只真正落库一次（重复触发仅正常生成摘要、跳过落库）。
5. 无 thread 上下文（report/evaluation/recommend 等子 agent）→ 全部 no-op。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from langgraph.config import get_config
from langchain_core.messages import AnyMessage

from deepagents.middleware.summarization import SummarizationMiddleware
from langchain.agents.middleware.types import ExtendedModelResponse

from agent.memory.tokens import estimate_context_tokens
from config.model_catalog import get_model_meta

logger = logging.getLogger(__name__)

_FALLBACK_PREFIX = "Error generating summary"
_DEBOUNCE_SECONDS = 60.0
_FALLBACK_LINE_CHARS = 200
_FALLBACK_KEEP_LINES = 20


class SummarizationSyncMiddleware(SummarizationMiddleware):
    """SummarizationMiddleware 子类：压缩落库 + fallback + 双模板（Phase 4 P0-A）。"""

    def __init__(
        self,
        model,
        *,
        backend,
        repo=None,
        summarize_prompt: str | None = None,
        update_prompt: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, backend=backend, **kwargs)
        self._repo = repo
        self._summarize_prompt = summarize_prompt or self._lc_helper.summary_prompt
        self._update_prompt = update_prompt or self._summarize_prompt
        self._last_compaction_ts: dict[str, float] = {}
        self._pending_fallback: set[str] = set()
        # 异步双模板需要 swap 共享 summary_prompt；多会话并发压缩时串行化，防模板串台
        self._summary_lock: asyncio.Lock | None = None

    # ── 上下文提取 ───────────────────────────────────────────────────
    def _current_context(self) -> tuple[str | None, str | None]:
        """从 langgraph config 取 thread_id / user_id（无则 None → no-op）。"""
        try:
            cfg = get_config() or {}
        except Exception:  # noqa: BLE001
            return None, None
        configurable = (cfg or {}).get("configurable") or {}
        return configurable.get("thread_id"), configurable.get("user_id")

    # ── 双模板 + fallback（同步主路径；wrap_model_call 调 _create_summary）──
    def _resolve_summary_prompt(self, thread_id: str | None) -> str | None:
        """双模板选择（A5）：已有 compaction → 增量合并模板；否则首轮六节模板。

        返回注入好 <previous-summary> 的 update 模板；无 thread / 无 repo / 无历史 /
        读库失败 → None（调用方维持首轮模板）。sync/async 共用同一决策，避免双路径漂移。
        """
        if not thread_id or self._repo is None:
            return None
        try:
            prev = self._repo.get_latest_compaction(thread_id)
        except Exception:  # noqa: BLE001 —— 读库失败维持首轮模板，不阻塞压缩
            return None
        if prev and prev.get("summary"):
            return self._update_prompt.replace("{previous_summary}", str(prev["summary"]))
        return None

    def _create_summary(self, messages_to_summarize: list[AnyMessage]) -> str:
        thread_id, _ = self._current_context()
        old_prompt = self._lc_helper.summary_prompt
        resolved = self._resolve_summary_prompt(thread_id)
        # 无历史 / 无 repo 时也显式设回首轮模板（旧语义：每次都用 summarize_prompt）
        target = resolved if resolved is not None else self._summarize_prompt
        if target is not None and target != old_prompt:
            self._lc_helper.summary_prompt = target
        try:
            try:
                summary = super()._create_summary(messages_to_summarize)
            except Exception:  # noqa: BLE001 —— langchain 一般已吞，双保险
                summary = f"{_FALLBACK_PREFIX}: {type(messages_to_summarize).__name__}"
        finally:
            self._lc_helper.summary_prompt = old_prompt
        if not summary or summary.startswith(_FALLBACK_PREFIX):
            if thread_id:
                self._pending_fallback.add(thread_id)
            return self._fallback_summary(messages_to_summarize)
        return summary

    # ── 异步路径（deepagents awrap_model_call / compact-tool async 调 _acreate_summary）──
    async def _acreate_summary(self, messages_to_summarize: list[AnyMessage]) -> str:
        """异步摘要：与同步路径一致走双模板（首轮六节 / 已有 compaction 增量合并）。

        异步下模板要写入共享的 self._lc_helper.summary_prompt，而生成期间有 await，
        多会话并发压缩可能串模板 → 用实例级 asyncio.Lock 串行化 swap+生成+还原。
        """
        if self._summary_lock is None:
            self._summary_lock = asyncio.Lock()
        async with self._summary_lock:
            thread_id, _ = self._current_context()
            old_prompt = self._lc_helper.summary_prompt
            resolved = self._resolve_summary_prompt(thread_id)
            # 无历史 / 无 repo 时也显式设回首轮模板（旧语义：每次都用 summarize_prompt）
            target = resolved if resolved is not None else self._summarize_prompt
            if target is not None and target != old_prompt:
                self._lc_helper.summary_prompt = target
            try:
                try:
                    summary = await super()._acreate_summary(messages_to_summarize)
                except Exception:  # noqa: BLE001
                    summary = f"{_FALLBACK_PREFIX}: async"
            finally:
                self._lc_helper.summary_prompt = old_prompt
        if not summary or summary.startswith(_FALLBACK_PREFIX):
            if thread_id:
                self._pending_fallback.add(thread_id)
            return self._fallback_summary(messages_to_summarize)
        return summary
    def _fallback_summary(self, messages_to_summarize: list[AnyMessage]) -> str:
        """规则式截断：保留最近若干条消息的 content 前 N 字符，绝不崩会话。"""
        lines: list[str] = []
        for m in messages_to_summarize:
            content = getattr(m, "content", "") or ""
            if isinstance(content, list):
                content = "".join(
                    item.get("text", "") for item in content if isinstance(item, dict)
                )
            text = str(content).strip()
            if text:
                lines.append(text[:_FALLBACK_LINE_CHARS])
        kept = lines[-_FALLBACK_KEEP_LINES:]
        return "（摘要生成失败，已降级为规则式截断，status=fallback）\n" + "\n".join(kept)

    # ── 写后同步 ─────────────────────────────────────────────────────
    async def awrap_model_call(self, request, handler):
        result = await super().awrap_model_call(request, handler)
        event = None
        if isinstance(result, ExtendedModelResponse) and result.command is not None:
            update = getattr(result.command, "update", None) or {}
            if isinstance(update, dict):
                event = update.get("_summarization_event")
        if event:
            await self._persist_compaction(event)
        return result

    async def _persist_compaction(self, event: dict) -> None:
        """先落库成功再推进；失败仅告警；防抖 60s；无 user_id/thread_id 则 no-op。"""
        thread_id, user_id = self._current_context()
        if not thread_id or not user_id or self._repo is None:
            return
        now = time.monotonic()
        last = self._last_compaction_ts.get(thread_id, 0.0)
        if now - last < _DEBOUNCE_SECONDS:
            return
        try:
            summary_message = event.get("summary_message")
            summary = getattr(summary_message, "content", "") or ""
            if isinstance(summary, list):
                summary = "".join(
                    item.get("text", "") for item in summary if isinstance(item, dict)
                )
            status = "fallback" if thread_id in self._pending_fallback else "ok"
            self._pending_fallback.discard(thread_id)
            prev = self._repo.get_latest_compaction(thread_id)
            model_name = getattr(self.model, 'model_name', None) or getattr(self.model, 'name', None) or ''
            model_name = str(model_name)
            usage_json = None
            um = getattr(summary_message, "usage_metadata", None) or {}
            if um:
                usage_json = json.dumps(um, ensure_ascii=False)
            self._repo.append_compaction(
                user_id=user_id,
                session_id=thread_id,
                summary=summary,
                prev_compaction_id=int(prev["id"]) if prev else None,
                first_kept_message_id=int(event.get("cutoff_index") or 0),
                tokens_before=0,
                tokens_after=0,
                reserve_tokens=0,
                keep_recent_tokens=0,
                model=model_name,
                reason="threshold",
                status=status,
                usage_json=usage_json,
                details_json=json.dumps(
                    {"middleware": "summarization_sync", "fallback": status == "fallback"},
                    ensure_ascii=False,
                ),
            )
            self._last_compaction_ts[thread_id] = now
            logger.info(
                "summarization_sync.persisted session_id=%s user_id=%s status=%s",
                thread_id,
                user_id,
                status,
            )
        except Exception as exc:  # noqa: BLE001 —— 写库失败仅告警，绝不阻塞对话
            logger.warning("summarization_sync.persist_failed session_id=%s err=%s", thread_id, exc)


def estimate_session_tokens(messages: list[AnyMessage], usage_json: dict | str | None = None) -> int:
    """供压缩前 token 估算（A3 入口，写后同步 details 用）。"""
    return estimate_context_tokens(messages, usage_json)


def model_window(model_name: str) -> int:
    """catalog 查询上下文窗口（A7 入口）。"""
    return get_model_meta(model_name).context_window
