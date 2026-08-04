from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "SupervisorOrchestrator",
    "HardConstraintFilter",
    "build_recommendation_graph",
]

if TYPE_CHECKING:
    from .graph import build_recommendation_graph
    from .hard_constraint_filter import HardConstraintFilter
    from .supervisor import SupervisorOrchestrator


def __getattr__(name: str):
    if name == "SupervisorOrchestrator":
        from .supervisor import SupervisorOrchestrator

        return SupervisorOrchestrator
    if name == "HardConstraintFilter":
        from .hard_constraint_filter import HardConstraintFilter

        return HardConstraintFilter
    if name == "build_recommendation_graph":
        from .graph import build_recommendation_graph

        return build_recommendation_graph
    raise AttributeError(f"module 'app.recommend' has no attribute {name!r}")