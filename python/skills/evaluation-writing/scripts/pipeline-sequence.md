# Script: pipeline-sequence（评价生成编排序列示例）

> 编排契约示例；单工具参数以工具 docstring 为准。

## 五层调用序列
```json
[{"tool": "get_academic_snapshot", "args": {}},
 {"tool": "design_dimensions", "args": {}},
 {"tool": "compute_radar_values", "args": {}},
 {"tool": "generate_comment", "args": {"comment_type": "encouragement"}}]
```
- user_id 从上下文注入（目标学生由端点显式指定）。
- 层②/④ 失败走确定性降级（默认维度集 / 规则化评语），status=fallback。

## 数值核验口径
评语数字 ⊆ 快照派生值 ∪ 雷达值（容差 0.5），白名单由代码计算。
