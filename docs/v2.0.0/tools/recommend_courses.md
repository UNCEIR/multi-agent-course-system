# recommend_courses

**状态**: `stub` — `NotImplementedError`
**Phase**: 1（Step 3 实装完整功能）
**类别**: `recommend/*`

## 功能描述

包装 v1 `SupervisorOrchestrator` 推荐链路为 deepagents 可调用的 tool。支持自然语言偏好描述、冷启动、硬约束过滤、语义重排、可行性分析和推荐理由生成。

## 输入参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `user_id` | `str` | 否 | `""` | 用户 ID（可选，有则提供个性化推荐） |
| `query` | `str` | 否 | `""` | 用户偏好描述（如"不考试的公选课"） |
| `num_items` | `int` | 否 | `10` | 推荐课程数量，范围 1-50 |

## 输出

返回推荐结果 JSON 字符串（课程列表 + 推荐理由 + 选课建议）。

## 失败兜底

- tool 失败时提示用户稍后重试，不返回空推荐
- 接入 v1 `SupervisorOrchestrator` 后继承其重试/兜底机制

## 参考

- `python/agent/recommend/supervisor.py` — v1 编排核心
- `python/agent/recommend/react_tools.py` — v1 7 个 ReAct 工具定义