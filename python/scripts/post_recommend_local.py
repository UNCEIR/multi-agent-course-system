"""
对本地已启动的 FastAPI 发一次推荐请求（等价于 curl 冒烟）。

用法（在 python/ 目录下）:
  pip install -r requirements.txt  # 若尚未安装 httpx
  # 先配置仓库根目录或 python/.env 中的 ECOM_LLM_*，再启动: uvicorn main:app --host 0.0.0.0 --port 8000
  python scripts/post_recommend_local.py

环境变量:
  RECOMMEND_URL      默认 http://127.0.0.1:8000/api/v1/recommend
  HEALTH_URL         默认 http://127.0.0.1:8000/health （用于核对实际 LLM host）

纯 curl（PowerShell，在 python/ 目录）示例：
  curl.exe -sS -X POST "http://127.0.0.1:8000/api/v1/recommend" -H "Content-Type: application/json" --data-binary "@scripts/curl_recommend_payload.json"
"""

from __future__ import annotations

import json
import os
import sys

import httpx


def _print_llm_diagnostics(client: httpx.Client, health_url: str) -> None:
    try:
        hr = client.get(health_url)
        if not hr.is_success:
            print(f"[诊断] GET {health_url} HTTP {hr.status_code}", file=sys.stderr)
            return
        data = hr.json()
        llm = data.get("llm") or {}
        emb = data.get("embedding_provider")
        print(
            "[诊断] /health 解析到的 LLM: "
            f"host={llm.get('base_url_host')} model={llm.get('model')} "
            f"dashscope_like={llm.get('looks_like_dashscope')} embedding={emb}",
            file=sys.stderr,
        )
        if llm and not llm.get("looks_like_dashscope"):
            print(
                "[诊断] base_url_host 不是灵积域名时，阿里云 DashScope 控制台不会产生 token 记录；"
                "请检查 ECOM_LLM_BASE_URL（或 .env 是否在仓库根 / python/ 被加载）。",
                file=sys.stderr,
            )
    except Exception as e:
        print(f"[诊断] 读取 /health 失败: {e}", file=sys.stderr)


def main() -> int:
    base = os.environ.get("RECOMMEND_BASE", "http://127.0.0.1:8000").strip().rstrip("/")
    url = os.environ.get(
        "RECOMMEND_URL", f"{base}/api/v1/recommend"
    ).strip()
    health_url = os.environ.get("HEALTH_URL", f"{base}/health").strip()
    body = {
        "user_id": "smoke_user",
        "scene": "course_selection",
        "num_items": 2,
        "prompt": "想选作业少的人文艺术类公选课",
        "context": {},
    }
    try:
        with httpx.Client(timeout=120.0) as client:
            _print_llm_diagnostics(client, health_url)
            r = client.post(url, json=body)
    except httpx.ConnectError as e:
        print(f"连接失败 ({url})，请先启动服务: {e}", file=sys.stderr)
        return 2
    print(f"HTTP {r.status_code}")
    try:
        payload = r.json()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        ar = payload.get("agent_results") or {}
        rerank = ar.get("course_rerank") or {}
        prof = ar.get("student_profile") or {}
        crs = payload.get("courses") or []
        strat = rerank.get("rerank_strategy") if isinstance(rerank, dict) else None
        print(
            f"[诊断] courses={len(crs)} student_profile.success={prof.get('success')} "
            f"course_rerank.rerank_strategy={strat}",
            file=sys.stderr,
        )
        if isinstance(rerank, dict) and strat == "rule_based_course_rerank":
            print(
                "[诊断] 重排走了规则分支（无画像或画像缺失），未调用重排 LLM；"
                "画像与理由 Agent 仍可能产生 token。",
                file=sys.stderr,
            )
        if len(crs) == 0:
            print(
                "[诊断] 最终课程为空时，推荐理由 Agent 会跳过 LLM，可能几乎无 token。",
                file=sys.stderr,
            )
    except Exception:
        print(r.text)
    return 0 if r.is_success else 1


if __name__ == "__main__":
    raise SystemExit(main())
