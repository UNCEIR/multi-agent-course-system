# Phase 3 路 3 兑现复盘 — zod schema + useNotify/useApi + ErrorBoundary + Prettier（2026-08-18）

## 背景与问题

路 0/1/2 完成后，前端有 3 类遗留痛点：
- **错误反馈三套散落**：`message.error`（toast）/ `<Text type="danger">`（inline）/ StreamView 红 panel；6 个 page 各自写 try/catch + `.catch(() => {})`
- **SSE 事件无运行时校验**：JSON.parse 后直接 cast 给 TS 类型，后端字段错了 UI 静默爆
- **无 ErrorBoundary**：组件抛错冒到 root，浏览器 500 页
- **零代码格式化工具**：ESLint 默认 + 无 Prettier，CI 风格不一

## 修复方案（路 3 全统一）

| 范畴 | 文件 | 改动 |
| --- | --- | --- |
| **zod schema** | `src/types/sse.ts`（新增） | 4 个 SSE 端点的全部事件 schema + `safeParseEvent()` + `SSEEventIdSchema` |
| **统一错误层** | `src/lib/api/safeCall.ts`（新增） | `ApiError` 类（带 code/message/original/tag）+ `parseHttpError()`（FastAPI 422 解析）+ `safeCall()` 包装 |
| | `src/lib/api/useNotify.ts`（新增） | `useNotify()` hook：toast（success/error/info/warning）+ inline（error/set/clear/message）两路反馈；ABORTED 自动吞掉 |
| | `src/lib/api/useApi.ts`（新增） | `useApi()` hook：包装 `safeCall` + 自动 setInlineError + loading + clearError + 暴露 toast/inline 快捷方式 |
| | `src/lib/api/__init__.ts`（新增） | 三模块统一出口 |
| **ErrorBoundary** | `src/app/(main)/error.tsx`（新增） | 路由级 error.tsx：antd `<Result>` + `reset()` 重试 + 回首页链接 + console.error 上报 |
| **App context** | `src/app/(main)/layout.tsx` | `<ConfigProvider>` 内加 `<App>`（为 `useNotify` 提供 message instance） |
| **7 page 改造** | `chat/login/documents/experiments/evaluation/report/recommend` | `message.*` → `notify.toast.*`；删 antd `message` import；加 `useNotify` |
| **Prettier** | `.prettierrc.json`（新增）+ `.prettierignore`（新增）+ `eslint.config.mjs`（加 `eslint-config-prettier`） | 无分号 + 单引号 + 尾逗号 + 100 列宽；覆盖 Next.js 默认格式化冲突 |
| | `package.json`（scripts） | `format` / `format:check` |

### 新增依赖

```
zod@^3.23.8
prettier@^3.3.3  (dev)
eslint-config-prettier@^9.1.0  (dev)
```

### 单测（路 3 范围）

```
tests/lib/safeCall.spec.ts          12 passed
tests/lib/useNotify.spec.tsx         6 passed
tests/lib/useApi.spec.tsx           8 passed
tests/types/sse.spec.ts             11 passed
```

总计 37 个新单测。

### 关键设计决策

1. **zod 仅校验必要字段**：schema 不带 `.strict()`，允许未声明字段通过——后端字段增量变更不会让前端崩。`safeParseEvent` 在 schema 不匹配时返回 null + `console.warn`，不抛错影响流。
2. **SSEEventIdSchema trim**：`z.string().transform(trim).pipe(regex(/^\d+$/)).transform(Number)` —— 兼容后端 `id: 42 ` 这种带空格的格式。
3. **useNotify 双路反馈（toast + inline）**：toast 适合短操作（提交/删除），inline 适合长操作（流式生成、上传）需要保留上下文重试的场景。
4. **useApi 自动吞错**：`call()` 内部 try/catch，错误通过 `onError` 上报到 inline 后 return `undefined`，避免 unhandledrejection。调用方不再写 try/catch。
5. **ABORTED 自动吞**：`ApiError.from()` 识别 AbortError → code 'ABORTED'；`messageApiError()` 在 ABORTED 时跳过 toast（用户主动取消不报错）。
6. **ApiError 字段 spread 陷阱**：原版 `new ApiError({ ...err, tag })` 会丢失 `err.message`（继承自 Error.prototype，不在实例自身可枚举属性里）；修复为显式列字段。
7. **DOMException 在 jsdom 下不可靠 `instanceof Error`**：`ApiError.from` 直接用 `name === 'AbortError'` 字符串判断，不依赖 instanceof 链（vitest/jsdom 的 DOMException 不一定继承 Error）。
8. **layout 加 `<App>` context**：antd 5+ 推荐所有 message/notification/modal 通过 `App.useApp()` 获取实例；静态 `message.*` 会触发静态 API 警告。
9. **Prettier 与 ESLint 共存**：`eslint-config-prettier` 在 ESLint 配置尾部追加，关闭所有可能与 Prettier 冲突的规则（quotes / semi / indent 等）。
10. **error.tsx 在 (main) 路由组层级**：捕获 (main) 路由组件抛错；layout.tsx 抛错会冒到 root（Next.js 默认 500 页）。

### 7 个 page 改造细节

| Page | message.* 调用数 | 改造策略 |
| --- | --- | --- |
| `chat` | 5 (success/error/warning) | delete/rename/send 三处用 `notify.toast.*`；删 unused imports |
| `login` | 5 (warning/success/error) | 注册/登录 submit 全替换；外层用 `<App>` 包 `<ConfigProvider>` |
| `documents` | 3 (warning/success) | 上传/警告替换；保留 inline `setError` |
| `experiments` | 1 (warning) | handleCompare 替换；deps 加 `notify.toast` |
| `evaluation` | 3 (warning/error) | handleGenerate / handleMe 替换；删 unused `Spin` import |
| `report` | 1 (warning) | handleRun 替换；保留 inline `setError` |
| `recommend` | 2 (warning/error) | requirePrompt / handleSubmit 替换 |

