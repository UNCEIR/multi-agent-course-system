from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["SupervisorOrchestrator", "build_recommendation_graph"]

if TYPE_CHECKING:
    from .graph import build_recommendation_graph
    from .supervisor import SupervisorOrchestrator


def __getattr__(name: str):
    if name == "SupervisorOrchestrator":
        from .supervisor import SupervisorOrchestrator

        return SupervisorOrchestrator
    if name == "build_recommendation_graph":
        from .graph import build_recommendation_graph

        return build_recommendation_graph
    raise AttributeError(f"module 'orchestrator' has no attribute {name!r}")
