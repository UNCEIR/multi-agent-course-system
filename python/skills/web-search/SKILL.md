---
name: web-search
description: 通过互联网搜索获取实时信息（tavily MCP 主路，熔断自动降级直连 SDK）。当用户需要实时信息、最新新闻、外部资料时使用。
allowed_tools: [web_search]
---

## Description
实时网页搜索：MCP 主路（tavily）→ 熔断降级直连 SDK → 双失败结构化错误；回答标注来源。

## Trigger
用户需要实时信息、最新新闻、外部资料时激活。触发关键词：搜索/搜一下/查查/最新/最近/今天/网上说/据报道/知识库没有的。

## Architecture（按序加载）
1. Rules（先读边界，再行动）：
   - [Load Shared Rules: grounding](../_shared/rules/grounding.md)
   - [Load Shared Rules: fallback](../_shared/rules/fallback.md)
2. Commands（执行流程）：
   - [Load Command: search-and-answer](./commands/search-and-answer.md)
3. Scripts（调用示例，按需引用）：
   - [Load Script: search-example](./scripts/search-example.md)