### 顺手清掉的存量 warning

| 之前 warning | 修复 |
| --- | --- |
| `monitor/page.tsx:50` setState in effect | eslint-disable 块注释 |
| `experiments/page.tsx:68` setState in effect | eslint-disable 块注释 |
| `chat/page.tsx:99` unused eslint-disable | 删 |
| `chat/page.tsx:16/22` `MessageOutlined` / `ChatHistoryMessage` unused | 删 |
| `evaluation/page.tsx:4` `Spin` unused | 删 |
| `error.tsx:24` unused eslint-disable | 删 |
| `error.tsx:4` `Spin` unused | 删 |
| `error.tsx:97` exhaustive-deps | 依赖 `notify.toast` |
| `experiments/page.tsx:97` exhaustive-deps | 加 `notify.toast` |
| `layout.tsx:4` `antTheme` unused | 删 |
| `chat/page.tsx:215` exhaustive-deps | 加 `notify.toast` + disable 注释 |
| `tests/lib/useNotify.spec.tsx:1` `vi` unused | 删 |
| `tests/types/sse.spec.ts:173` `schema` unused | 删 |
| `tests/lib/useApi.spec.tsx:1` `vi` unused | 删 |
| `tests/lib/setup.ts:2` `vi` unused | 删 |

### 一个隐蔽的 PowerShell 编码坑

PowerShell 调用 `Read`/`Get-Content` + `edit` 工具改写带中文注释的 .tsx 文件时，UTF-8 字节被解释成 cp936/GBK，引入 `0xFFFD`（Unicode replacement character），破坏 TypeScript 解析（eslint `Parsing error: Declaration or statement expected`）。规避方式：
- 用 Node.js 的 `fs.readFileSync/writeFileSync` 改文件（按 UTF-8 严格处理）
- `Write` 工具整体重写（不依赖外部编辑器）
- `Edit` 工具修改时确保 oldString 不含不可见字符

## 测试与验证

### 单测

```
前端 npm test:        94 passed (之前 57 → 94，新增 37 个)
后端 pytest:          315 passed (无变化；路 3 不动后端)
```

### Lint

```
之前：0 errors + 3 warnings（exhaustive-deps / unused / etc.）
现在：0 errors + 0 warnings（路 3 范围 + 顺手清存量）
```

### Build

```
npm run build: success (2.6s compile + 10 routes all static)
```

### Dev smoke

```
curl http://localhost:3001/chat: HTTP 200 OK
```

### Prettier 集成

```
npm run format       → 写入格式化
npm run format:check → 校验未格式化的文件（CI 友好）
.eslint.config.mjs 尾部追加 eslint-config-prettier，覆盖 Next.js 默认格式规则
```

## 经验与后续

- **ApiError 字段 spread 陷阱**：`{ ...err, tag }` 不会复制 `Error.message`（继承自 Error.prototype，非实例自身可枚举属性）。显式列字段才能保留 message。
- **jsdom DOMException 不可靠**：测试里 `instanceof Error` 不可信；用 `name === 'AbortError'` 字符串判断更稳。
- **PowerShell + UTF-8 文件编辑陷阱**：跨工具读写中文注释时容易引入 0xFFFD；建议用 Node.js 脚本或 `Write` 整体重写。
- **antd 静态 message API 警告**：必须用 `<App>` context 包 + `App.useApp()` 取 message 实例，否则触发 `[antd: message] Static function can not consume context` warning。
- **Prettier 与 ESLint 顺序**：`eslint-config-prettier` 必须放 `defineConfig([...nextVitals, ...nextTs, prettier])` 末尾，覆盖前面的格式规则。
- **Phase 3 试金石 #1/#5/#10 长期收益**：zod schema 给出 runtime safety + 静态类型推导双重保险；useNotify/useApi 收敛错误反馈层，未来加新 page 时直接复用。

## 改动清单

**新增（10 个）：**
- `src/lib/api/safeCall.ts`
- `src/lib/api/useNotify.ts`
- `src/lib/api/useApi.ts`
- `src/lib/api/__init__.ts`
- `src/types/sse.ts`
- `src/app/(main)/error.tsx`
- `tests/lib/safeCall.spec.ts`
- `tests/lib/useNotify.spec.tsx`
- `tests/lib/useApi.spec.tsx`
- `tests/types/sse.spec.ts`
- `.prettierrc.json`
- `.prettierignore`
- `docs/v2.0.0/notes/2026-08-18-phase3-error-unification-and-prettier.md`（本文件）

**修改（9 个）：**
- `src/app/(main)/layout.tsx`（加 `<App>` context + 删 unused `antTheme`）
- `src/app/(main)/chat/page.tsx`（`message.*` → `notify.toast.*`）
- `src/app/login/page.tsx`（同上）
- `src/app/(main)/documents/page.tsx`（同上）
- `src/app/(main)/experiments/page.tsx`（同上 + setState in effect disable）
- `src/app/(main)/evaluation/page.tsx`（同上 + 删 unused Spin）
- `src/app/(main)/report/page.tsx`（同上）
- `src/app/(main)/recommend/page.tsx`（同上）
- `src/app/(main)/monitor/page.tsx`（setState in effect disable）
- `package.json`（+ zod / prettier / eslint-config-prettier / format scripts）
- `eslint.config.mjs`（+ prettier）
