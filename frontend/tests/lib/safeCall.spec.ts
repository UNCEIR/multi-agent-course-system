import { describe, expect, it, vi } from 'vitest'
import { ApiError, safeCall, parseHttpError } from '@/lib/api/safeCall'

describe('ApiError', () => {
  it('preserves code/message/original', () => {
    const original = new Error('boom')
    const err = new ApiError({ code: 'BOOM', message: '失败', original })
    expect(err).toBeInstanceOf(Error)
    expect(err.code).toBe('BOOM')
    expect(err.message).toBe('失败')
    expect(err.original).toBe(original)
    expect(err.name).toBe('ApiError')
  })

  it('ApiError.from normalizes Error instances', () => {
    const original = new TypeError('network unreachable')
    const err = ApiError.from(original, '兜底', 'test:tag')
    expect(err.code).toBe('NETWORK')
    expect(err.message).toBe('network unreachable')
    expect(err.tag).toBe('test:tag')
    expect(err.original).toBe(original)
  })

  it('ApiError.from maps AbortError to ABORTED', () => {
    const original = new DOMException('Aborted', 'AbortError')
    const err = ApiError.from(original)
    expect(err.code).toBe('ABORTED')
    expect(err.message).toBe('请求已取消')
  })

  it('ApiError.from maps non-Error values to UNKNOWN with fallback', () => {
    const err = ApiError.from({ weird: 'shape' }, '业务自定义错误')
    expect(err.code).toBe('UNKNOWN')
    expect(err.message).toBe('业务自定义错误')
  })

  it('ApiError.from re-tags existing ApiError', () => {
    const original = new ApiError({ code: 'X', message: '原', tag: 'old' })
    const retagged = ApiError.from(original, undefined, 'new')
    expect(retagged.code).toBe('X')
    expect(retagged.message).toBe('原')
    expect(retagged.tag).toBe('new')
  })
})

describe('parseHttpError', () => {
  it('extracts FastAPI string detail', () => {
    const err = parseHttpError(404, { detail: '资源不存在' })
    expect(err.code).toBe('HTTP_404')
    expect(err.message).toBe('资源不存在')
  })

  it('extracts FastAPI 422 validation array detail', () => {
    const err = parseHttpError(422, {
      detail: [{ type: 'value_error', loc: ['body', 'user_id'], msg: '字段必填' }],
    })
    expect(err.code).toBe('VALIDATION_ERROR')
    expect(err.message).toBe('body.user_id: 字段必填')
  })

  it('falls back to generic message for unknown body shape', () => {
    const err = parseHttpError(500, { weird: 'object' })
    expect(err.code).toBe('HTTP_500')
    expect(err.message).toBe('请求失败（500）')
  })

  it('handles null body gracefully', () => {
    const err = parseHttpError(502, null)
    expect(err.code).toBe('HTTP_502')
    expect(err.message).toBe('请求失败（502）')
  })
})

describe('safeCall', () => {
  it('returns the resolved value on success', async () => {
    const result = await safeCall(async () => 42, { tag: 'ok' })
    expect(result).toBe(42)
  })

  it('wraps thrown error into ApiError and calls onError', async () => {
    const onError = vi.fn()
    await expect(
      safeCall(
        async () => {
          throw new Error('boom')
        },
        { tag: 'safeCall:test', fallbackMessage: 'fallback', onError },
      ),
    ).rejects.toMatchObject({
      code: 'NETWORK',
      message: 'boom',
      tag: 'safeCall:test',
    })
    expect(onError).toHaveBeenCalledTimes(1)
  })

  it('uses fallback message when error has no message', async () => {
    await expect(
      safeCall(
        async () => {
          throw new Error('')
        },
        { fallbackMessage: '业务兜底' },
      ),
    ).rejects.toMatchObject({
      code: 'NETWORK',
      message: '业务兜底',
    })
  })
})
