# -*- coding: utf-8 -*-
"""跨会话记忆合并（consolidation）— 防同义条目膨胀。

- 确定性去重：按 (kind, NFKC 归一 content) 保留最新一条，删除重复条目
- 相似合并：某 kind 条目数 > 阈值（memory_consolidate_threshold_per_kind）时，
  调用一次 MEMORY_EXTRACT LLM 生成合并建议（Pydantic 校验），替换旧条目；
  LLM 失败/校验不过 → 仅去重不合并（规则兜底）
- 触发点：maybe_extract 成功后顺带执行（同一后台任务，失败不阻塞对话）
- 决策 19：只操作 chat_memory_entries 表（user 分区），绝不写出文件
"""

from __future__ import annotations

import asyncio
import json
import logging
import unicodedata
from pathlib import Path

from langchain_core.messages import HumanMessage

from ai.llm_client import build_chat_openai
from ai.llm_task_name import LLMTaskName
from agent.memory.extractor import MemoryEntry, MemoryExtractOutput

logger = logging.getLogger(__name__)


def _consolidate_prompt() -> str:
    path = Path(__file__).resolve().parent / "prompts" / "consolidate.txt"
    return path.read_text(encoding="utf-8")


def build_consolidate_llm():
    return build_chat_openai(
        temperature=0.2,
        max_tokens=2048,
        task_name=LLMTaskName.MEMORY_EXTRACT,
    )


def _extract_json(text: str) -> dict | None:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


class ConsolidationWorker:
    """记忆合并工作器：独立 LLM，与主 agent 零共享。"""

    def __init__(self, llm=None):
        self._llm = llm or build_consolidate_llm()

    async def consolidate(self, *, repo, user_id: str) -> dict:
        """执行合并：确定性去重 + 超限 kind 的 LLM 合并。返回统计。"""
        from config import get_settings

        settings = get_settings()
        threshold = int(getattr(settings, "memory_consolidate_threshold_per_kind", 15))
        entries = repo.list_memory_entries(user_id, limit=1000, max_chars=10**6)
        stats: dict = {"deduped": 0, "merged_kinds": []}

        by_kind: dict[str, list[dict]] = {}
        for e in entries:
            by_kind.setdefault(str(e.get("kind", "")), []).append(e)

        # 1) 确定性去重（防御层；DB upsert 已按 md5 精确去重，这里归一化后再兜底）
        seen: set[tuple[str, str]] = set()
        for kind, items in list(by_kind.items()):
            keep: list[dict] = []
            dup_contents: list[str] = []
            for e in items:
                norm = unicodedata.normalize("NFKC", str(e.get("content", ""))).strip()
                key = (kind, norm)
                if key in seen:
                    dup_contents.append(str(e.get("content", "")))
                    stats["deduped"] += 1
                    continue
                seen.add(key)
                keep.append(e)
            if dup_contents:
                repo.delete_memory_entries(user_id, dup_contents)
            by_kind[kind] = keep

        # 2) LLM 相似合并（仅超限 kind）
        for kind, items in by_kind.items():
            if not items or len(items) <= threshold:
                continue
            merged = await self._merge_kind(kind, items)
            if not merged:
                logger.warning("memory consolidate skipped (llm fail), kind=%s", kind)
                continue
            # 原子替换：单事务内删旧 + 写新（避免中途崩溃丢失该 kind 记忆）
            repo.replace_memory_entries(
                user_id,
                delete_contents=[e["content"] for e in items],
                upsert_entries=[(kind, content) for content in merged],
            )
            stats["merged_kinds"].append(kind)
        return stats

    async def _merge_kind(self, kind: str, items: list[dict]) -> list[str] | None:
        """单 kind 合并提案：LLM → Pydantic 校验。失败返回 None（仅去重不合并）。"""
        lines = [f"- ({e.get('kind', kind)}) {e.get('content')}" for e in items[:60]]
        content = (
            f"{_consolidate_prompt()}\n\n<kind>\n{kind}\n</kind>\n\n<entries>\n"
            + "\n".join(lines)
            + "\n</entries>"
        )
        try:
            resp = await asyncio.wait_for(self._llm.ainvoke([HumanMessage(content=content)]), timeout=60.0)
            raw = _extract_json(str(resp.content or ""))
            if raw is None:
                raise ValueError("输出不是合法 JSON")
            parsed = MemoryExtractOutput.model_validate(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory consolidate llm failed: %s", str(exc)[:150])
            return None
        return [e.content for e in parsed.entries]