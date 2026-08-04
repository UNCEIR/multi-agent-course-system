from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "ABTestEngine",
    "Experiment",
    "ExperimentGroup",
]

if TYPE_CHECKING:
    from .ab_test import ABTestEngine, Experiment, ExperimentGroup


def __getattr__(name: str):
    if name == "ABTestEngine":
        from .ab_test import ABTestEngine

        return ABTestEngine
    if name == "Experiment":
        from .ab_test import Experiment

        return Experiment
    if name == "ExperimentGroup":
        from .ab_test import ExperimentGroup

        return ExperimentGroup
    raise AttributeError(f"module 'experiment' has no attribute {name!r}")