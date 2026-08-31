# 前端 dev 白屏 + 错乱组件（2026-08-24）

> 症状：`npm run dev` 后浏览器 `localhost:3000` 几乎白屏，仅有少许错乱组件。
> `npm run build` 成功（`.next/BUILD_ID` 存在，10 路由全静态预渲染）—— 问题只在 dev 运行时暴露。
> 修复后：`npm run build` / `npm run lint` / `npm test`（127 用例）全部通过。

---

## 增量复盘：第二阶段修复（Header 内部 5 个细节问题）

> 第一阶段（白屏 + 几乎白屏）的 4 个根因修了之后，第二阶段通过浏览器实测发现 Header 区域还有 5 个细节问题：
>
> 1. Menu `flex: 1` 撑满剩余空间，但菜单项宽度不够，挤掉了徽章（badge 被压成 64×64）
> 2. Menu `flex: 1` 没设 `min-width: 0`，导致 overflow indicator 不工作（菜单不自动收起）
> 3. 徽章容器宽度受限导致内容单字换行竖排（"API 在线" 4 字竖排成 64px 高）
> 4. antd 6 Layout Header 内部 cssinjs 注入的 `line-height: var(--ant-layout-header-height)` = 64px，所有 Header 子元素继承（即使父级高度是 56px），导致徽章内部 span `line-height: 64px` 把每行撑成 64px
> 5. 配合 #3，徽章 `flex-shrink: 1`（默认）让窄容器单字换行成 4 行 → 高度变成 4 × 64 = 256px（实际 64px，因为 line-height 限一行）

### 5 个根因（按根因从深到浅）

#### 根因 A（最深）：antd 6 Layout Header 的 line-height 继承

**症状贡献**：徽章内 span 单字换行后，每行高度 64px，徽章整体高度变成 ~64-74px，比 Header (56px) 还高，导致徽章溢出 Header。

**根因**：antd 6 cssinjs 给 Header 注入 `line-height: var(--ant-layout-header-height)`（64px），所有 Header 子元素继承。即使我在 inline style 写了 `height: 56`，line-height 仍是 64px。

**修复**：`src/app/(main)/layout.tsx` 第 156 行给 statusText span 加 `style={{ lineHeight: 1.5 }}` 强制覆盖：

```tsx
<span style={{ lineHeight: 1.5 }}>{statusText}</span>
```

#### 根因 B：Menu `flex: 1` 没设 `min-width: 0`

**症状贡献**：Menu 撑到 ~830px，徽章被挤到 64-91px。

**根因**：flex item 默认 `min-width: auto`（防止被压到 0），即使 Menu 内容不需要那么多宽度，它仍占据 `flex: 1` 分配的空间。徽章 `flex: 1 1 auto`（默认）允许 shrink，被压到内容最小宽度以下。

**修复**：
- Menu 加 `minWidth: 0` —— 允许 Menu 被无限压缩，antd Menu 的 overflow indicator 自动收起多余菜单项（实测从 8 项收到 5 项 + ellipsis）
- 徽章加 `flexShrink: 0` + `whiteSpace: 'nowrap'` —— 徽章不被压，保持水平

```tsx
<Menu style={{ flex: 1, minWidth: 0, ... }} />
<div style={{ ..., flexShrink: 0, whiteSpace: 'nowrap' }}>...</div>
```

### 排查路径（给后续 agent）

```
Header 错乱（菜单挤出徽章 / 徽章文字竖排）
  ↓
1. Chrome DevTools → computed style 看徽章 width/height 是否异常
   - w<100 且 h>40 → 徽章被压垮，根因 B
  ↓
2. 看 span computed line-height
   - 等于父 Header 高度（56 或 64）→ 根因 A
   - 正常 1.5/normal → 修复 A 后恢复正常
  ↓
3. Menu 没自动收起 → 根因 B 的 min-width 修复
  ↓
4. 仍异常？看父元素 flex 布局 / 视窗宽度 → 缩窄菜单项 padding 或考虑响应式断点
```

### 验证（修复后）

```
Header 高 56 ✓
Menu 5 项 + ellipsis overflow ✓
徽章 91×28 ✓
徽章文字 "API 在线" 单行横排 ✓
Hub 卡片 "登录 / 注册" 横排 ✓
Header 整体无溢出 ✓
```

---

## 阶段一（白屏修复）原始内容保留 ↓

---

## 症状再确认

