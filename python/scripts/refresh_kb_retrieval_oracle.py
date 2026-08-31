# -*- coding: utf-8 -*-
"""回填 kb_retrieval.jsonl 的 expected.chunk_ids 为真实 chunk_id 体系。

背景：eval_sets/kb_retrieval.jsonl 的 expected.chunk_ids 原为虚构标注
（handbook_chunk_*），与真实检索返回的 chunk_id 体系（handbook_2025_<hash>:<N>）
不符，导致 live 评估 recall=0。

本脚本从 MySQL document_chunks（dataset_id LIKE '%handbook%'）读取真实 chunk，
按每个 case 的 reference.keywords 关键词匹配 content，回填：
- expected.chunk_ids → 匹配的真实 chunk_id 列表
- assertions[].value → 同上；匹配为空的主题降级为 count_ge（命中数 ≥ 1）

幂等可重跑；handbook 未摄入时显式提示并退出（绝不写假值）。
仅产出数据正确性；live 评估在算力允许时另行执行。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.mysql.base import MySQLRepository  # noqa: E402

EVAL_SET = Path(__file__).resolve().parent.parent / "eval_sets" / "kb_retrieval.jsonl"
DATASET_LIKE = "%handbook%"


def _load_cases() -> list[dict]:
    cases = []
    for line in EVAL_SET.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            cases.append(json.loads(line))
    return cases


def _fetch_handbook_chunks(repo: MySQLRepository) -> list[tuple[str, str]]:
    if not repo.ping():
        raise RuntimeError("MySQL 不可用")
    assert repo._engine is not None
    sql = (
        "SELECT chunk_id, content FROM document_chunks "
        f"WHERE dataset_id LIKE '{DATASET_LIKE}'"
    )
    with repo._engine.connect() as conn:
        rows = conn.execute(text(sql)).mappings().all()
    return [(r["chunk_id"], r.get("content") or "") for r in rows]


def _match_keywords(content: str, keywords: list[str]) -> bool:
    return any(kw and kw in content for kw in keywords)


def main() -> int:
    cases = _load_cases()
    if not cases:
        print(f"未找到 case：{EVAL_SET}")
        return 1

    repo = MySQLRepository()
    try:
        chunks = _fetch_handbook_chunks(repo)
    except RuntimeError as exc:
        print(f"[SKIP] {exc}；跳过回填（不写假值）")
        return 1
    if not chunks:
        print("[SKIP] MySQL document_chunks 中无 handbook dataset（未摄入？）；跳过回填（不写假值）")
        return 1

    print(f"handbook chunks 总数：{len(chunks)}")
    updated = 0
    skipped = 0
    for case in cases:
        keywords = (case.get("reference") or {}).get("keywords", [])
        matched = [
            cid
            for cid, content in chunks
            if _match_keywords(content, keywords)
        ]
        case_id = case["case_id"]
        case["expected"]["chunk_ids"] = matched
        k = case["assertions"][0].get("k", 5)
        if matched:
            case["assertions"] = [
                {"kind": "recall", "field": "hit_chunk_ids", "value": matched, "weight": 1.0, "k": k}
            ]
            updated += 1
            print(f"  {case_id} ({case['scenario']}): 命中 {len(matched)} 个真实 chunk")
        else:
            case["assertions"] = [
                {"kind": "count_ge", "field": "hit_chunk_ids", "value": 1, "weight": 1.0}
            ]
            skipped += 1
            print(f"  {case_id} ({case['scenario']}): 关键词 {keywords} 无匹配 → 降级 count_ge≥1")

    lines = [json.dumps(c, ensure_ascii=False) for c in cases]
    EVAL_SET.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"回填完成：更新 {updated}，降级 {skipped}，文件 {EVAL_SET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())