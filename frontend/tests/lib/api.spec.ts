import { describe, expect, it } from 'vitest'
import { unwrapEnvelope } from '@/lib/api'

describe('unwrapEnvelope', () => {
  it('unwraps BaseResult envelope and returns data', () => {
    const body = { code: 200, success: true, data: { count: 1, datasets: [] }, msg: '操作成功' }
    expect(unwrapEnvelope<{ count: number }>(body)).toEqual({ count: 1, datasets: [] })
  })

  it('returns non-envelope body as-is', () => {
    const raw = { status: 'ok', model: 'qwen' }
    expect(unwrapEnvelope(raw)).toEqual(raw)
  })

  it('returns null for failed envelope with null data', () => {
    const body = { code: 403, success: false, data: null, msg: '无权查看' }
    expect(unwrapEnvelope<null>(body)).toBeNull()
  })

  it('passes through primitive payloads', () => {
    expect(unwrapEnvelope(42)).toBe(42)
    expect(unwrapEnvelope(null)).toBeNull()
  })
})
