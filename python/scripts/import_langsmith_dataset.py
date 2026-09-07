# -*- coding: utf-8 -*-
"""eval_sets（规范 v2）→ LangSmith Dataset 导入。

结构对齐 LangSmith Dataset：inputs / outputs（ground truth）/ reference 三分量。
Phase 4 的 LLM-as-judge evaluator 直接消费同一 Dataset 的 reference。

用法：cd python && python scripts/import_langsmith_dataset.py [--set chat_intent]
需要 LANGCHAIN_API_KEY 配置。LangSmith 不可达 → 打印告警，不阻塞。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EVAL_SETS = Path(__file__).resolve().parent.parent / "eval_sets"


def import_set(name: str) -> None:
    path = EVAL_SETS / f"{name}.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"eval set 不存在: {path}")
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not cases:
        print(f"== {name}: 空集，跳过")
        return

    from langsmith import Client

    client = Client()
    dataset_name = f"phase2-{name}"
    try:
        dataset = client.create_dataset(dataset_name=dataset_name, description=f"Phase 2 eval set (v2): {name}")
    except Exception as exc:  # noqa: BLE001
        print(f"== {name}: 数据集可能已存在（{str(exc)[:80]}），沿用")
        datasets = client.list_datasets(name=dataset_name)
        dataset = datasets[0] if datasets else client.create_dataset(dataset_name=dataset_name)

    client.create_examples(
        dataset_id=dataset.id,
        inputs=[{"input": c.get("input", {}), "case_id": c["case_id"]} for c in cases],
        outputs=[
            {
                "expected": c.get("expected", {}),
                "assertions": c.get("assertions", []),
                "judge": c.get("judge", {}),
            }
            for c in cases
        ],
        reference=[{"reference": c.get("reference", {})} for c in cases],
    )
    print(f"== {name}: 导入 {len(cases)} 个 case（inputs/outputs/reference 三分量）到 '{dataset_name}'")


def attach_judge_scores(name: str, report_path: Path) -> None:
    """Phase 4 G2：把 runner 报告的 judge_results 回写 LangSmith Dataset（evaluator 消费）。

    LangSmith 不可达 / 报告无 judge 段 → 告警不阻塞。
    """
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"== {name}: 读取报告失败 {report_path}（{str(exc)[:80]}）")
        return
    judge_results = report.get("judge_results") or []
    if not judge_results:
        print(f"== {name}: 报告无 judge_results（需先 --judge），跳过回写")
        return
    from langsmith import Client

    client = Client()
    dataset_name = f"phase2-{name}"
    try:
        datasets = list(client.list_datasets(name=dataset_name))
        dataset = datasets[0] if datasets else None
        if dataset is None:
            print(f"== {name}: dataset '{dataset_name}' 不存在，先 --import 再回写")
            return
        examples = list(client.list_examples(dataset_id=dataset.id))
    except Exception as exc:  # noqa: BLE001
        print(f"== {name}: LangSmith 不可达，跳过回写（{str(exc)[:80]}）")
        return
    by_case = {str((e.inputs or {}).get("case_id", "")): e for e in examples}
    updated = 0
    for item in judge_results:
        example = by_case.get(str(item.get("case_id", "")))
        if example is None:
            continue
        outputs = dict(example.outputs or {})
        outputs["judge_scores"] = item.get("judge", {})
        client.update_example(example_id=example.id, outputs=outputs)
        updated += 1
    print(f"== {name}: 回写 {updated}/{len(judge_results)} 个 case 的 judge_scores 到 '{dataset_name}'")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", default=None, help="单个 eval set 名；缺省导入全部")
    parser.add_argument(
        "--judge-results",
        default=None,
        help="Phase 4 G2：把 eval/reports/<set>-<date>.json 的 judge_results 回写 Dataset",
    )
    args = parser.parse_args()
    if args.judge_results:
        attach_judge_scores(args.set or "chat_intent", Path(args.judge_results))
        return
    sets = [args.set] if args.set else [p.stem for p in sorted(EVAL_SETS.glob("*.jsonl")) if p.suffix == ".jsonl"]
    try:
        for name in sets:
            import_set(name)
    except Exception as exc:  # noqa: BLE001
        print(f"!! LangSmith 导入失败（{str(exc)[:120]}）；可稍后重试或仅本地运行 runner")
        sys.exit(1)


if __name__ == "__main__":
    main()
