import { describe, expect, it } from 'vitest'
import { getWarningLevel, WARNING_LEVEL_STYLES, DEFAULT_WARNING_LEVEL } from '@/lib/warningLevel'

describe('warningLevel', () => {
  it('returns known level styles for canonical values', () => {
    expect(getWarningLevel('high')).toEqual({
      color: '#C0392B', bg: '#FDECEC', label: '高',
    })
    expect(getWarningLevel('medium')).toEqual({
      color: '#B9772E', bg: '#fef3c7', label: '中',
    })
    expect(getWarningLevel('low')).toEqual({
      color: '#6B7A8D', bg: '#EAF2FB', label: '低',
    })
  })

  it('falls back to DEFAULT_WARNING_LEVEL for unknown string values', () => {
    // 防御性：后端未来引入新等级（如 critical）不应让 UI 崩
    expect(getWarningLevel('critical')).toEqual(DEFAULT_WARNING_LEVEL)
    expect(getWarningLevel('')).toEqual(DEFAULT_WARNING_LEVEL)
  })

  it('falls back to DEFAULT_WARNING_LEVEL for non-string inputs', () => {
    expect(getWarningLevel(undefined)).toEqual(DEFAULT_WARNING_LEVEL)
    expect(getWarningLevel(null)).toEqual(DEFAULT_WARNING_LEVEL)
    expect(getWarningLevel(123)).toEqual(DEFAULT_WARNING_LEVEL)
    expect(getWarningLevel({})).toEqual(DEFAULT_WARNING_LEVEL)
  })

  it('exports a complete styles table for all three canonical levels', () => {
    expect(WARNING_LEVEL_STYLES.high).toBeDefined()
    expect(WARNING_LEVEL_STYLES.medium).toBeDefined()
    expect(WARNING_LEVEL_STYLES.low).toBeDefined()
    expect(Object.keys(WARNING_LEVEL_STYLES)).toHaveLength(3)
  })
})
