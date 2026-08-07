# CircuitBreaker

**状态**: `implemented`
**Phase**: 1
**类别**: `system/*`

## 功能描述

熔断器，防止级联故障。状态机：`closed` → `open`（失败次数超阈值）→ `half_open`（恢复探测）→ `closed`（成功恢复）。

## 核心方法

| 方法 | 说明 |
|------|------|
| `call(func, *args, **kwargs)` | 在熔断保护下执行函数 |
| `reset()` | 手动重置熔断器到 closed 状态 |
| `state` (property) | 当前熔断器状态：closed / open / half_open |

## 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `failure_threshold` | `3` | 连续失败次数阈值 |
| `recovery_timeout` | `30.0` | 熔断后等待恢复的秒数 |

## 使用方式

```python
from tools import CircuitBreaker

cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
result = cb.call(my_tool, arg1, arg2)
# 连续 3 次失败 → open 状态 → 拒绝调用
# 30 秒后 → half_open → 试探调用 → 成功 → closed
```

## 参考

- `docs/v2.0.0/plan.md` 决策 11/12：可靠性机制