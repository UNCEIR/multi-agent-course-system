"""Direct fetch_courses benchmark — isolates DB query from full pipeline."""
from __future__ import annotations

import statistics
import time

from config.settings import get_settings
from storage.mysql.course_repo import CourseRepository


def get_repo():
    s = get_settings()
    repo = CourseRepository()
    repo.connect()
    # Ensure schema & indexes exist (idempotent)
    repo.ensure_schema()
    return repo


def bench(repo: CourseRepository, label: str, warmup: int = 2, runs: int = 5, **kwargs):
    for _ in range(warmup):
        repo.fetch_courses(**kwargs)

    latencies: list[float] = []
    for _ in range(runs):
        t0 = time.perf_counter()
        rows = repo.fetch_courses(**kwargs)
        elapsed = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed)

    avg = statistics.mean(latencies)
    mn = min(latencies)
    mx = max(latencies)
    print(f"  {label}")
    print(f"    rows={len(rows)}  avg={avg:.3f}ms  min={mn:.3f}ms  max={mx:.3f}ms")
    return avg


def main():
    repo = get_repo()
    print("CourseRepository.fetch_courses benchmark (warmup=2, runs=5)\n")

    results: dict[str, float] = {}

    results["no_filters"] = bench(repo, "no filters", limit=40)

    results["domain_filter"] = bench(
        repo, "domain='humanities'", limit=40, domains=["人文艺术"]
    )

    results["short_like_2char"] = bench(
        repo, "LIKE 2-char fallback", limit=40, query_text="心理"
    )

    results["long_match"] = bench(
        repo, "FULLTEXT MATCH", limit=40, query_text="不考试作业少"
    )

    results["combined"] = bench(
        repo,
        "domain + FULLTEXT",
        limit=40,
        domains=["人文艺术"],
        query_text="不考试",
    )

    print("\n--- Summary (avg ms) ---")
    for name, avg in results.items():
        print(f"  {name}: {avg:.3f}")


if __name__ == "__main__":
    main()
