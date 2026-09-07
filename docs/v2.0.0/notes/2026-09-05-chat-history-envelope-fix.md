# 2026-09-05 chat 历史消息无法回显（ApiEnvelopeMiddleware 残留 Content-Length → 200 空 body）

> 一句话：数据库里 session/message 关联与落库都正常（`chat_messages.session_id` 有列+索引+唯一键），
> 前端"切到往期 session 看不到消息"的根因在**响应封装层**——`ApiEnvelopeMiddleware` 给 JSON 包信封时
> 拷贝了内层响应的旧 `Content-Length`，新信封 body 长度不同 → h11 发送层报
> `LocalProtocolError: Too much data for declared Content-Length` → 客户端拿到 **200 但空 body**。

## 1. 排查方法
- **docker logs python-api**：每次 `GET /api/v1/chat/sessions/...` 前后都出现
  `h11._util.LocalProtocolError: Too much data for declared Content-Length`（starlette `_send` 抛）。
- **http.client 抓原始响应**：`GET /api/v1/chat/sessions?user_id=...` 返回 `Content-Length: 831`，
  但 `read()` 抛 `IncompleteRead(0 bytes read, 831 more expected)` —— 头声明长度与实际 body 不符。
- **DB 实证**：`SHOW COLUMNS` 确认 `chat_messages.session_id` 存在且带索引；JOIN 演示每条消息都能定位回会话
  （id=32 → session_1787585032168, seq=22）；数据落库正常 → 排除"表没关联/没落库"。

## 2. 问题根源
- `ApiEnvelopeMiddleware`（`python/api/envelope.py`）包信封时：
  `JSONResponse(content=enveloped, headers=dict(response.headers))` —— `response.headers` 含内层响应的
  旧 `Content-Length`，但 `enveloped`（信封体）长度不同 → 响应头长度与实际发送 body 不匹配。
- 该 bug 影响**所有非流式 `/api/v1` JSON 端点**（会话列表/messages、报告批次、文档列表等）：
  前端 `res.json()` 解析空 body 抛错 → 被 `catch {}` 静默吞掉 → 页面空白无消息。

## 3. 解决思想
- 信封包装本质是"换了 body"，长度/传输头必须交给新 `JSONResponse` 按实际内容重算，不能继承旧的。
- 对 `content-length` / `transfer-encoding` 做白名单剔除；`JSONResponse` 构造时会基于新 body 自动设置。

## 4. 实际编码
- `python/api/envelope.py`：新增 `_strip_body_length_headers()`（剔除 `content-length`/`transfer-encoding`），
  envelope 的两个 `JSONResponse` 返回分支（`is_base_result` 与包装成功分支）都改用它。
- `python/tests/test_api_envelope.py`：追加回归 `test_enveloped_json_content_length_matches_body`
  （断言 `Content-Length == len(resp.content)`；修复前会 IncompleteRead 直接失败）。

## 5. 测试结果
- 轻量 ASGI 验证（不 import agent.app）：信封 body 4017 字节 = 声明 Content-Length 4017，可正常 `json()`。
- 容器实测（重建 python-api 后）：
  - `GET /api/v1/chat/sessions?user_id=3123003252` → 200，CL 887 = 实际 887；
  - `GET /api/v1/chat/sessions/session_1787585032168/messages` → 200，CL 8720 = 实际 8720（含 24 条历史消息）。
- 前端切换 session 后历史消息可正常回显；回归测试留待容器/CI 跑（本机 import agent.app 慢）。

## 附：seq 与 session 的关系（FAQ）
- `chat_messages.id` = 全局自增（跨会话交错分配）；`seq` = **per-session** 从 1 开始的消息序号
  （由 `chat_sessions.message_count + 1` 事务分配，`uq(session_id, seq)` 保证会话内唯一）。
- 所以单个会话 seq=24 正常（该会话有 24 条消息），与会话表总行数 15 无关；定位消息 → 读它自己的
  `session_id` 列或 `JOIN chat_sessions ON session_id`。
