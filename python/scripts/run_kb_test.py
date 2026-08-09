# -*- coding: utf-8 -*-
"""执行知识库检验 JSON：逐 case 调 /api/v1/chat，核对回答。

用法: python scripts/run_kb_test.py scripts/kb_test_transcript.json
"""

import json
import sys
import time
from pathlib import Path

import httpx

BASE = "http://localhost:8000"


def run_case(client, payload: dict, case: dict) -> dict:
    body = {
        "message": case["question"],
        "session_id": payload["session_id"],
        "user_id": payload["user_id"],
    }
    t0 = time.perf_counter()
    r = client.post(f"{BASE}/api/v1/chat", json=body, timeout=280)
    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    if r.status_code != 200:
        return {"id": case["id"], "status": "HTTP_ERROR", "code": r.status_code, "elapsed_ms": elapsed}
    reply = r.json().get("reply", "")

    checks = {}
    # expected_keywords：任一命中即视为满足（agent 措辞灵活，OR 语义）
    kws = case.get("expected_keywords", [])
    if kws:
        checks["keywords_hit"] = any(kw in reply for kw in kws)
        checks["matched"] = [kw for kw in kws if kw in reply]
    # expected_redact：必须都不出现
    reds = case.get("expected_redact", [])
    for red in reds:
        checks[f"redact:{red}"] = red not in reply
    all_pass = all(checks.values()) if checks else None

    return {
        "id": case["id"],
        "question": case["question"],
        "elapsed_ms": elapsed,
        "checks": checks,
        "all_pass": all_pass,
        "reply_head": reply[:160],
    }


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "scripts/kb_test_transcript.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    print(f"== {path.name} | user={payload['user_id']} | session={payload['session_id']}")
    with httpx.Client() as client:
        results = [run_case(client, payload, c) for c in payload["cases"]]
    passed = sum(1 for r in results if r.get("all_pass") is True)
    for r in results:
        flag = "PASS" if r.get("all_pass") is True else ("FAIL" if r.get("all_pass") is False else "??")
        reply_esc = (r.get("reply_head", "") or "").encode("unicode_escape").decode()
        print(f"[{flag}] {r['id']} ({r.get('elapsed_ms')}ms) checks={r.get('checks')}")
        print(f"        reply: {reply_esc}")
    print(f"== {passed}/{len(results)} cases passed")


if __name__ == "__main__":
    main()
