# Script: two-phase-example（两段式调用契约示例）

> 编排契约示例；参数细节以工具 docstring 为准。

## 阶段一：提交
```json
{"prompt": "夕阳下的大学图书馆，插画风格，温暖色调，请生成 1-3 张内容关联的组图", "ratio": "16:9", "scale": 0.7, "force_single": false}
```
→ 返回 `{"task_id": "739...", "status": "in_queue", "hint": "..."}`

## 阶段二：轮询（按 next_poll_after_seconds 间隔，指数退避 3→6→10s 封顶）
```json
{"task_id": "739...", "attempt": 1}
```
→ `generating` 时返回 `{"status": "generating", "next_poll_after_seconds": 3, "attempts_left": 9}`
→ `done` 时返回 `{"status": "done", "image_urls": ["/api/v1/report/download?file_key=images/xxx.png..."]}`

## 链路与降级
`image_generate` → MCP `image/*`（自建 stdio server）→ 火山引擎提交/查询
失败链：任务超时（120s）→ 保留 task_id 可续查；审核码 50411/12/13 → 提示改 prompt（不可重试）；限流 50429/30 → 退避重试；转存失败 → 返回 24h 外部 URL 并标注时效
