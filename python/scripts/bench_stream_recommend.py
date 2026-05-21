"""
End-to-end benchmark for /api/v1/recommend/stream

Usage:
  python scripts/bench_stream_recommend.py [--cold] [--runs 3]

Extracts total_latency_ms from SSE "done" event and measures client wall-clock.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.request
from urllib.error import URLError


PAYLOAD = {
    "user_id": "bench_test_user",
    "scene": "course_selection",
    "num_items": 3,
    "prompt": "想找不考试、作业少的人文艺术公选课，东校区优先",
    "context": {"avoid_time_slots": ["周三第9-10节"]},
}

API_URL = "http://localhost:8000/api/v1/recommend/stream"
RECALL_PATTERN = "recall:*"


def flush_recall_cache() -> None:
    import subprocess

    try:
        result = subprocess.run(
            ["docker", "exec", "multi-agent-course-system-redis-1", "redis-cli", "KEYS", RECALL_PATTERN],
            capture_output=True, text=True, timeout=10,
        )
        keys = [k.strip() for k in result.stdout.strip().split("\n") if k.strip()]
        if keys:
            subprocess.run(
                ["docker", "exec", "multi-agent-course-system-redis-1", "redis-cli", "DEL"] + keys,
                capture_output=True, timeout=10,
            )
            print(f"  flushed {len(keys)} redis recall keys")
    except Exception as exc:
        print(f"  flush warning: {exc}")


def call_stream_api() -> tuple[float, float | None]:
    """Calls the SSE stream endpoint. Returns (client_wall_ms, server_total_ms)."""
    t0 = time.perf_counter()
    server_ms: float | None = None

    data = json.dumps(PAYLOAD).encode("utf-8")
    req = urllib.request.Request(API_URL, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
    except URLError as exc:
        print(f"  ERROR: {exc}")
        return 0.0, None

    client_ms = (time.perf_counter() - t0) * 1000

    for line in raw.split("\n"):
        if line.startswith("data:") and '"total_latency_ms"' in line:
            try:
                payload = json.loads(line[5:].strip())
                server_ms = float(payload.get("total_latency_ms", 0))
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

    return client_ms, server_ms


def run_bench(label: str, runs: int, cold: bool) -> dict[str, float]:
    print(f"\n--- {label} ({runs} runs) ---")
    client_lats: list[float] = []
    server_lats: list[float] = []

    for i in range(runs):
        if cold:
            flush_recall_cache()
            time.sleep(0.5)

        client_ms, server_ms = call_stream_api()
        client_lats.append(client_ms)
        if server_ms is not None:
            server_lats.append(server_ms)

        tag = f"run {i + 1}"
        if server_ms is not None:
            print(f"  {tag}: client={client_ms:.0f}ms  server={server_ms:.0f}ms")
        else:
            print(f"  {tag}: client={client_ms:.0f}ms  server=N/A")
        time.sleep(1.0)

    result = {
        "client_avg": statistics.mean(client_lats),
        "client_min": min(client_lats),
        "client_max": max(client_lats),
    }
    if server_lats:
        result.update({
            "server_avg": statistics.mean(server_lats),
            "server_min": min(server_lats),
            "server_max": max(server_lats),
        })
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cold", action="store_true", help="Flush recall cache before each run")
    parser.add_argument("--runs", type=int, default=3, help="Number of runs per scenario")
    parser.add_argument("--label", default="baseline", help="Label for this test session")
    args = parser.parse_args()

    print(f"Stream recommend benchmark [{args.label}]")
    sys.stdout.flush()

    # Cold cache
    cold_result = run_bench("cold cache", args.runs, cold=True)

    # Warm cache: same payload, no flush
    warm_result = run_bench("warm cache", args.runs, cold=False)

    # Print summary
    print(f"\n=== Summary [{args.label}] ===")
    for scenario, result in [("cold", cold_result), ("warm", warm_result)]:
        print(f"  {scenario}:")
        print(f"    client  avg={result['client_avg']:.0f}ms  min={result['client_min']:.0f}ms  max={result['client_max']:.0f}ms")
        if "server_avg" in result:
            print(f"    server  avg={result['server_avg']:.0f}ms  min={result['server_min']:.0f}ms  max={result['server_max']:.0f}ms")


if __name__ == "__main__":
    main()
