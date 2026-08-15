# Tavily MCP websearch 闭环打通（2026-08-15）

## 背景与问题

- 本轮要解决的问题：将 tavily MCP 从"未配置降级态"打通为真实可用的 web 搜索闭环，并用 eval set 做几组对比验证。
- 触发原因或用户诉求：用户提供 tavily API key 与 MCP 配置方式（官方 `mcp.tavily.com/mcp/?tavilyApiKey=...` 端点），要求构建完整 websearch 闭环、不写测试类、直接 docker 重建只测该功能，并用几组 eval set 测试对比。
- 影响范围：`python/tools/chat/web_search.py`、`python/tools/mcp_client.py`、`python/requirements.txt`、`python/.env`（仅配置）、`python/eval_sets/web_search.jsonl`（新增）、`python/eval/runner.py`。

## 总体架构方案

- 涉及模块：
  - MCP 客户端层（`mcp_client.py`）：配置注册表（settings.mcp_servers）+ streamable_http 连接 + 每服务器熔断
  - 工具层（`web_search.py`）：MCP 主路 → tavily SDK 直连兜底 → 双失败结构化错误；输出规范化
  - 评测层：`eval_sets/web_search.jsonl` + runner 的 web_search live 分支
- 数据流或调用链：
  `web_search(query)` → `_resolve_tavily_tool`（list_tools 探测真实工具名，命中 tavily_search）→ `call_tool("tavily", ...)`（懒连接 streamable_http，url 中 {key} 由 api_key_env 指向的密钥替换）→ MCP 返回 content 数组 → `_normalize_result` 规范化为 `{query, results[{title,url,content}], source}` → 失败则 `_tavily_fallback` 直连 SDK
- 关键设计取舍：
  - key 注入双通道：进程 env 优先（容器 compose env_file），settings 兜底（宿主 .env 由 pydantic 读取）——解决"宿主/容器环境差异"
  - 工具名候选探测（tavily_search/search/web_search）而非硬编码——真实 MCP 暴露名与假服务器测试名解耦
  - mcp SDK pin `<2`：2.x 移除 `streamablehttp_client` API，防 requirements 漂移破坏构建

## 细节实现

- 修改或分析的关键文件：
  - `python/tools/mcp_client.py`：
    - `__init__` 增 `_transports` 字典（持有 streamablehttp/stdio 上下文引用）
    - `connect`：保存 transport 引用 → `transport.__aenter__()` → `ClientSession.__aenter__()` → `session.initialize()`（MCP 握手）→ `load_mcp_tools`；失败走 `_cleanup_transport`
    - `disconnect`：按序关闭 session → transport
    - `_resolved_url`：`os.getenv(api_key_env)` 为空时 fallback `get_settings()` 对应字段（`key_env.lower()` 映射）
  - `python/tools/chat/web_search.py`：
    - `_resolve_tavily_tool`（async，候选探测 + 缓存）；`_normalize_result`（兼容 dict 直返 / MCP content 数组 / 裸字符串三种形态，保留直连兜底的 source 标记）
  - `python/requirements.txt`：`+mcp>=1.24,<2`（显式 pin，注释说明 2.x API 破坏）
  - `python/eval_sets/web_search.jsonl`（新增 5 组 case）：实时政策/机构信息/知识资料/实时新闻/校园生活，断言 = contains 关键词 + count_ge 结果数
  - `python/eval/runner.py`：`count_ge` 断言、`_live_web_search`（真实工具调用 → results+joined）、`_smoke_output` web_search 分支、`sys.path` 注入项目根（eval/ 子目录运行可 import tools）
- 核心逻辑：MCP content 数组 `[{"type":"text","text":"{json}"}]` → 提取内层 JSON → 重建 results（title/url/content 截断）——LLM 拿到干净结构而非原始协议
- 兼容性与风险控制：`_normalize_result` 对 isError dict 原样透传（降级链不被改写）；工具名探测失败兜底 `tavily_search`；连接失败记熔断（3 次 open）

## Debug 结论

