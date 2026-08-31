import { describe, expect, it } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { App } from 'antd'
import React from 'react'

import { useApi } from '@/lib/api/useApi'

function WithApp({ children }: { children: React.ReactNode }) {
  return <App>{children}</App>
}

describe('useApi', () => {
  it('call returns the resolved value on success', async () => {
    const { result } = renderHook(
      () => useApi({ tag: 'useApi:test' }),
      { wrapper: WithApp },
    )
    let value: number | undefined
    await act(async () => {
      value = await result.current.call(async () => 99)
    })
    expect(value).toBe(99)
    expect(result.current.error).toBeNull()
    expect(result.current.loading).toBe(false)
  })

  it('call captures error into inline state and returns undefined', async () => {
    const { result } = renderHook(
      () => useApi({ tag: 'useApi:test', fallbackMessage: 'fallback' }),
      { wrapper: WithApp },
    )
    let value: number | undefined = 42
    await act(async () => {
      value = await result.current.call(async () => {
        throw new Error('upstream 502')
      })
    })
    expect(value).toBeUndefined()
    expect(result.current.error).not.toBeNull()
    expect(result.current.error?.message).toBe('upstream 502')
    expect(result.current.loading).toBe(false)
  })

  it('loading flips true during call and false after', async () => {
    const { result } = renderHook(() => useApi({ tag: 'x' }), { wrapper: WithApp })
    // Sync-resolve promise so call finishes in the same microtask;
    // Awaiting inside act lets setLoading(true) flush before checking final state.
    await act(async () => {
      await result.current.call(async () => {
        await Promise.resolve()
        return 'ok'
      })
    })
    expect(result.current.loading).toBe(false)
  })

  it('loading starts false before any call', () => {
    const { result } = renderHook(() => useApi({ tag: 'x' }), { wrapper: WithApp })
    expect(result.current.loading).toBe(false)
  })

  it('clearError resets inline error', async () => {
    const { result } = renderHook(() => useApi({ tag: 'x' }), { wrapper: WithApp })
    await act(async () => {
      await result.current.call(async () => {
        throw new Error('boom')
      })
    })
    expect(result.current.error).not.toBeNull()
    act(() => result.current.clearError())
    expect(result.current.error).toBeNull()
  })

  it('exposes toast/inline shortcuts', () => {
    const { result } = renderHook(() => useApi({ tag: 'x' }), { wrapper: WithApp })
    expect(typeof result.current.toast.success).toBe('function')
    expect(typeof result.current.toast.error).toBe('function')
    expect(typeof result.current.inline.set).toBe('function')
    expect(typeof result.current.inline.clear).toBe('function')
  })

  it('clearOnCall=true clears previous error on new call', async () => {
    const { result } = renderHook(
      () => useApi({ tag: 'x', clearOnCall: true }),
      { wrapper: WithApp },
    )
    await act(async () => {
      await result.current.call(async () => {
        throw new Error('first')
      })
    })
    expect(result.current.error).not.toBeNull()
    let value: number | undefined
    await act(async () => {
      value = await result.current.call(async () => 7)
    })
    expect(result.current.error).toBeNull()
    expect(value).toBe(7)
  })

  it('clearOnCall=false preserves error across calls', async () => {
    const { result } = renderHook(
      () => useApi({ tag: 'x', clearOnCall: false }),
      { wrapper: WithApp },
    )
    await act(async () => {
      await result.current.call(async () => {
        throw new Error('first')
      })
    })
    const previous = result.current.error
    expect(previous).not.toBeNull()
    await act(async () => {
      await result.current.call(async () => 7)
    })
    // Previous error is preserved (clearOnCall=false)
    expect(result.current.error).toBe(previous)
  })
})
