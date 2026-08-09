# recommend_courses

**状态**: `implemented` — 内部走统一流式（默认并行 Pipeline，可选 ReAct）
**Phase**: 1
**类别**: `recommend/*`

## 功能描述

包装 v1 `SupervisorOrchestrator` 推荐链路为 deepagents 可调用的 tool。内部消费 `supervisor.stream_recommend_unified`（与 `POST /api/v1/recommend/stream` 同源），默认走并行 Pipeline（最快，`student_profile∥course_recall`、`rerank∥feasibility` 并行），`mode="react"` 可选 ReAct 编排。支持自然语言偏好描述、冷启动、硬约束过滤、语义重排、可行性分析和推荐理由生成。

## 输入参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `query` | `str` | 否 | `""` | 用户偏好描述（如"不考试的公选课"） |
| `num_items` | `int` | 否 | `10` | 推荐课程数量，范围 1-50 |
| `mode` | `str` | 否 | `pipeline` | 编排模式：pipeline（并行，快，默认）/ react（多轮决策，慢） |

## 输出

返回推荐结果 JSON 字符串（课程列表 + 推荐理由 + 选课建议）。

## 失败兜底

- 默认走并行 Pipeline（快）；`mode="react"` 走 ReAct，任一阶段失败自动切换 Pipeline，`experiment_group=pipeline_fallback`
- 工具内部消费统一流式 generator（`stream_recommend_courses`），错误事件转为异常抛出

## 参考

- `python/agent/recommend/supervisor.py` — v1 编排核心（`stream_recommend_unified`）
- `python/api/recommend.py` — 统一流式入口 `POST /api/v1/recommend/stream`
