# Script: search-example（搜索调用示例）

> 调用契约示例；参数细节以工具 docstring 为准。

## 单次调用
```json
{"query": "2026年考研国家线", "max_results": 5}
```

## 链路与降级
`web_search` → MCP `search/*`（tavily）→ 熔断 → tavily SDK 直连 → 双失败 → `{isError, code, message}`

## 结果整合模板
- 要点摘要（1-3 句）
- 来源：`[标题](URL)`
- 不确定信息标注"以官方发布为准"
