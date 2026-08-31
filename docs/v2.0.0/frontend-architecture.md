# Frontend Architecture — Next.js 16 App Router（2026-08-18）

> 路 7 抽取 CourseFields 共用子组件时整理的架构文档。配套 README §目录结构。

## 1. 技术栈

| 层 | 选型 | 版本 | 备注 |
|---|---|---|---|
| 框架 | Next.js | 16.3.1 | App Router + Turbopack（dev 1.5s ready / build 2.6s） |
| UI | React | 19.2.8 | RSC + Client Components 混合 |
| 组件库 | antd | 6.6.0 | `<App>` context 提供 message/notification/modal 实例 |
| 图标 | @ant-design/icons | 6.3.2 | 装饰图标统一 `aria-hidden="true"` |
| 图表 | echarts | 6.1.0 | 评价雷达图（components/RadarChart.tsx） |
| 样式 | Tailwind CSS | 4.x | postcss 集成 |
| 状态 | zustand | 5.0.15 | `stores/auth.ts` localStorage 持久化登录态 |
| 类型 | zod | 3.23.8 | 路 3 引入，SSE 事件运行时校验（src/types/sse.ts） |
| 测试 | vitest + RTL | 2.1.9 / 16.1.0 | jsdom + @vitejs/plugin-react |
| 格式化 | prettier | 3.3.3 | 无分号 / 单引号 / 100 列宽 |

## 2. 目录结构与职责

