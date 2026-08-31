'use client'

/**
 * useNotify：统一 toast + inline 两套错误反馈（路 3）。
 *
 * 设计动机：前端之前 3 套反馈（message.error / inline Text danger / StreamView 红 panel）
 * 风格不一、缺统一出口。用本 hook 收敛为 2 种：
 *   - toast（短暂浮层通知，适合"操作失败请重试"）
 *   - inline（页面内联错误展示，适合"需要保留上下文重试"）
 *
 * 调用方按场景选择：
 *   - 短操作（提交/删除）：notify.toast.error(err)
 *   - 长操作（上传/流式生成）：notify.inline.set(err) + UI render notify.inline.message
 */

import { useCallback, useMemo, useState } from 'react'
import { App } from 'antd'
import type { MessageInstance } from 'antd/es/message/interface'

import { ApiError } from './safeCall'

interface NotifyHandle {
  toast: {
    success: (msg: string) => void
    error: (err: unknown, fallback?: string) => void
    info: (msg: string) => void
    warning: (msg: string) => void
  }
  inline: {
    error: ApiError | null
    set: (err: unknown, fallback?: string) => void
    clear: () => void
    /** 给 UI 用的标准化错误文案（优先 err.message） */
    message: string | null
  }
}

export function useNotify(): NotifyHandle {
  // antd App context 提供 message 实例（避免静态 message.warning 警告）
  const { message } = App.useApp()
  const [inlineError, setInlineError] = useState<ApiError | null>(null)

  const set = useCallback((err: unknown, fallback = '操作失败，请稍后重试') => {
    const apiErr = ApiError.from(err, fallback)
    setInlineError(apiErr)
  }, [])

  const clear = useCallback(() => setInlineError(null), [])

  const error = useCallback(
    (err: unknown, fallback = '操作失败，请稍后重试') => {
      const apiErr = ApiError.from(err, fallback)
      messageApiError(message, apiErr)
    },
    [message],
  )

  const success = useCallback(
    (msg: string) => {
      message.success(msg)
    },
    [message],
  )

  const info = useCallback(
    (msg: string) => {
      message.info(msg)
    },
    [message],
  )

  const warning = useCallback(
    (msg: string) => {
      message.warning(msg)
    },
    [message],
  )

  return useMemo(
    () => ({
      toast: { success, error, info, warning },
      inline: {
        error: inlineError,
        set,
        clear,
        message: inlineError?.message ?? null,
      },
    }),
    [success, error, info, warning, set, clear, inlineError],
  )
}

/** 把 ApiError 渲染为 antd message.error；保留 Aborted 静默（用户主动取消不报错）。 */
function messageApiError(msg: MessageInstance, err: ApiError) {
  if (err.code === 'ABORTED') return
  msg.error({
    content: err.message,
    duration: 4,
  })
}
