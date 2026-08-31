import type { NextConfig } from "next";

// docker desktop 转发 host → container 8000 偶发 502；用 127.0.0.1 强制 IPv4 解析
// 比 localhost 少一次 DNS 解析，能减少（但不能完全消除）转发层 502。
// 根治方案是把 Next.js 也放进 docker compose 网络，目标改为 http://python-api:8000。
const API_PROXY_TARGET =
  process.env.API_PROXY_TARGET || "http://127.0.0.1:8000";

// antd 6 走 ESM + cssinjs，Next.js / Turbopack 默认不会编译 antd 包内的 ESM 与
// rc-* 工具库 → 运行时 `<empty string>` style 注入失败、dev 白屏错乱。
// 这里强制 Next.js 把 antd 系 ESM 源码当作应用代码编译。
const nextConfig: NextConfig = {
  // dev 代理响应体超时：Next.js dev 的 rewrites 代理默认 30s 就掐断长 SSE（report 批量生成
  // 12~15min 必被截断 → 前端 network error → uvicorn cancel）。这里显式放大到 30 分钟。
  // 见 node_modules/next/dist/server/lib/router-utils/proxy-request.js（proxyTimeout || 30000）。
  experimental: {
    proxyTimeout: 30 * 60 * 1000,
  },
  transpilePackages: [
    "antd",
    "@ant-design/icons",
    "@ant-design/cssinjs",
    "@ant-design/cssinjs-utils",
    "@ant-design/icons-svg",
    "@ant-design/colors",
    "rc-util",
    "rc-pagination",
    "rc-picker",
    "rc-tree",
    "rc-table",
    "rc-input",
    "rc-select",
    "rc-cascader",
    "rc-checkbox",
    "rc-dropdown",
    "rc-field-form",
    "rc-image",
    "rc-mentions",
    "rc-menu",
    "rc-motion",
    "rc-notification",
    "rc-overflow",
    "rc-progress",
    "rc-rate",
    "rc-resize-observer",
    "rc-segmented",
    "rc-slider",
    "rc-steps",
    "rc-switch",
    "rc-tabs",
    "rc-textarea",
    "rc-tooltip",
    "rc-tree-select",
    "rc-trigger",
    "rc-upload",
    "rc-virtual-list",
  ],
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_PROXY_TARGET}/api/:path*`,
      },
      {
        source: "/health",
        destination: `${API_PROXY_TARGET}/health`,
      },
    ];
  },
};

export default nextConfig;
