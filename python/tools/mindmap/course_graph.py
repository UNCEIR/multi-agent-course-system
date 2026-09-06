# -*- coding: utf-8 -*-
"""课程图谱 JSON（Phase 4 P1-E / E2）。

不复用 MindMap DSL（语义不兼容）→ 新 nodes/edges 结构：
- nodes[]: {id(唯一), type: course|domain|prerequisite, label}
- edges[]: {source, target, relation(枚举: prerequisite|domain_of|related)}
id 唯一 + source/target 引用完整性校验。
"""

from __future__ import annotations

import json
from typing import Any


def build_course_graph(courses: list[dict]) -> dict:
    """推荐课程列表 → 课程/领域/前置关系图谱 JSON（确定性构建，不依赖 LLM）。

    Args:
        courses: 课程 dict，至少含 course_name；可选 domain / prerequisites（列表）。
    """
    nodes: list[dict] = []
    edges: list[dict] = []
    node_ids: set[str] = set()
    domain_ids: dict[str, str] = {}

    def _add_node(nid: str, ntype: str, label: str) -> None:
        if nid in node_ids:
            return
        node_ids.add(nid)
        nodes.append({"id": nid, "type": ntype, "label": label})

    def _add_edge(source: str, target: str, relation: str) -> None:
        if source in node_ids and target in node_ids:
            edges.append({"source": source, "target": target, "relation": relation})

    for course in courses:
        name = str(course.get("course_name") or course.get("name") or "").strip()
        if not name:
            continue
        cid = f"course:{name}"
        _add_node(cid, "course", name)
        domain = str(course.get("domain") or "").strip()
        if domain:
            did = f"domain:{domain}"
            _add_node(did, "domain", domain)
            domain_ids.setdefault(domain, did)
            _add_edge(cid, did, "domain_of")
        for pre in course.get("prerequisites") or []:
            pname = str(pre).strip()
            if not pname:
                continue
            pid = f"prerequisite:{pname}"
            _add_node(pid, "prerequisite", pname)
            _add_edge(cid, pid, "prerequisite")

    return {"nodes": nodes, "edges": edges, "counts": {"nodes": len(nodes), "edges": len(edges)}}


def course_graph_json(courses: list[dict]) -> str:
    """JSON 字符串形式（工具返回给 LLM/前端）。"""
    return json.dumps(build_course_graph(courses), ensure_ascii=False)