```
frontend/
├── src/
│   ├── app/                              ← Next.js App Router 入口
│   │   ├── layout.tsx                    ← Root Layout（每个页面必经）
│   │   │                                  - 加载 Geist Sans/Mono 字体
│   │   │                                  - <html lang="zh-CN"> + globals.css
│   │   ├── globals.css                   ← 全局样式 + Tailwind 指令
│   │   ├── favicon.ico
│   │   │
│   │   ├── login/
│   │   │   └── page.tsx                  ← /login 路由
│   │   │                                  - 独立 layout（不走 MainLayout）
│   │   │                                  - ConfigProvider + zhCN locale
│   │   │
│   │   ├── (main)/                       ← Route Group（括号不影响 URL）
│   │   │   ├── layout.tsx                ← Main Layout
│   │   │   │                              - 15s 健康轮询 → API status
│   │   │   │                              - Header 导航 (MENU_ITEMS) + API 状态徽标
│   │   │   │                              - <App> context（antd 5+ 推荐）+ ConfigProvider
│   │   │   ├── page.tsx                  ← / 路由（Hub 首页）
│   │   │   │                              - 角色感知卡片（学生/老师）
│   │   │   ├── error.tsx                 ← 路由级 ErrorBoundary
│   │   │   │                              - antd Result + reset() + console.error 上报
│   │   │   │
│   │   │   ├── chat/page.tsx             ← /chat
│   │   │   ├── documents/page.tsx        ← /documents
│   │   │   ├── evaluation/page.tsx       ← /evaluation
│   │   │   ├── experiments/page.tsx      ← /experiments
│   │   │   ├── monitor/page.tsx          ← /monitor
│   │   │   ├── recommend/page.tsx        ← /recommend
│   │   │   └── report/page.tsx           ← /report
│   │   │
│   │   └── api/                          ← BFF（Next.js Route Handlers）
│   │                                      当前空（前端直接调 python-api）
│   │
│   ├── components/                       ← 共享 React 组件
│   │   ├── StreamView.tsx                ← 流式推荐输出（chat → main_agent → recommend_courses）
│   │   │                                  - rAF 节流 flush（O(N) → O(1) per token）
│   │   │                                  - 取消按钮 + aria-live + Last-Event-ID 续传
│   │   ├── CourseInlineCard.tsx          ← 流式课程卡（精简 div 容器）
│   │   │                                  - 流式输出专用（每 token 重渲染 → 不用 antd Card）
│   │   │                                  - 用 CourseFields variant="inline"
│   │   ├── CourseFields.tsx              ← 路 7 抽取：共享字段渲染层
│   │   │                                  - variant: 'inline' | 'card'
│   │   │                                  - 不含独有字段（序号 / 评分 Tooltip / match_reasons）
│   │   │                                  - 不含外层 a11y（role/aria-label 由父组件决定）
│   │   ├── RadarChart.tsx                ← 评价雷达图（echarts wrapper）
│   │   │
│   │   └── recommend/                    ← 路 1 拆出的推荐子组件
│   │       ├── StatCard.tsx              ← 总耗时/课程数/Agent 数/选课提醒
│   │       ├── PipelineTimeline.tsx      ← 三阶段 Agent 流水线可视化
│   │       ├── CourseCard.tsx            ← 静态课程卡（hoverable + match_reasons）
│   │       │                              - 用 CourseFields variant="card"
│   │       ├── SingleResultView.tsx      ← 经典模式结果视图
│   │       ├── CompareView.tsx           ← 多查询对比表格
│   │       └── constants.tsx             ← PRESET_QUERIES / PHASE_MAP / DIFFICULTY_COLORS
│   │
│   ├── lib/                              ← 业务库（无 React 依赖）
│   │   ├── api.ts                        ← API 客户端（recommendStream / chatStream / ...）
│   │   │                                  + 4 个 *WithRetry 方法（路 2 SSE 续传）
│   │   ├── sse.ts                        ← consumeSSE / consumeSSEWithRetry（路 2）
│   │   │                                  - 解析 event/data/id 三行
│   │   │                                  - 指数退避（500ms → 1s → 2s）+ Last-Event-ID
│   │   ├── theme.ts                      ← antd 主题 token
│   │   └── api/                          ← 路 3 错误反馈层
│   │       ├── safeCall.ts               ← ApiError 归一化 + parseHttpError
│   │       ├── useNotify.ts              ← toast + inline 两路反馈 hook
│   │       └── useApi.ts                 ← 基于 safeCall 的统一 hook
│   │
│   ├── stores/                           ← Zustand state
│   │   ├── auth.ts                       ← 登录态（localStorage 持久化）
│   │   ├── session.ts                    ← 会话列表（按 user_id 隔离）
│   │   └── index.ts                      ← 推荐 / 实验 store
│   │
│   ├── types/                            ← 全局类型
│   │   ├── index.ts                      ← 主类型（Course / API 响应 / 文档类型 / 认证）
│   │   │                                  - 12 个文件引用，v2 核心类型源
│   │   │                                  - **不是遗留文件**——保留不动
│   │   └── sse.ts                        ← 路 3 zod schema（SSE 事件严格类型）
│   │
│   └── styles + tests/                   ← 测试代码（vitest + RTL）
├── next.config.ts                        ← rewrites 代理 /api、/health → :8000
│                                            - 默认 API_PROXY_TARGET=http://127.0.0.1:8000
│                                            - 容器内可用 API_PROXY_TARGET=http://python-api:8000
├── Dockerfile                            ← 路 5：node:20-slim 镜像（dev 模式启动）
├── .dockerignore
├── eslint.config.mjs                     ← ESLint 9 + eslint-config-next + eslint-config-prettier
├── prettier.config                       ← 无分号 / 单引号 / 100 列宽
├── vitest.config.mts                     ← jsdom + tsconfigPaths + react plugin
├── tsconfig.json                         ← @/* 别名指向 ./src/*
├── package.json                          ← engines: ^20.9.0 || >=22.0.0
└── AGENTS.md                             ← 项目方维护的 Next.js 16 警告
```

## 3. 页面挂载链路（Next.js 16 App Router）

```
URL: /
  RootLayout (app/layout.tsx)             ← <html><body> + 字体 + globals.css
    └─ MainLayout (app/(main)/layout.tsx)  ← <App> + ConfigProvider + Header 导航
        └─ HubPage (app/(main)/page.tsx)    ← 角色感知卡片入口

URL: /chat
  RootLayout
    └─ MainLayout
        └─ ChatPage (app/(main)/chat/page.tsx)

URL: /recommend
  RootLayout
    └─ MainLayout
        └─ RecommendPage (app/(main)/recommend/page.tsx)
            ├─ <SingleResultView />  (variant: 经典模式 / 单次结果)
            ├─ <CompareView />       (variant: 多查询对比)
            └─ <StreamView />        (variant: 流式对话, 内部用 <CourseInlineCard />)

URL: /login
  RootLayout                                ← 注意：login 不走 MainLayout
    └─ LoginPage (app/login/page.tsx)        ← 独立 ConfigProvider
```

### 关键设计点

