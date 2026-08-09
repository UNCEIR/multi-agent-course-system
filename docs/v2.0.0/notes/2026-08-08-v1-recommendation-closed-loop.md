# v1 推荐业务闭环验证

## 验证范围

- 仅验证 `python/agent/recommend/` v1 推荐业务及其 API、MySQL、Redis、Milvus 依赖。
- 不纳入 v2 deepagent 业务、FastGPT 或 MCP。

## 验证结果

- v1 推荐相关单元测试：`44 passed`。
- 默认非 slow 测试：`95 passed, 4 deselected`。
- Compose 依赖启动成功：MySQL、Redis、Milvus、etcd、MinIO。
- `GET /health`：HTTP 200，MySQL/Redis/Milvus 均为 `true`。
- MySQL 数据量：`course_records=150`、`course_chunks=600`。
- Pipeline 分桶请求：HTTP 200，返回 2 门课程、2 条推荐理由和 5 条风险/选择提示；Agent 结果包含画像、召回、重排、可行性、推荐理由五阶段。
- ReAct 分桶请求：HTTP 200，完成 11 轮工具调用并返回 2 门课程。
- SSE 请求 `/api/v1/recommend/stream`：HTTP 200，收到阶段事件、文本事件、课程事件和 `done` 事件。

## 修复的问题

- `python/requirements.txt` 删除当前 PyPI 不存在的 `langgraph-checkpoint-redis>=2.0.0`，避免 Docker 镜像无法构建；RedisSaver 属于后续阶段。
- `agent/main/backend.py` 与 `checkpointer.py` 改为以 Python 包根目录为路径基准，修复容器内 `/python/...` 不存在导致 API 无法启动的问题。
- ReAct LLM 调用失败时，`SupervisorOrchestrator.recommend()` 自动降级到 Pipeline，并记录 `react_fallback`，避免推荐 API 直接返回 500。

## 当前结论

- v1 推荐业务已形成可运行闭环：请求 → 画像/召回 → 硬约束过滤 → 重排/可行性 → 理由 → HTTP/SSE 响应。
- 仍需关注外部 LLM 服务偶发 `RemoteProtocolError`；现有 Pipeline Agent 有 fallback，ReAct 已增加 Pipeline 降级。
- Milvus 使用的 ORM API 当前有 PyMilvus deprecation warning，但不阻塞本次闭环。
