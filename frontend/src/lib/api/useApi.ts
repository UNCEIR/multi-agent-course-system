'use client'

/**
 * useApi：基于 useNotify 的统一 API 调用 hook（路 3）。
 *
 * 设计动机：替换之前散落在每个 page 的 try/catch + .catch(() => {}) + message.error 模式。
 * 三套散落的错误反馈收敛到 useNotify.toast.error / useNotify.inline.set 两路。
 *
 * 用法：
 *   const api = useApi({ tag: 'chat:send' })
 *   const data = await api.call(() => apiModule.listSessions(userId))
 *   // api.error 自动 setInlineError；api.toast 触发 toast 通知
 */

import { useCallback, useMemo, useState } from 'react'

import { ApiError, safeCall } from './safeCall'
import { useNotify } from './useNotify'

interface UseApiOptions {
  /** 业务标签（用于日志 / 错误归类） */
  tag?: string
  /** 默认错误兜底文案 */
  fallbackMessage?: string
  /** inline 错误是否在每次新调用前自动清空（默认 true） */
  clearOnCall?: boolean
}

export interface UseApiReturn {
  /** 包了 safeCall 的统一调用入口；inline error 自动上报 */
  call: <T>(fn: () => Promise<T>) => Promise<T | undefined>
  /** 当前 inline 错误（受 useNotify.inline 同步） */
  error: ApiError | null
  /** 手动清空 inline 错误 */
  clearError: () => void
  /** 是否正在 loading（call 调用期间为 true） */
  loading: boolean
  /** toast 通知快捷方式（success/error/warning/info） */
  toast: ReturnType<typeof useNotify>['toast']
  /** inline 错误反馈快捷方式（与 toast 共享同一份 notify 实例） */
  inline: ReturnType<typeof useNotify>['inline']
}

export function useApi(options: UseApiOptions = {}): UseApiReturn {
  const { tag, fallbackMessage = '请求失败，请稍后重试', clearOnCall = true } = options
  const notify = useNotify()
  const [loading, setLoading] = useState(false)

  const clearError = useCallback(() => {
    notify.inline.clear()
  }, [notify])

  const call = useCallback(
    async <T>(fn: () => Promise<T>): Promise<T | undefined> => {
      if (clearOnCall) notify.inline.clear()
      setLoading(true)
      try {
        return await safeCall(fn, {
          tag,
          fallbackMessage,
          onError: (apiErr) => notify.inline.set(apiErr),
        })
      } catch {
        // 已经被 safeCall 归一化并通过 onError 上报 inline；此处只吞错避免 unhandledrejection
        return undefined
      } finally {
        setLoading(false)
      }
    },
    [tag, fallbackMessage, clearOnCall, notify],
  )

  return useMemo(
    () => ({
      call,
      error: notify.inline.error,
      clearError,
      loading,
      toast: notify.toast,
      inline: notify.inline,
    }),
    [call, notify, clearError, loading],
  )
}
