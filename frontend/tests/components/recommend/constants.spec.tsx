import { describe, expect, it } from 'vitest'
import { PRESET_QUERIES, PHASE_MAP, DIFFICULTY_COLORS, PRESET_ICON_MAP } from '@/components/recommend/constants'

describe('recommend/constants', () => {
  it('exports 5 preset queries covering distinct student personas', () => {
    expect(PRESET_QUERIES).toHaveLength(5)
    // 每个 preset id 唯一
    const ids = PRESET_QUERIES.map((p) => p.id)
    expect(new Set(ids).size).toBe(ids.length)
    // 五个常见学生画像都覆盖
    expect(ids).toEqual(expect.arrayContaining(['cs', 'art', 'finance', 'senior', 'sport']))
  })

  it('preset prompts are non-empty Chinese strings (>20 chars)', () => {
    for (const p of PRESET_QUERIES) {
      expect(typeof p.prompt).toBe('string')
      expect(p.prompt.length).toBeGreaterThan(20)
    }
  })

  it('preset icon strings all map to PRESET_ICON_MAP entries', () => {
    for (const p of PRESET_QUERIES) {
      expect(PRESET_ICON_MAP[p.icon]).toBeDefined()
    }
  })

  it('PHASE_MAP covers all 5 agent keys returned by backend', () => {
    const keys = ['student_profile', 'course_recall', 'course_rerank', 'course_feasibility', 'recommendation_reason']
    for (const k of keys) {
      expect(PHASE_MAP[k]).toBeDefined()
      expect(PHASE_MAP[k].label).toBeTruthy()
      expect(typeof PHASE_MAP[k].phase).toBe('number')
    }
  })

  it('DIFFICULTY_COLORS maps both Chinese (高/中/低) and English (hard/medium/easy) keys', () => {
    expect(DIFFICULTY_COLORS['高']).toBeDefined()
    expect(DIFFICULTY_COLORS['中']).toBeDefined()
    expect(DIFFICULTY_COLORS['低']).toBeDefined()
    expect(DIFFICULTY_COLORS.hard).toBeDefined()
    expect(DIFFICULTY_COLORS.medium).toBeDefined()
    expect(DIFFICULTY_COLORS.easy).toBeDefined()
  })
})