- **`(main)` 是 Route Group**：括号只是分组用，**不影响 URL**。`/chat` 不是 `/(main)/chat`
- **`login` 在 `(main)/` 外**：所以登录页**无 Header / 无 App context / 无健康轮询**——独立的 ConfigProvider 自管理
- **`(main)/layout.tsx` 是 client**（`'use client'`）含 `usePathname + useRouter + 健康轮询`，但 `children` 由 RSC 流式渲染
- **`error.tsx` 是 Next.js 约定**：路由组件抛错时被该层捕获（(main) 路由级）

## 4. 客户端/服务端组件边界

| 组件 | 类型 | 原因 |
|---|---|---|
| `app/layout.tsx` | Server | 只渲染 `<html><body>` 静态框架 |
| `app/(main)/layout.tsx` | Client | 用 `usePathname` + 健康轮询 |
| `app/(main)/error.tsx` | Client | antd `<Result>` 客户端组件 |
| 所有 `page.tsx` | Client | 都用 `useState` / `useEffect` / SSE 消费 |
| `components/StreamView.tsx` | Client | SSE 消费 + `useRef` rAF |
| `components/CourseInlineCard.tsx` | Client | 接受 SSE 实时数据 |
| `components/CourseFields.tsx` | Client | antd `<Tag>` `<Tooltip>` |
| `components/RadarChart.tsx` | Client | echarts 实例化 |
| `lib/api.ts` | 共享 | 纯函数 + 类型 |
| `stores/*.ts` | 共享 | Zustand 状态 |

**RSC 红利**：`app/layout.tsx` 是 Server Component（无 `'use client'`），减少客户端 bundle 体积。

## 5. 构建流程（`npm run build` → Next.js 16 Turbopack）

```
1. 入口扫描     Next.js 扫描 src/app/，每个 page.tsx 自动注册一个路由
2. Layout 嵌套   每个 layout.tsx 包裹同目录及子目录的所有 page.tsx（除 Route Group）
3. 客户端边界   'use client' 文件 → 客户端 bundle；其余 → Server Component
4. 静态生成     所有 page 无动态数据 → 全部 (Static) 预渲染（10 个路由）
5. 运行时       浏览器 → Next.js Router → RootLayout → 嵌套 layout → 渲染 page
```

**当前构建结果**：2.6s 编译 + 38s 类型检查 + 1.4s 静态生成 + 10 路由 all static。

## 6. 状态管理（Zustand）

| Store | 持久化 | 内容 |
|---|---|---|
| `useAuthStore` | localStorage `campus_auth_v1` | `user: AuthUser / token: string` |
| `useSessionStore` | localStorage（按 user_id 隔离） | `sessions / activeSessionId` |
| `useRecommendStore / useActiveJobStore / useInputStore` | 否 | 推荐任务 / 输入文本 / 选课数 |

**Server Components 不可用**：Zustand 是纯客户端 store，必须在 `'use client'` 组件里用。

## 7. SSE 消费链路（路 2）

```
后端 SSE 端点（python-api）
  ├─ /api/v1/chat/stream          ChatEventSchema (text/tool/done/error)
  ├─ /api/v1/recommend/stream     RecommendEventSchema (phase/text/course_start/...)
  ├─ /api/v1/evaluation           EvaluationEventSchema (stage/radar/comment_token/...)
  └─ /api/v1/report                ReportEventSchema (student_done/progress/done/...)

每条 SSE 帧格式：id: N\nevent: <name>\ndata: {...}\n\n
                  ↑                       ↑
                  Last-Event-ID    zod schema 校验（路 3）

前端消费
  src/lib/sse.ts
    ├─ consumeSSE()              解析 event/data/id 三行
    └─ consumeSSEWithRetry()      + 指数退避 (500ms→1s→2s, max 3)
                                   + Last-Event-ID header 透传

  src/lib/api.ts
    ├─ recommendStream() / chatStream() / evaluation() / reportUpload()
    └─ *WithRetry()              同上但带 retry 封装

  src/components/StreamView.tsx
    ├─ rAF 节流 flush（O(N) → O(1) per token）
    ├─ 取消按钮（AbortController UI 暴露）
    ├─ aria-live="polite" + role="status"
    └─ last_event_id 缓存供重连（未实装——靠后端 deepagents thread_id 自然恢复）
```

## 8. 错误反馈层（路 3）

