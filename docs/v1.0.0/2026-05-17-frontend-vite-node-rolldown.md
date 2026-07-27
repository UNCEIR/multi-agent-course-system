# 前端 Vite 8 / Rolldown 与 Node 20.17 不兼容排查

## 背景与问题

- 用户在 `frontend` 执行 `npm run dev` 时出现两类报错：  
  1. **Node 版本**：`You are using Node.js 20.17.0. Vite requires Node.js version 20.19+ or 22.12+`。  
  2. **原生绑定**：`Cannot find native binding`，缺少 `@rolldown/binding-win32-x64-msvc`（Rolldown 可选依赖在 Windows/npm 场景下常见问题）。
- 影响范围：本地无法启动前端开发服务器。

## 总体架构方案

- **Vite 7/8** 的 `engines` 为 `^20.19.0 || >=22.12.0`，落在 **Node 20.17.0 之外**。  
- **Vite 6** 仍为 `^18.0.0 || ^20.0.0 || >=22.0.0`，与 **Node 20.17** 兼容，且继续使用 **esbuild/Rollup** 链路，不依赖 **Vite 8 的 Rolldown** 与对应 Windows native 包。  
- `@tailwindcss/vite@4.x` 的 peer 声明为 `vite ^5 || ^6 || ^7 || ^8`，因此 **降为 Vite 6** 仍可配合当前 Tailwind 插件。

## 细节实现

- `frontend/package.json`：  
  - `vite`：`^8.0.10` → **`^6.4.2`**。  
  - 新增 **`engines.node`**：`^18.18.0 || ^20.0.0 || >=22.0.0`（与 Vite 6 官方范围对齐，便于后续 CI/协作一眼看出支持区间）。  
- 依赖重装：删除 `frontend/node_modules` 与 **`package-lock.json`** 后重新 `npm install`，避免锁文件仍解析到 Vite 8 / Rolldown 残留树。

### 备选方案（未采纳）

- 将本机 Node 升级到 **≥20.19** 或 **≥22.12**，继续使用 Vite 8；能解决版本检查与 Rolldown 安装问题时也可行。本项目选择降级 Vite 以降低对团队成员 Node 补丁版本的硬性要求。

## Debug 结论

| 现象 | 根因 |
|------|------|
| Vite 报 Node 过旧 | Vite 7/8 `engines` 要求 20.19+ |
| `@rolldown/binding-*` MODULE_NOT_FOUND | Vite 8 走 Rolldown；可选原生依赖未正确安装或过旧锁树 |

## 测试与验证

- 已在 `frontend` 执行 **`npm install`**（清理后重装，`added 107 packages`）。  
- 已执行 **`npm run build`**：`tsc` + `vite build` **成功**，输出 `✓ built in ~18–19s`。  
- 未在本机会话中长时间运行 `npm run dev`；若在 Node 20.17 下需再确认浏览器访问与 HMR。

## 经验与后续

- **Node 补丁号**也会影响工具链：`20.17` 与 `20.19` 仅差小版本，但 Vite 8 已硬性拦截。升级 Node 或使用与 `engines` 匹配的 Vite 大版本可避免此类问题。  
- Windows 上出现 **optional dependencies** 缺失时，除升级 npm 外，**删 `node_modules` + lock 重装**仍是有效手段（与报错里 Rolldown 提示一致）。  
- 若未来需要 **Vite 8**，团队应统一：**Node ≥20.19 或 ≥22.12**，并重装前端依赖以确保 Rolldown binding 就位。
