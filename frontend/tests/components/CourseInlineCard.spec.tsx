import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import CourseInlineCard from '@/components/CourseInlineCard'
import type { Course } from '@/types'

// CourseInlineCard 是 v2 推荐流的精简课程卡（流式输出用，无 Card 包装）；
// 与 components/recommend/CourseCard 视觉相似但用途不同：流式（每 token 重渲染）vs 静态。

const baseCourse: Course = {
  course_id: 'c1',
  course_name: '人工智能导论',
  teacher: '张老师',
  credits: 3,
  course_type: '公选',
  course_category: '信息技术',
  domain: '人工智能',
  campus: '龙洞',
  time_slot: '周三 5-6 节',
  location: 'B201',
  capacity: 100,
  current_enrolled: 80,
  current_enrollment_ratio: 0.8,
  popularity_level: 1,
  rush_advice: '',
  description: '',
  assessment: '',
  difficulty: '中',
  workload: '中等',
  grade_friendly: '给分友好',
  has_exam: 0,
  group_work_required: 0,
  suitable_for: '',
  tags: [],
  score: 4.8,
  match_reasons: ['热门课程', 'AI 相关'],
}

describe('CourseInlineCard', () => {
  describe('基础渲染', () => {
    it('renders course name, teacher, credits, and match score', () => {
      render(<CourseInlineCard course={baseCourse} index={0} />)
      expect(screen.getByText('人工智能导论')).toBeTruthy()
      expect(screen.getByText('张老师')).toBeTruthy()
      expect(screen.getByText('3学分')).toBeTruthy()
      expect(screen.getByText('4.8')).toBeTruthy()
    })

    it('omits teacher row entirely when teacher is empty (different from CourseCard which shows "待定")', () => {
      render(<CourseInlineCard course={{ ...baseCourse, teacher: '' }} index={0} />)
      // CourseInlineCard 是流式精简版：teacher 为空时不渲染整行（无"待定" fallback，与 CourseCard 不同）
      expect(screen.queryByText(/张老师/)).toBeNull()
      expect(screen.queryByText('待定')).toBeNull()
    })

    it('renders match_reasons chips (capped at 3) — CourseInlineCard 故意不展示 match_reasons（流式场景每 token 重渲染）', () => {
      // 注意：CourseInlineCard 与 recommend/CourseCard 关键差异 — 不显示 match_reasons
      const courseWith5Reasons = {
        ...baseCourse,
        match_reasons: ['热门', 'AI', '好给分', '轻松', '人少'],
      }
      render(<CourseInlineCard course={courseWith5Reasons} index={0} />)
      expect(screen.queryByText('热门')).toBeNull()
      expect(screen.queryByText('AI')).toBeNull()
    })

    it('shows "无考试" tag when has_exam is 0', () => {
      render(<CourseInlineCard course={baseCourse} index={0} />)
      const tag = screen.getByLabelText('无考试')
      expect(tag).toBeTruthy()
      expect(tag.textContent).toBe('无考试')
    })

    it('shows "有考试" tag when has_exam is 1', () => {
      render(<CourseInlineCard course={{ ...baseCourse, has_exam: 1 }} index={0} />)
      const tag = screen.getByLabelText('有考试')
      expect(tag).toBeTruthy()
      expect(tag.textContent).toBe('有考试')
    })
  })

  describe('popularity tag', () => {
    it('shows "热门" when popularity_level is 3', () => {
      render(<CourseInlineCard course={{ ...baseCourse, popularity_level: 3 }} index={0} />)
      expect(screen.getByLabelText('热门')).toBeTruthy()
    })

    it('shows "爆满" when popularity_level >= 4', () => {
      render(<CourseInlineCard course={{ ...baseCourse, popularity_level: 5 }} index={0} />)
      expect(screen.getByLabelText('爆满')).toBeTruthy()
    })

    it('does not show popularity tag when popularity_level < 3', () => {
      render(<CourseInlineCard course={baseCourse} index={0} />)
      expect(screen.queryByLabelText('热门')).toBeNull()
      expect(screen.queryByLabelText('爆满')).toBeNull()
    })
  })

  describe('路 1 a11y 升级（漏掉，本轮补齐）', () => {
    it('exposes course info to screen readers via aria-label on a group landmark', () => {
      render(<CourseInlineCard course={baseCourse} index={2} />)
      const group = screen.getByRole('group', {
        name: '第 3 门课程：人工智能导论，张老师，3 学分',
      })
      expect(group).toBeTruthy()
    })

    it('decorative icons are aria-hidden (TeamOutlined / BookOutlined / etc.)', () => {
      // 验证装饰图标带 aria-hidden="true"，屏幕阅读器跳过
      const { container } = render(<CourseInlineCard course={baseCourse} index={0} />)
      const hiddenSpans = container.querySelectorAll('span[aria-hidden="true"]')
      // 至少包含：序号圆形 + StarOutlined + TeamOutlined + BookOutlined + EnvironmentOutlined + FieldTimeOutlined
      expect(hiddenSpans.length).toBeGreaterThanOrEqual(5)
    })

    it('aria-label index reflects the actual course position (0-indexed → "第 N+1 门")', () => {
      render(<CourseInlineCard course={baseCourse} index={0} />)
      expect(
        screen.getByRole('group', { name: /第 1 门课程/ }),
      ).toBeTruthy()

      const { rerender } = render(<CourseInlineCard course={baseCourse} index={4} />)
      expect(
        screen.getByRole('group', { name: /第 5 门课程/ }),
      ).toBeTruthy()
      rerender(<div />)
    })
  })
})
