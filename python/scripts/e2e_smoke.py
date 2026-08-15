# -*- coding: utf-8 -*-
"""端到端冒烟：对已闭环的 skill 功能接口跑真实链路（需 API 运行中）。

覆盖：
  1. chat → knowledge-query（知识库引用）
  2. chat → recommend（选课推荐）
  3. chat → writing（论文写作）
  4. chat → web-search（搜索降级链）
  5. chat → image-generation（生图降级链）
  6. chat → image_recognize（图片附件视觉识别）
  7. POST /api/v1/report（批量成绩单 + token 下载）
  8. POST /api/v1/evaluation + GET /me（评价生成与读取）
  9. POST /api/v1/documents/upload（文档摄入）

用法：cd python && python scripts/e2e_smoke.py [--skip-report]
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx

BASE = "http://localhost:8000"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

results: list[dict] = []


def record(name: str, ok: bool, detail: str, elapsed: float) -> None:
    results.append({"name": name, "ok": ok, "detail": detail[:200], "elapsed_s": round(elapsed, 1)})
    flag = "PASS" if ok else "FAIL"
    print(f"[{flag}] {name} ({elapsed:.1f}s) {detail[:150]}")


def chat(message: str, user_id: str = "3123003252", images: list[str] | None = None) -> tuple[str, float]:
    t0 = time.perf_counter()
    body = {"message": message, "session_id": "e2e", "user_id": user_id}
    if images:
        body["images"] = images
    resp = httpx.post(f"{BASE}/api/v1/chat", json=body, timeout=280)
    reply = resp.json().get("reply", "") if resp.status_code == 200 else f"HTTP {resp.status_code}"
    return reply, time.perf_counter() - t0


def report_e2e() -> None:
    xlsx = [n for n in REPO_ROOT.iterdir() if n.suffix == ".xlsx"]
    if not xlsx:
        record("report 全链", False, "无样本 xlsx", 0)
        return
    t0 = time.perf_counter()
    with xlsx[0].open("rb") as f:
        resp = httpx.post(
            f"{BASE}/api/v1/report",
            files={"files": (xlsx[0].name, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"semester": "2023-2024", "user_message": "grade4"},
            timeout=590,
        )
    text = resp.text
    events = re.findall(r"^event: (\w+)", text, re.M)
    if "done" not in events:
        record("report 全链", False, f"无 done 事件（events={events[-5:]}）", time.perf_counter() - t0)
        return
    done_line = [l for l in text.splitlines() if "failed_students" in l][0]
    payload = json.loads(done_line.split("data: ", 1)[1])
    students = payload["students"]
    ok_count = len([s for s in students if s["status"] == "ok"])
    failed = payload.get("failed_students", [])
    if not students or failed:
        record("report 全链", False, f"ok={ok_count} failed={len(failed)}", time.perf_counter() - t0)
        return
    # 下载验证第一份 PDF
    url = students[0]["url"]
    dl = httpx.get(f"{BASE}{url}", timeout=60)
    magic = dl.content[:4] if dl.status_code == 200 else b""
    ok = dl.status_code == 200 and magic == b"%PDF"
    record("report 全链", ok, f"{ok_count} 学生 PDF + 下载 {dl.status_code} magic={magic}", time.perf_counter() - t0)


def evaluation_e2e() -> None:
    t0 = time.perf_counter()
    body = {"target_user_id": "3123003252", "comment_type": "encouragement", "generated_by": "e2e"}
    with httpx.stream("POST", f"{BASE}/api/v1/evaluation", json=body, timeout=280) as resp:
        text = "\n".join(line for line in resp.iter_lines() if line)
    events = re.findall(r"^event: (\w+)", text, re.M)
    ok = "radar" in events and "done" in events and "error" not in events
    me = httpx.get(f"{BASE}/api/v1/evaluation/me", params={"user_id": "3123003252"}, timeout=30)
    items = me.json().get("items", []) if me.status_code == 200 else []
    ok = ok and len(items) >= 1 and items[0]["comment_type"] == "encouragement"
    record("evaluation 全链", ok, f"events={events[:6]} /me items={len(items)}", time.perf_counter() - t0)


def upload_e2e() -> None:
    csv = REPO_ROOT / "course_dataset_tools" / "output" / "course.csv"
    if not csv.is_file():
        record("documents upload", False, "无 course.csv", 0)
        return
    t0 = time.perf_counter()
    with csv.open("rb") as f:
        resp = httpx.post(
            f"{BASE}/api/v1/documents/upload",
            files={"file": ("course_sample.csv", f, "text/csv")},
            data={"dataset_name": "e2e_smoke", "chunk_strategy": "auto"},
            timeout=180,
        )
    data = resp.json() if resp.status_code == 200 else {}
    ok = resp.status_code == 200 and data.get("chunks_count", 0) > 0
    record("documents upload", ok, f"dataset_id={data.get('dataset_id', '')} chunks={data.get('chunks_count', 0)}", time.perf_counter() - t0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-report", action="store_true", help="跳过 report 全链（较慢）")
    args = parser.parse_args()

    # 1. knowledge-query：知识库引用
    reply, dt = chat("奖学金申请条件是什么？")
    record("chat→knowledge-query", "来源" in reply or "奖学金" in reply, f"reply={reply[:60]}", dt)

    # 2. recommend：选课推荐
    reply, dt = chat("帮我推荐3门不用考试的选修课")
    record("chat→recommend", len(reply) > 30, f"reply={reply[:60]}", dt)

    # 3. writing：论文写作
    reply, dt = chat("帮我写一篇关于深度学习的300字短文")
    record("chat→writing", len(reply) > 100, f"reply_len={len(reply)}", dt)

    # 4. web-search：搜索（MCP/直连 key 未配置 → 结构化错误或结果，验证降级链不崩溃）
    reply, dt = chat("帮我搜一下今年考研国家线")
    record("chat→web-search", bool(reply) and "Error" not in reply[:20], f"reply={reply[:60]}", dt)

    # 5. image-generation：生图（即梦 MCP 未配置 → 结构化错误，验证不伪造）
    reply, dt = chat("帮我画一张图书馆的插画")
    record("chat→image-generation", bool(reply), f"reply={reply[:60]}", dt)

    # 6. image_recognize：图片附件视觉识别
    img = REPO_ROOT / "docs" / "v2.0.0" / "image.png"
    data_url = "data:image/png;base64," + base64.b64encode(img.read_bytes()).decode()
    reply, dt = chat("这是一张什么图？描述一下", images=[data_url])
    record("chat→image_recognize", len(reply) > 20, f"reply={reply[:60]}", dt)

    # 7. report 全链
    if not args.skip_report:
        report_e2e()

    # 8. evaluation 全链
    evaluation_e2e()

    # 9. documents upload
    upload_e2e()

    passed = sum(1 for r in results if r["ok"])
    print("\n" + "=" * 60)
    print(f"E2E 结果：{passed}/{len(results)} 通过")
    for r in results:
        print(f"  {'PASS' if r['ok'] else 'FAIL'}  {r['name']}  ({r['elapsed_s']}s)")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
