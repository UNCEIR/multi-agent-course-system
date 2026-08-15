# Script: pipeline-sequence（一键推荐编排序列示例）

> 本文件是**编排契约示例**（多步骤调用序列），单工具参数细节以工具 docstring 为准，不在此重复。

## 一键路径（推荐）
```json
{"query": "<学生选课需求原话>", "num_items": 6, "mode": "pipeline"}
```
一次调用完成 7 阶段（画像∥召回 / 重排∥可行性并行）。

## 原子路径（精细控制）完整序列
```json
[{"tool": "extract_profile", "args": {"query": "..."}},
 {"tool": "search_courses", "args": {"strategy": "wide"}},
 {"tool": "search_courses", "args": {"strategy": "refined"}},
 {"tool": "filter_hard_constraints", "args": {}},
 {"tool": "semantic_filter_courses", "args": {}},
 {"tool": "rerank_courses", "args": {}},
 {"tool": "check_feasibility", "args": {}},
 {"tool": "generate_reasons", "args": {}}]
```

## 失败处理
- 一键工具失败 → 告知用户稍后重试；候选不足 → 建议放宽约束。
