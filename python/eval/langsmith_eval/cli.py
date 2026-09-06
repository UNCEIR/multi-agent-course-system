# -*- coding: utf-8 -*-
"""Phase 4 LangSmith 原生评测 CLI。

用法（cwd=python）：
    python eval/langsmith_eval/cli.py --feature chat_intent --dry-run        # mock target + D evaluator，落盘报告（不烧 LLM）
    python eval/langsmith_eval/cli.py --feature chat_intent --publish-only   # 发布 dataset 到 LangSmith（需 key）
    python eval/langsmith_eval/cli.py --feature chat_intent --live           # aevaluate 真调（需 key + 本地 API + 配额，Phase 3）
    python eval/langsmith_eval/cli.py --list-features

报告落盘：python/eval/reports/langsmith/<feature>-<date>.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# 脚本运行时把 python/ 加入 sys.path（pytest 由 pytest.ini pythonpath=. 提供）
_PY_ROOT = Path(__file__).resolve().parents[2]
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("langsmith_eval")

PY_ROOT = _PY_ROOT
REPORTS_DIR = PY_ROOT / "eval" / "reports" / "langsmith"

FEATURES = ["chat_intent", "recommend", "report", "evaluation", "kb_rag", "memory", "sse", "image_generate"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def _run_dry(feature: str) -> dict:
    """mock target + 确定性 evaluator 本地执行，返回报告 dict（不连 LangSmith、不调 LLM）。"""
    from eval.langsmith_eval import datasets, targets
    from eval.langsmith_eval.evaluators.deterministic import get_deterministic

    cases = datasets.load_cases(feature)
    examples = datasets.map_examples(cases)
    mock = targets.get_target(feature, live=False)
    evaluators = get_deterministic(feature)

    rows = []
    for ex in examples:
        ref_out = ex["outputs"]
        out = mock(ex["inputs"], ref_out)
        evals = []
        for ev in evaluators:
            r = ev(ex["inputs"], out, ref_out)
            evals.append(r)
        rows.append(
            {
                "case_id": ex["inputs"]["case_id"],
                "difficulty": ex["metadata"].get("difficulty"),
                "mode": ex["metadata"].get("mode"),
                "evaluations": evals,
                "pass": all(e["score"] >= 1.0 for e in evals),
            }
        )
    passed = sum(1 for r in rows if r["pass"])
    report = {
        "date": _utc_now(),
        "feature": feature,
        "mode": "dry-run",
        "total": len(rows),
        "passed": passed,
        "pass_rate": round(passed / len(rows), 3) if rows else 0.0,
        "evaluator": "deterministic",
        "results": rows,
    }
    return report


def _write_report(feature: str, report: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{feature}-{date.today().isoformat()}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

def _serialize(value):
    """宽松序列化 LangSmith 结果对象（dict/list/dataclass）。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict()
        except Exception:
            pass
    try:
        import dataclasses
        if dataclasses.is_dataclass(value):
            return dataclasses.asdict(value)
    except Exception:
        pass
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return str(value)