| 维度 | 表现 |
|---|---|
| 命令 | `npm run dev` (Turbopack 16.3.1) |
| 浏览器 | Header 几乎不可见、Hub 卡片错位、字体失效；Console 有大量 antd `<empty string>` style 注入失败 + `findDOMNode` 警告 |
| 生产构建 | `npm run build` 成功且无警告 —— 因为 build 把所有 client component 预渲染成静态 HTML，hydration / cssinjs 顺序问题在生产模式不显式报错 |

**关键启示**：生产构建成功不代表运行时正常。dev 模式的 Turbopack 编译路径与生产 webpack 不同，dev 会暴露 ESM/CJS 互操作、CSS-in-JS 注入顺序、React 19 findDOMNode 等问题。

---

## 四个根因（按概率从高到低）

### 根因 1（最高概率）：`@ant-design/v5-patch-for-react-19` 缺失

**症状贡献**：console 持续打印 `findDOMNode is deprecated`，部分 antd hook 返回 `undefined`，`App.useApp()` 拿不到 message/notification 实例 → `useNotify().toast.*` 静默失效。

**根因**：antd 6.6.0 内部仍依赖 React 17 的 `findDOMNode` API（用于 `Trigger` / `Wave` 等组件定位 DOM），React 19 已移除。官方补丁 `@ant-design/v5-patch-for-react-19` 通过 monkey-patch 在应用入口前重新挂上兼容实现。

**修复**：

```bash
cd frontend
npm i -D @ant-design/v5-patch-for-react-19
```

在 `src/app/layout.tsx` **首行**（早于任何 `antd` import）：

```tsx
import "@ant-design/v5-patch-for-react-19";
import "./globals.css";
// ... 其余 Geist / metadata
```

> 必须放在最顶部：补丁要在 antd 模块被 import 前生效。

---

### 根因 2：`next.config.ts` 缺 `transpilePackages`

**症状贡献**：dev Turbopack 控制台刷屏 `Warning: [antd: compatible] <empty string> ... cssinjs 注入失败`，所有 antd 组件样式丢失 → 几乎白屏 + 组件结构错乱。

**根因**：antd 6 + `@ant-design/cssinjs@2.x` 走 ESM + 大量 `rc-*` 子包（CJS/ESM 混用）。Next.js 16 默认不编译 `node_modules` 下的 ESM，Turbopack 看到 `antd` 入口时拿到的是 `<empty string>` 占位。

**修复**：在 `next.config.ts` 显式声明需编译的包：

```ts
const nextConfig: NextConfig = {
  transpilePackages: [
    "antd",
    "@ant-design/icons",
    "@ant-design/cssinjs",
    "@ant-design/cssinjs-utils",
    "@ant-design/icons-svg",
    "@ant-design/colors",
    // antd 依赖的 rc-* 工具库
    "rc-util", "rc-pagination", "rc-picker", "rc-tree", "rc-table",
    "rc-input", "rc-select", "rc-cascader", "rc-checkbox", "rc-dropdown",
    "rc-field-form", "rc-image", "rc-mentions", "rc-menu", "rc-motion",
    "rc-notification", "rc-overflow", "rc-progress", "rc-rate",
    "rc-resize-observer", "rc-segmented", "rc-slider", "rc-steps",
    "rc-switch", "rc-tabs", "rc-textarea", "rc-tooltip", "rc-tree-select",
    "rc-trigger", "rc-upload", "rc-virtual-list",
  ],
  // 保留现有 rewrites
  async rewrites() { /* ... */ },
};
```

> **依据**：观察到的具体 `rc-*` 包列表来自修复后 `npm ls antd` 的依赖树。后续若 antd 升级引入新 `rc-*`，需同步追加。

---

### 根因 3：login 页 `<App>` / `<ConfigProvider>` 嵌套顺序错误

**症状贡献**：login 页 `useNotify().toast.*` 拿不到 theme（无 token 注入），`App.useApp()` 的 message 实例是默认主题色（蓝色），与全局学院蓝不一致；视觉上像「错乱组件」。

**根因**：antd 6 推荐顺序 `<ConfigProvider><App>`，让 `<App>` 在 ConfigProvider 内部才能读到 theme/locale context。

**现状对比**：

| 位置 | 原顺序 | 应为 |
|---|---|---|
| `(main)/layout.tsx` | `<ConfigProvider><App>` ✓ | — |
| `login/page.tsx` | `<App><ConfigProvider>` ✗ | `<ConfigProvider><App>` |

**修复**：`src/app/login/page.tsx` 第 64-65 行 + 闭合标签 157-158 行交换顺序。

---

### 根因 4：Tailwind v4 preflight 与 antd 6 样式冲突

**症状贡献**：button 变方块、input 错位、antd message/notification 被 Header（`z-index: 100`）盖住。

