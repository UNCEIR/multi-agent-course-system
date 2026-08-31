# BFF 预留层（Backend-for-Frontend）

> 决策 22（`docs/v2.0.0/plan.md`）：本目录为未来 Java 数据服务（REST/OpenAPI）预留的
> Route Handlers 代理层。**当前故意为空**，请勿添加真实代理逻辑。

## 为什么预留

- 后续部分数据 CRUD 将转 Java 数据服务（决策 21），前端将面对 **Python（SSE 流式）+ Java（REST CRUD）** 双后端。
- BFF 让前端**永远只请求自己的 `/api`**，由 Next.js Route Handlers 在服务端转发到
  Python 或 Java——前端对"后端是谁"无感，Java 接入/地址变动/鉴权聚合都不改前端。

## 分线策略（未来启用时）

- **Python SSE 流式**：保持前端直连（经 `next.config.ts` rewrites 代理到 8000），流式长连接不走 BFF。
- **Java REST CRUD**：走本目录 Route Handlers（`app/api/.../route.ts`），Node 侧转发到 Java 服务。
- 管理平台（独立项目，同 React 栈）可复用同一套 API 契约。