def _run_live(feature: str, sample: int | None = None) -> dict:
    """LangSmith aevaluate：target 真调本地 API/管线 -> D + LLM-judge evaluator -> experiment。"""
    from eval.langsmith_eval import datasets, targets
    from eval.langsmith_eval.evaluators.deterministic import get_deterministic
    from eval.langsmith_eval.evaluators.llm_judge import llm_judge_evaluator

    cases = datasets.load_cases(feature)
    datasets.publish(feature, cases)  # 全量发布；已存在跳过；不可达告警不阻塞
    dataset_name = datasets.dataset_name(feature)
    target = targets.get_target(feature, live=True)
    evaluators = [*get_deterministic(feature), llm_judge_evaluator]

    # langsmith 0.10.16 的 aevaluate(data=list[Example]) 有内部 bug（tee(function)），
    # 统一走同步 evaluate + 同步 target/evaluator（llm_judge 用 asyncio.run 同步入口）。
    from eval.langsmith_eval.evaluators.llm_judge import llm_judge_evaluator_sync
    from langsmith import evaluate

    sync_evaluators = [llm_judge_evaluator_sync if ev is llm_judge_evaluator else ev for ev in evaluators]

    data: object = dataset_name
    if sample:
        from langsmith import Client

        client = Client()
        examples = list(client.list_examples(dataset_name=dataset_name))
        data = examples[:sample]

    results = evaluate(
        target,
        data=data,
        evaluators=sync_evaluators,
        max_concurrency=1,
        num_repetitions=1,
        experiment_prefix=f"phase4-{feature}",
    )
    rows = []
    for item in results:
        rows.append(_serialize(item))

    # pass 判定（宽松）：读取每个 item 的 evaluation_results 分数
    passed = 0
    for row in rows:
        evals = row.get("evaluation_results") if isinstance(row, dict) else None
        if isinstance(evals, dict):
            evals = evals.get("results") or evals.get("evaluation_results") or []
        ok = True
        detail = []
        if isinstance(evals, list):
            scored = 0
            for e in evals:
                if not isinstance(e, dict):
                    continue
                key = e.get("key") or e.get("feedback_key") or ""
                s = e.get("score")
                if not isinstance(s, (int, float)):
                    continue
                scored += 1
                thr = 0.6 if key == "llm_judge" else 1.0  # LLM judge 用 judge.py 默认 0.6；D 层 1.0
                ok = ok and s >= thr
                detail.append(f"{key}={s}")
        row["_pass"] = ok and scored > 0
        row["_detail"] = "; ".join(detail)
        if row.get("_pass"):
            passed += 1
    report = {
        "date": _utc_now(),
        "feature": feature,
        "mode": "live",
        "total": len(rows),
        "passed": passed,
        "pass_rate": round(passed / len(rows), 3) if rows else 0.0,
        "evaluator": "deterministic+llm_judge",
        "experiment": "phase4-" + feature,
        "results": rows,
    }
    return report





def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 4 LangSmith 原生评测 CLI")
    parser.add_argument("--feature", default=None, help="功能点：chat_intent/recommend/...")
    parser.add_argument("--list-features", action="store_true", help="列出功能点")
    parser.add_argument("--publish-only", action="store_true", help="只发布 dataset 到 LangSmith")
    parser.add_argument("--dry-run", action="store_true", help="mock target + D evaluator（默认，不烧 LLM）")
    parser.add_argument("--live", action="store_true", help="aevaluate 真调（需 key+本地 API+配额）")
    parser.add_argument("--sample", type=int, default=None, help="仅跑前 N 条")
    args = parser.parse_args()

    if args.list_features or args.feature is None:
        print("features:", ", ".join(FEATURES))
        return

    feature = args.feature
    try:
        from ai.tracing import configure_langsmith_tracing
        configure_langsmith_tracing()
    except Exception as exc:  # noqa: BLE001
        logger.warning("tracing 未激活（%s）", str(exc)[:80])

    if args.publish_only:
        from eval.langsmith_eval import datasets
        name = datasets.publish(feature)
        print(f"publish -> {name or 'SKIPPED(不可达/失败)'}")
        return

    if args.live:
        report = _run_live(feature, args.sample)
        path = _write_report(feature, report)
        keys = [k for k in ("feature", "mode", "total", "passed", "pass_rate", "experiment") if k in report]
        print(json.dumps({k: report[k] for k in keys}, ensure_ascii=False))
        print(f"report -> {path}")
        return

    report = asyncio.run(_run_dry(feature))
    if args.sample:
        report["results"] = report["results"][: args.sample]
        report["total"] = len(report["results"])
        report["passed"] = sum(1 for r in report["results"] if r["pass"])
        report["pass_rate"] = round(report["passed"] / report["total"], 3) if report["total"] else 0.0
    path = _write_report(feature, report)
    print(json.dumps({k: report[k] for k in ("feature", "mode", "total", "passed", "pass_rate")}, ensure_ascii=False))
    print(f"report -> {path}")


if __name__ == "__main__":
    main()