**根因**：Tailwind v4 的 `@import "tailwindcss";` 自动启用 preflight，重置 button/input/select/textarea/h1-h6 的全部默认样式；antd 6 内部仍依赖部分 user-agent 样式。

**修复**：在 `globals.css` `@import "tailwindcss";` 后追加 `@layer base` 补回最小必需值：

```css
@layer base {
  button { cursor: pointer; padding: 0; border: none; background: transparent;
           font: inherit; color: inherit; text-align: inherit; }
  input, textarea, select { margin: 0; font: inherit; color: inherit; }
  .ant-message, .ant-notification, .ant-modal-mask, .ant-modal-wrap { z-index: 2000; }
  body { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
}
```

> **不关闭 preflight**：项目用了 `min-h-full` / `flex` / `h-full` 等 Tailwind utility。完整关闭 preflight 会丢失 layout 基础。

---

## 排查顺序（给后续 agent 的速查路径）

```
localhost:3000 dev 白屏 + 错乱
  ↓
1. console 是否报 findDOMNode / antd <empty string> cssinjs？
  ├─ 是 findDOMNode → 根因 1：装 v5-patch-for-react-19 + layout 顶行 import
  ├─ 是 cssinjs <empty string> → 根因 2：next.config.ts 加 transpilePackages
  └─ 两个都报 → 两个都修（最常见组合）
  ↓
2. 修复后仍有「局部错乱」（不是白屏）：
  ├─ login 页单独错乱 → 根因 3：检查 App/ConfigProvider 顺序
  └─ button/input 形状不对 / 弹窗被盖 → 根因 4：globals.css 补 @layer base
  ↓
3. 仍异常？删 .next 缓存 + 重装 node_modules
  ↓
4. 还不行？抓 `next dev --turbo` 的完整 stderr 找 antd 版本兼容性 changelog
```

---

## 验证清单（每改一项后跑一次）

```bash
cd frontend
npm run lint          # 0 错
npm test              # vitest 全部通过（127 → 现在 127）
npm run build         # 10 路由全静态、TypeScript 通过
```

**通过判据**：
- `lint` 0 error 0 warning（仅风格 warning 可放行）
- `test` 0 fail
- `build` 0 error
- `localhost:3000` 在 dev 模式肉眼：Header / 渐变背景 / 网格底纹 / Hub 卡片 / 路由跳转全部正常
- 浏览器 console 无 `findDOMNode` 警告、无 `<empty string>` style 警告

---

## 回滚指引

如果某项 Fix 引发新问题，按 C → D → B → A 顺序回滚（最小影响先撤）：

1. **Fix C**：login 页两行换回原顺序即可，无副作用。
2. **Fix D**：删 `globals.css` 顶部 `@layer base { ... }` 块，无副作用。
3. **Fix B**：从 `next.config.ts` 删 `transpilePackages`，构建可能仍 OK 但 dev 报 cssinjs 警告。
4. **Fix A**：卸包 `npm uninstall @ant-design/v5-patch-for-react-19`、删 layout 顶部 import，重新出现 `findDOMNode` 警告。

---

## 影响的文件清单

| 文件 | 改动 |
|---|---|
| `frontend/package.json` | +1 devDep: `@ant-design/v5-patch-for-react-19` |
| `frontend/package-lock.json` | 同步更新 |
| `frontend/src/app/layout.tsx` | +1 行 import |
| `frontend/next.config.ts` | + `transpilePackages` 数组 |
| `frontend/src/app/login/page.tsx` | 第 64-65 行 + 157-158 行 顺序交换 |
| `frontend/src/app/globals.css` | + `@layer base { ... }` 块 |

未涉及：所有页面 / 组件 / store / lib / hooks / tests。

---

## 给后续 agent 的预防建议

- **新装 antd 版本时**，确认 React 主版本兼容；若 React ≥ 19，**必须**装 `@ant-design/v5-patch-for-react-19` 并在应用入口首行 import。
- **新增 `rc-*` 子依赖时**（antd 升级可能引入），同步追加到 `next.config.ts` 的 `transpilePackages`。
- **新页面用 antd 时**，ConfigProvider + App 嵌套顺序：`<ConfigProvider><App>{children}</App></ConfigProvider>`。
- **Tailwind 与 antd 共存时**，不要关闭 preflight，改用 `@layer base` 补回冲突项。
- **判断 dev 与 prod 渲染差异**：dev Turbopack 暴露运行时问题，生产 webpack 静默通过。修复验证必须看 `npm run dev` 浏览器表现，不能只看 `npm run build` 成功。
