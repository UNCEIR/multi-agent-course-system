from __future__ import annotations

from enum import Enum


class LLMTaskName(str, Enum):
    """LLM/Embedding 调用场景名称枚举。

    每个枚举值对应一个调用场景，会作为 ``run_name`` 传递到 LangSmith trace，
    替代默认的类名，便于在监控平台按业务维度识别调用。
    """

    # ── LLM 场景 ────────────────────────────────────────────────────
    STUDENT_PROFILE = "student_profile"
    COURSE_RERANK = "course_rerank"
    COURSE_FEASIBILITY = "course_feasibility"
    RECOMMENDATION_REASON = "recommendation_reason"
    SEMANTIC_FILTER = "semantic_filter"
    REACT_ORCHESTRATOR = "react_orchestrator"
    GRAPH_SEMANTIC_FILTER = "graph_semantic_filter"

    # ── v2.0.0 主 Agent 场景 ──────────────────────────────────────────
    MAIN_AGENT_ROUTER = "main_agent_router"  # 主 agent 意图识别 + 路由
    CHAT_SUMMARY = "chat_summary"  # 对话摘要（compaction 用）

    # ── Embedding 场景 ──────────────────────────────────────────────
    COURSE_RECALL = "course_recall"  # 在线召回/搜索（course_recall_agent + main.py 探活）
    BACKFILL = "backfill"  # 离线批量回填（backfill_milvus_vectors.py）