```
3 套散落反馈（重构前）
  ├─ message.error/warning/success   (antd static API → 警告)
  ├─ <Text type="danger">             (inline 错误)
  └─ <div> 红 panel                  (StreamView 自定义)

3 套统一收敛（重构后）
  useNotify (hook)
    ├─ toast.{success, error, info, warning}   via App context
    └─ inline.{error, set, clear, message}     本地 state

  useApi (hook) = useNotify + safeCall + loading + clearError
    ├─ call()       自动捕获 + 上报 inline
    ├─ loading      boolean
    ├─ clearError() 手动清除
    └─ toast/inline 暴露 useNotify 快捷方式

  ErrorBoundary
    └─ app/(main)/error.tsx (路由级)
```

## 9. 测试基建（路 0 / 路 7）

```
vitest.config.mts
  - jsdom 环境（antd 兼容）
  - tsconfigPaths (@/* 别名)
  - react plugin
  - include: tests/**/*.{test,spec}.{ts,tsx}
  - exclude: node_modules / .next / dist

tests/setup.ts (路 0 引入，路 7 沿用)
  - @testing-library/dom (jest-dom matcher)
  - cleanup afterEach
  - ResizeObserver polyfill (antd Card/Tooltip 用)
  - matchMedia polyfill (antd Table 用)
  - getComputedStyle(elt, pseudoElt) 拦截（jsdom not implemented）

测试规模：127 passed（路 7 后）
  - tests/lib/safeCall.spec.ts          12
  - tests/lib/sse.spec.ts              11
  - tests/lib/useNotify.spec.tsx         6
  - tests/lib/useApi.spec.tsx           8
  - tests/types/sse.spec.ts             11
  - tests/components/StreamView.spec.tsx  11
  - tests/components/CourseInlineCard.spec.tsx 11
  - tests/components/CourseFields.spec.tsx      18 (路 7 新增)
  - tests/components/recommend/StatCard.spec.tsx           3
  - tests/components/recommend/PipelineTimeline.spec.tsx   6
  - tests/components/recommend/CourseCard.spec.tsx         9
  - tests/components/recommend/SingleResultView.spec.tsx   6
  - tests/components/recommend/CompareView.spec.tsx        5
  - tests/components/recommend/constants.spec.tsx          5
```

## 10. 关键决策记录

| 决策 | 时机 | 理由 |
|---|---|---|
| 拆 CourseFields（路 7） | 2026-08-18 | 课程卡两实现共享 80% 字段；双份维护成本高 |
| CourseInlineCard 不渲染 match_reasons | 2026-05-18 | 流式每 token 重渲染 → match_reasons 静态信息不在流里展示 |
| CourseCard 用 antd `<Card>` | 2026-08-18 | 静态结果 → hoverable + match_reasons 展开 |
| 抽 `<App>` context | 路 3 | antd 5+ 推荐；消除 `Static function can not consume context` 警告 |
| 抽 SSE `id:` + Last-Event-ID | 路 2 | 跨请求续传；前端断网后自动从 last_event_id 继续 |
| rAF 节流 token 累积 | 路 2 | O(N) → O(1) per token；长推荐流下肉眼可见的卡顿修复 |
| jsx-a11y fix all now | 路 1 + 路 6 补 | 全仓装饰图标 aria-hidden + a11y 语义标签 |
| Prettier 与 ESLint 共存 | 路 3 | `eslint-config-prettier` 必须在 defineConfig 末尾 |
| types/index.ts 保留不动 | 路 7 | 12 个文件活跃引用，是 v2 核心类型源（**不是遗留**） |

## 11. 故障排查速查

| 症状 | 排查点 |
|---|---|
| `npm run lint` warning：`'Tag' is defined but never used` | 检查 import 是否还有该组件用到 |
| `npm test` `ResizeObserver is not defined` | tests/setup.ts 的 polyfill 是否被覆盖（不要 eslint-disable 该处） |
| `npm test` `getComputedStyle ... not implemented` | 同上，setup.ts 拦截 |
| `npm run dev` 启动后 host:3001 502 | docker desktop 转发 bug；改用 `127.0.0.1:8000` 或启 `docker compose --profile frontend up -d` |
| `<App>` context warning | 顶层 layout.tsx 必须包 `<App>` |
| SSE 流卡住不返回 | 检查后端 LLM 配额（路 4 live eval 卡死主因） |
| 流式 token 不显示 | 检查 StreamView 的 rAF flush + ref→state 同步 |
