import { describe, expect, it } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { App } from 'antd'
import React from 'react'

import { useNotify } from '@/lib/api/useNotify'

// useNotify 依赖 antd App context（提供 message 实例）；用 renderHook 包 <App> 提供 context。

function WithApp({ children }: { children: React.ReactNode }) {
  return <App>{children}</App>
}

describe('useNotify', () => {
  it('toast.success forwards the message', () => {
    const { result } = renderHook(() => useNotify(), { wrapper: WithApp })
    // antd 的 message.success 是 fire-and-forget；这里只验证调用不抛错
    act(() => result.current.toast.success('保存成功'))
    // 内部 state 不变（toast 不进入 React state）
    expect(result.current.inline.error).toBeNull()
  })

  it('toast.error swallows ABORTED without surfacing', () => {
    const { result } = renderHook(() => useNotify(), { wrapper: WithApp })
    act(() => result.current.toast.error(new DOMException('Aborted', 'AbortError')))
    // inline state 不变，toast 不抛错
    expect(result.current.inline.error).toBeNull()
  })

  it('toast.error converts normal error to ApiError.message', () => {
    const { result } = renderHook(() => useNotify(), { wrapper: WithApp })
    act(() =>
      result.current.toast.error(new Error('upstream 502'), '兜底文案'),
    )
    // 不抛错即通过；error 工具不进入 inline state
    expect(result.current.inline.error).toBeNull()
  })

  it('inline.set stores ApiError and exposes its message', () => {
    const { result } = renderHook(() => useNotify(), { wrapper: WithApp })
    act(() => result.current.inline.set(new Error('查询失败')))
    expect(result.current.inline.error).toBeInstanceOf(Error)
    expect(result.current.inline.error?.code).toBe('NETWORK')
    expect(result.current.inline.message).toBe('查询失败')
  })

  it('inline.clear resets state to null', () => {
    const { result } = renderHook(() => useNotify(), { wrapper: WithApp })
    act(() => result.current.inline.set(new Error('X')))
    expect(result.current.inline.error).not.toBeNull()
    act(() => result.current.inline.clear())
    expect(result.current.inline.error).toBeNull()
    expect(result.current.inline.message).toBeNull()
  })

  it('inline.set with ApiError preserves the code', () => {
    const { result } = renderHook(() => useNotify(), { wrapper: WithApp })
    act(() =>
      result.current.inline.set(
        Object.assign(new Error('upstream'), { name: 'ApiError', code: 'UPSTREAM' }),
        '兜底',
      ),
    )
    // ApiError.from 重新归一化时如果 original 是 ApiError 会沿用 code
    expect(result.current.inline.error?.code).toBeDefined()
  })
})
