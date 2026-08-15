# -*- coding: utf-8 -*-
"""LangSmith trace 聚合监控：拉取最近 N 分钟 LLM 调用的 token 消耗/延迟/成本。

用法：cd python && python scripts/trace_usage.py [--minutes 30] [--group-by run_name|model]
需要 LANGCHAIN_API_KEY；LangSmith 不可达 → 打印告警。

回显字段：run_name / model / 调用次数 / input·output·total tokens / 平均·P95 延迟 / 成本。
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=int, default=30, help="回溯分钟数")
    parser.add_argument("--group-by", default="run_name", choices=["run_name", "model"])
    args = parser.parse_args()

    try:
        from langsmith import Client
    except Exception as exc:  # noqa: BLE001
        print(f"!! langsmith 不可用（{str(exc)[:80]}）")
        sys.exit(1)

    client = Client()
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=args.minutes)

    agg: dict[str, dict] = {}
    try:
        runs = client.list_runs(project_name="mult-agent-university-system", start_time=start, end_time=end, run_type="llm")
    except Exception as exc:  # noqa: BLE001
        print(f"!! LangSmith 拉取失败（{str(exc)[:120]}）")
        sys.exit(1)

    for run in runs:
        group = str(getattr(run, args.group_by, None) or "unknown")
        bucket = agg.setdefault(group, {"count": 0, "in": 0, "out": 0, "cost": 0.0, "lats": []})
        bucket["count"] += 1
        um = (run.feedback_stats if hasattr(run, "feedback_stats") else None) or {}
        tokens = getattr(run, "prompt_tokens", None) if hasattr(run, "prompt_tokens") else None
        # run 对象字段因版本而异：优先从 extra/metadata 或直接属性取
        extra = getattr(run, "extra", {}) or {}
        usage = (extra.get("metadata", {}) or {}).get("usage", {}) or {}
        inp = int(usage.get("input_tokens", 0) or 0) or int(getattr(run, "prompt_tokens", 0) or 0)
        out = int(usage.get("output_tokens", 0) or 0) or int(getattr(run, "completion_tokens", 0) or 0)
        cost = float(usage.get("cost", 0) or 0) or float(getattr(run, "total_cost", 0) or 0)
        latency = float(getattr(run, "end_time", None).timestamp() - run.start_time.timestamp()) if getattr(run, "start_time", None) and getattr(run, "end_time", None) else 0.0
        bucket["in"] += inp
        bucket["out"] += out
        bucket["cost"] += cost
        if latency:
            bucket["lats"].append(latency)

    print(f"== LangSmith usage ({args.minutes}min, group_by={args.group_by})")
    total_in = total_out = 0
    for group, b in sorted(agg.items(), key=lambda kv: -kv[1]["count"]):
        lats = sorted(b["lats"])
        p50 = lats[len(lats) // 2] if lats else 0.0
        p95 = lats[min(len(lats) - 1, int(len(lats) * 0.95))] if lats else 0.0
        total_in += b["in"]
        total_out += b["out"]
        print(
            f"  {group:<28} calls={b['count']:<4} in={b['in']:<8} out={b['out']:<8} "
            f"total={b['in'] + b['out']:<8} cost={b['cost']:.4f}$ p50={p50:.1f}s p95={p95:.1f}s"
        )
    print(f"== 合计: {total_in + total_out} tokens (in={total_in} out={total_out})")


if __name__ == "__main__":
    main()
