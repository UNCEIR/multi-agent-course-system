/**
 * safeCall：把任意 API 调用错误归一化为 ApiError。
 *
 * 用法：
 *   const data = await safeCall(() => api.chat(body), { tag: 'chat:send' })
 *
 * 后端错误格式 { detail: "..." } → ApiError；其他异常 → ApiError(UNKNOWN)
 */

export interface ApiErrorPayload {
  /** 错误代号：后端 'detail' 字段或前端推导的 'UNKNOWN'/'NETWORK'/'ABORTED' */
  code: string
  /** 给用户看的中文/英文错误信息 */
  message: string
  /** 原始 Error 对象（如有），便于上层记录堆栈 */
  original?: unknown
  /** 业务标签，用于日志聚合 / 错误归类（如 'chat:send' / 'report:upload'） */
  tag?: string
}

export class ApiError extends Error {
  readonly code: string
  readonly original?: unknown
  readonly tag?: string

  constructor(payload: ApiErrorPayload) {
    super(payload.message)
    this.name = 'ApiError'
    this.code = payload.code
    this.original = payload.original
    this.tag = payload.tag
  }

  /** 把任意 unknown 错误归一化为 ApiError。 */
  static from(err: unknown, fallbackMessage = '请求失败', tag?: string): ApiError {
    if (err instanceof ApiError) {
      if (!tag) return err
      // 显式列出字段：spread ApiError 实例不会复制 Error.message（继承自 Error.prototype）
      return new ApiError({
        code: err.code,
        message: err.message,
        original: err.original,
        tag,
      })
    }
    // 识别 abort：不依赖 instanceof Error（vitest/jsdom DOMException 不一定继承 Error）
    const looksLikeAbort =
      err instanceof DOMException
        ? err.name === 'AbortError'
        : typeof err === 'object' && err !== null && 'name' in err && (err as { name?: unknown }).name === 'AbortError'
    if (looksLikeAbort) {
      const original = err instanceof Error ? err : undefined
      return new ApiError({
        code: 'ABORTED',
        message: '请求已取消',
        original,
        tag,
      })
    }
    if (err instanceof Error) {
      return new ApiError({
        code: 'NETWORK',
        message: err.message || fallbackMessage,
        original: err,
        tag,
      })
    }
    return new ApiError({
      code: 'UNKNOWN',
      message: fallbackMessage,
      original: err,
      tag,
    })
  }
}

/**
 * 解析后端错误响应 { detail: string } → ApiError。
 * 兼容 FastAPI 422 / 404 / 500 等结构化错误。
 */
export function parseHttpError(status: number, body: unknown): ApiError {
  let code = `HTTP_${status}`
  let message = `请求失败（${status}）`
  if (body && typeof body === 'object') {
    const b = body as Record<string, unknown>
    if (typeof b.detail === 'string') {
      message = b.detail
      code = (b.code as string) || code
    } else if (b.detail && typeof b.detail === 'object') {
      // FastAPI 422 校验错误：{ detail: [{type, loc, msg, ...}, ...] }
      const items = (b.detail as unknown[]) || []
      if (Array.isArray(items) && items.length > 0) {
        const first = items[0] as Record<string, unknown>
        const msg = (first.msg as string) || message
        const loc = Array.isArray(first.loc) ? (first.loc as unknown[]).join('.') : ''
        message = loc ? `${loc}: ${msg}` : msg
        code = 'VALIDATION_ERROR'
      }
    }
  }
  return new ApiError({ code, message })
}

/**
 * safeCall 包装器：捕获异常并归一化为 ApiError 抛出。
 *
 * @param fn 业务调用
 * @param options.tag 业务标签（用于日志/分类）
 * @param options.fallbackMessage 兜底错误信息
 * @param options.onError 额外错误回调（如埋点 / 静默吞错场景）
 */
export async function safeCall<T>(
  fn: () => Promise<T>,
  options: {
    tag?: string
    fallbackMessage?: string
    onError?: (err: ApiError) => void
  } = {},
): Promise<T> {
  try {
    return await fn()
  } catch (err) {
    const apiErr = ApiError.from(err, options.fallbackMessage, options.tag)
    options.onError?.(apiErr)
    throw apiErr
  }
}
