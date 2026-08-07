# ToolRegistry

**状态**: `implemented`
**Phase**: 1（MCP 懒加载待 Phase 3）
**类别**: `system/*`

## 功能描述

工具注册中心，统一管理所有 tool 的注册、发现和权限控制（allowlist 门控）。支持 MCP 动态发现接入外部工具。

## 核心方法

| 方法 | 说明 |
|------|------|
| `register(tool)` | 注册单个 tool |
| `register_many(tools)` | 批量注册多个 tool |
| `get(name)` | 按名称获取已注册的 tool |
| `get_all(allowed=None)` | 返回所有 tool，按 allowlist 过滤 |
| `list_tools()` | 列出所有 tool 元数据 |
| `is_allowed(name)` | 检查 tool 是否在 allowlist 中 |

## 使用方式

```python
from tools import ToolRegistry, get_registry

registry = ToolRegistry()
registry.register_many([tool1, tool2])
all_tools = registry.get_all()
filtered = registry.get_all(allowed=["tool1"])
```

## 参考

- `python/tools/__init__.py` — 工具包导出
- `python/agent/runtime.py` — 启动时注册所有内置 tool