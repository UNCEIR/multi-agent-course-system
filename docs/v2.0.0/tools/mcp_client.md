# MultiServerMCPClient

**状态**: `stub` — `NotImplementedError`（`disconnect` 已实装用于测试）
**Phase**: 3
**类别**: `system/*`

## 功能描述

多服务器 MCP 客户端管理，对接外部 TS 服务（FastGPT mcp_server 等），支持 tools/list 动态发现。通过 `langchain-mcp-adapters` 实现。

## 核心方法

| 方法 | 说明 |
|------|------|
| `connect(server_name, url)` | 连接到 MCP 服务器（Phase 3 实装） |
| `disconnect(server_name)` | 断开 MCP 服务器连接（已实装） |
| `list_tools(server_name)` | 列出服务器的可用工具（Phase 3 实装） |
| `call_tool(server_name, tool_name, args)` | 调用 MCP 服务器上的工具（Phase 3 实装） |

## 使用方式

```python
from tools import MultiServerMCPClient, get_mcp_client

client = get_mcp_client()
# Phase 3: await client.connect("fastgpt", "http://localhost:3003/{key}/sse")
# tools = await client.list_tools("fastgpt")
# result = await client.call_tool("fastgpt", "tool_name", {"arg": "value"})
```

## 参考

- `python/config/settings.py` — `fastgpt_mcp_url` / `fastgpt_mcp_key` 配置
- `E:\Agent\FastGPT` — FastGPT mcp_server 源码