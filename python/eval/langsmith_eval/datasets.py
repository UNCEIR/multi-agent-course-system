# -*- coding: utf-8 -*-
"""Phase 4 LangSmith 原生评测：数据集映射与发布。

`python/eval_sets/phase4_<feature>.jsonl` 仍沿用 eval_sets v2 契约（input/expected/reference/judge/
assertions/metadata），是唯一事实源。本模块把它映射成 LangSmith Dataset 原生三分量并发布：

- inputs:  {"case_id", **case["input"]}             # 传给 target 的真实请求
- outputs: {"case_id", "expected", "reference", "judge", "assertions"}  # ground truth，
                                                      # 不传给 target，只注入 evaluator 的 reference_outputs
- metadata: {"mode", "difficulty", "scenario"}

LangSmith 不可达 → 告警不阻塞（与 scripts/import_langsmith_dataset.py 约定一致）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PY_ROOT = Path(__file__).resolve().parents[2]
EVAL_SETS = PY_ROOT / "eval_sets"
FEATURE_PREFIX = "phase4_"
DATASET_PREFIX = "phase4_"


def _feature_path(feature: str) -> Path:
    return EVAL_SETS / f"{FEATURE_PREFIX}{feature}.jsonl"


def load_cases(feature: str) -> list[dict]:
    """读 phase4_<feature>.jsonl（v2 契约）→ list[原始 case]。"""
    path = _feature_path(feature)
    if not path.is_file():
        raise FileNotFoundError(f"phase4 eval set 不存在: {path}")
    cases = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not cases:
        raise ValueError(f"phase4 eval set 为空: {path}")
    return cases


def map_examples(cases: list[dict]) -> list[dict]:
    """原始 case → LangSmith example 形态 [{inputs, outputs, metadata}]。"""
    examples = []
    for c in cases:
        case_id = str(c["case_id"])
        meta = dict(c.get("metadata") or {})
        examples.append(
            {
                "inputs": {"case_id": case_id, **dict(c.get("input") or {})},
                "outputs": {
                    "case_id": case_id,
                    "expected": c.get("expected", {}),
                    "reference": c.get("reference", {}),
                    "judge": c.get("judge", {}),
                    "assertions": c.get("assertions", []),
                },
                "metadata": {
                    "mode": meta.get("mode", "offline"),
                    "difficulty": c.get("difficulty", "medium"),
                    "scenario": c.get("scenario", ""),
                },
            }
        )
    return examples


def dataset_name(feature: str) -> str:
    return f"{DATASET_PREFIX}{feature}"


def publish(feature: str, cases: list[dict] | None = None) -> str | None:
    """把 phase4_<feature> 发布到 LangSmith Dataset（已存在则跳过）。返回 dataset 名或 None。"""
    if cases is None:
        cases = load_cases(feature)
    examples = map_examples(cases)
    name = dataset_name(feature)
    try:
        from langsmith import Client

        client = Client()
    except Exception as exc:  # noqa: BLE001
        logger.warning("LangSmith 不可达，跳过发布 %s（%s）", name, str(exc)[:120])
        return None
    try:
        if client.has_dataset(dataset_name=name):
            logger.info("dataset 已存在: %s（跳过）", name)
            return name
        dataset = client.create_dataset(dataset_name=name, description=f"Phase 4 LangSmith LLM-as-judge: {feature}")
        client.create_examples(dataset_id=dataset.id, examples=examples)
        logger.info("发布 %d 个 example 到 %s", len(examples), name)
        return name
    except Exception as exc:  # noqa: BLE001
        logger.warning("发布 %s 失败（%s）", name, str(exc)[:120])
        return None