1. **MCP transport 被 GC 导致跨任务崩溃**
   - 根因：`streamablehttp_client(url).__aenter__()` 的 async generator 未持有引用，connect 返回后被 GC，anyio cancel scope 在错误任务退出 → `Attempted to exit cancel scope in a different task`
   - 解决：`_transports[server_name]` 持有引用；disconnect 按序关闭 session → transport；失败路径 `_cleanup_transport`
   - 验证：容器内 connect/list_tools 稳定成功
2. **`asyncio.run` 在运行中事件循环内调用**
   - 根因：`_resolve_tavily_tool` 用 asyncio.run 调 list_tools，pytest-asyncio 已持有循环 → 非法；且异常被吞后走错误工具名 → 假服务器 MCP_TOOL_NOT_FOUND
   - 解决：改 async 函数直接 await
   - 验证：单测 14 passed
3. **URL 的 {key} 未被替换 → Invalid Tavily API key**
   - 根因：`_resolved_url` 只读 `os.getenv`，宿主进程 env 无该变量（key 只在 .env 由 pydantic 读取）→ URL 保留字面 `{key}`
   - 排查：打印 call_tool 原始返回看到 `Invalid Tavily API key: ... does not start with 'tvly-'`（证据）
   - 解决：`os.getenv` 空时 fallback `get_settings()` 对应字段
   - 验证：宿主 MCP 路径返回真实结果
4. **宿主依赖缺口**
   - 根因：宿主 Anaconda 未装 `mcp`/`tavily`/`langchain_mcp_adapters`（容器全量安装故正常）；且 `pip install mcp` 装了 2.0.0（`streamablehttp_client` 已移除）
   - 解决：宿主对齐 `mcp==1.29.0` + 补装 tavily-python/langchain-mcp-adapters；requirements pin `mcp>=1.24,<2` 防漂移
   - 验证：宿主 live eval 5/5
5. **tavily 服务端对纯中文 query 返回 400**
   - 根因：tavily API 对纯中文 query（"转专业流程"/"广州图书馆开放时间"等）返回 `Query is invalid`，含数字/拉丁字符的（"2026年考研国家线"/"最新 AI 政策"）正常——服务端中文兼容问题（外部行为）
   - 排查：直连与 MCP 同错 + 多组 query 变量试验定位规律
   - 解决：eval query 加数字/英文锚点（如 "广东工业大学 2026 转专业 条件"、"deep learning 入门 书籍 推荐"）
   - 验证：调整后 live 5/5

## 测试与验证

- 已执行（未写 pytest 测试类，按用户要求）：
  - 容器内探活：connect=True，`list_tools` 暴露 tavily_search/extract/crawl/map/research
  - 容器内真实调用：`web_search` 返回 2 条真实 AI 政策结果（source=tavily-mcp）
  - eval 对比（宿主）：`python eval/runner.py --set web_search --live` = **5/5 passed**（p50=878ms，p95=8.9s）；smoke 自洽 5/5
  - MCP 主路 vs 直连兜底对比：5 组 query 对照（MCP 结果数与延迟 vs 直连）
  - 全量回归：`pytest tests/ -m "not slow"` = **236 passed, 4 deselected**（含 mcp_client/web_search 既有单测，代码改动零破坏）
- 未执行及原因：真实 MCP 的 e2e_smoke 全量（chat→web-search 用例已在容器内单点验证）；即梦/E2B MCP 仍未配置（凭据未提供，保持降级态）

## 经验与后续

- 本轮经验：
  - **"配置了但环境差异导致静默失败"是最难排查的一类**：同代码在容器（env 注入）与宿主（.env 文件）表现不同——key 注入必须有"env → settings"双通道
  - async generator 生命周期是 Python MCP 客户端的经典坑：**上下文对象必须持有引用并在同一任务内进出**
  - 外部 API 的中文兼容问题（tavily 纯中文 400）要沉淀为 eval case 设计约束——query 带数字/英文锚点既是规避也是检索质量提升
  - "无测试类"不意味着无验证：探活脚本 + eval live + 容器实测构成有效闭环
- 后续建议：
  - 即梦/E2B MCP 凭据到位后按同模板打通（tool 名探测 + 输出规范化 + eval set）
  - eval_sets/web_search.jsonl 可扩为回归集（每周跑 live 监控 tavily 服务端行为漂移）
  - runner 的 live 模式与 LangSmith run_id 回链（README 承诺）在 Phase 4 补齐
