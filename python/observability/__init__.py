from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "MetricsCollector",
    "AgentMetric",
]

if TYPE_CHECKING:
    from .metrics import AgentMetric, MetricsCollector


def __getattr__(name: str):
    if name == "MetricsCollector":
        from .metrics import MetricsCollector

        return MetricsCollector
    if name == "AgentMetric":
        from .metrics import AgentMetric

        return AgentMetric
    raise AttributeError(f"module 'observability' has no attribute {name!r}")