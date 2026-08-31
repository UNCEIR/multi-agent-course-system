// Vitest 启动钩子：每个测试文件前后清理
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'
import '@testing-library/dom'

// jsdom 缺 ResizeObserver / matchMedia / getComputedStyle(elt, pseudoElt)
// antd 的 Card/Tooltip/Table 依赖这几个浏览器 API；这里 polyfill noop 实现。

class ResizeObserverPolyfill {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
// jsdom 类型不暴露 ResizeObserver，用 any cast 兜底
type GlobalAny = typeof globalThis & {
  ResizeObserver: typeof ResizeObserverPolyfill
  matchMedia: (query: string) => MediaQueryList
}
const g = globalThis as GlobalAny
g.ResizeObserver = g.ResizeObserver || ResizeObserverPolyfill

g.matchMedia =
  g.matchMedia ||
  ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }))

// getComputedStyle 的第二参数（pseudoElt）在 jsdom 中 not implemented，
// antd Table 测量滚动条宽度时用到。这里拦截调用，仅返回第一个参数的基础计算。
const originalGetComputedStyle = window.getComputedStyle
window.getComputedStyle = function (
  elt: Element,
  pseudoElt?: string | null,
): CSSStyleDeclaration {
  // antd 调用时通常传 null/undefined；传非空字符串时降级为 elt-only
  if (pseudoElt) {
    return originalGetComputedStyle.call(window, elt)
  }
  return originalGetComputedStyle.call(window, elt)
}

// 自动卸载渲染组件，避免测试间状态泄漏
afterEach(() => {
  cleanup()
})
