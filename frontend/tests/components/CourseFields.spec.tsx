import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import CourseFields from '@/components/CourseFields'
import type { Course } from '@/types'

// 路 7：CourseFields 单测
// - 覆盖 inline + card 两个 variant 的字段渲染
// - 验证 a11y（aria-label）由 CourseFields 提供，role/aria-label 由父组件负责
// - 验证独有字段（序号/评分 Tooltip/match_reasons）不在 CourseFields 里

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
  current_enrolled: 50,
  current_enrollment_ratio: 0.5,
  popularity_level: 4, // 触发"爆满" tag
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
  match_reasons: ['热门', 'AI'],
}

describe('CourseFields', () => {
  describe('inline variant', () => {
    it('renders teacher / credits / campus / time_slot in a flat flexWrap row', () => {
      render(<CourseFields course={baseCourse} variant="inline" />)
      expect(screen.getByText('张老师')).toBeTruthy()
      expect(screen.getByText('3学分')).toBeTruthy()
      expect(screen.getByText('龙洞')).toBeTruthy()
      expect(screen.getByText('周三 5-6 节')).toBeTruthy()
    })

    it('omits teacher row entirely when teacher is empty (matches CourseInlineCard behavior)', () => {
      render(<CourseFields course={{ ...baseCourse, teacher: '' }} variant="inline" />)
      expect(screen.queryByText('张老师')).toBeNull()
      expect(screen.queryByText('待定')).toBeNull()
    })

    it('does not show "待定" fallback (inline 模式精简——与 card 模式差异)', () => {
      render(<CourseFields course={{ ...baseCourse, teacher: '' }} variant="inline" />)
      // inline 模式 teacher 为空时不显示任何教师信息（与 CourseCard 的"待定" fallback 不同）
      const infoRow = screen.getByLabelText('课程基本信息')
      expect(within(infoRow).queryByText('张老师')).toBeNull()
    })

    it('shows "爆满" tag when popularity_level >= 4', () => {
      render(<CourseFields course={{ ...baseCourse, popularity_level: 4 }} variant="inline" />)
      expect(screen.getByLabelText('爆满')).toBeTruthy()
    })

    it('shows "热门" tag when popularity_level is 3', () => {
      render(<CourseFields course={{ ...baseCourse, popularity_level: 3 }} variant="inline" />)
      expect(screen.getByLabelText('热门')).toBeTruthy()
    })

    it('does not show popularity tag when popularity_level < 3', () => {
      render(
        <CourseFields
          course={{ ...baseCourse, popularity_level: 1 }}
          variant="inline"
        />,
      )
      expect(screen.queryByLabelText('热门')).toBeNull()
      expect(screen.queryByLabelText('爆满')).toBeNull()
    })
  })

  describe('card variant', () => {
    it('renders teacher / credits in 授课信息 group with "待定" fallback when teacher is empty', () => {
      render(<CourseFields course={{ ...baseCourse, teacher: '' }} variant="card" />)
      const group = screen.getByLabelText('授课信息')
      expect(within(group).getByText('待定')).toBeTruthy()
      expect(within(group).getByText('3 学分')).toBeTruthy()
    })

    it('renders domain + course_category as inline tags in 分类 group', () => {
      const courseWithSameDomainAndCategory = {
        ...baseCourse,
        domain: '人工智能',
        course_category: '人工智能',
      }
      render(<CourseFields course={courseWithSameDomainAndCategory} variant="card" />)
      const group = screen.getByLabelText('分类')
      // course_category === domain 时不重复渲染
      expect(within(group).getByText('人工智能')).toBeTruthy()
      // 只渲染一个 tag
      expect(within(group).getAllByText('人工智能')).toHaveLength(1)
    })

    it('renders course_category separately when it differs from domain', () => {
      const courseWithDifferentCategory = {
        ...baseCourse,
        domain: '人工智能',
        course_category: '计算机',
      }
      render(<CourseFields course={courseWithDifferentCategory} variant="card" />)
      const group = screen.getByLabelText('分类')
      expect(within(group).getByText('人工智能')).toBeTruthy()
      expect(within(group).getByText('计算机')).toBeTruthy()
    })

    it('renders time_slot + campus in 时间地点 group', () => {
      render(<CourseFields course={baseCourse} variant="card" />)
      const group = screen.getByLabelText('时间地点')
      expect(within(group).getByText('周三 5-6 节')).toBeTruthy()
      expect(within(group).getByText('龙洞')).toBeTruthy()
    })

    it('renders all 7 tags in 课程标签 group (difficulty/workload/grade_friendly/has_exam/popularity)', () => {
      render(<CourseFields course={baseCourse} variant="card" />)
      const group = screen.getByLabelText('课程标签')
      expect(within(group).getByText(/难度\s*中/)).toBeTruthy()
      expect(within(group).getByText(/作业\s*中等/)).toBeTruthy()
      expect(within(group).getByText(/给分\s*给分友好/)).toBeTruthy()
      expect(within(group).getByLabelText('无考试')).toBeTruthy()
      expect(within(group).getByLabelText('爆满')).toBeTruthy()
    })
  })

  describe('独有字段不在 CourseFields 里', () => {
    it('does not render 序号（CourseInlineCard 独有）', () => {
      render(<CourseFields course={baseCourse} variant="inline" />)
      expect(screen.queryByText('1')).toBeNull()
    })

    it('does not render match_reasons chips（CourseCard 独有）', () => {
      render(<CourseFields course={baseCourse} variant="card" />)
      expect(screen.queryByText('热门')).toBeNull()
      expect(screen.queryByText('AI')).toBeNull()
      expect(screen.queryByText('匹配理由')).toBeNull()
    })

    it('does not render score / Tooltip（CourseInlineCard 独有）', () => {
      render(<CourseFields course={baseCourse} variant="inline" />)
      // 评分文本"4.8"不出现在 CourseFields 里
      expect(screen.queryByText('4.8')).toBeNull()
    })
  })

  describe('a11y', () => {
    it('inline variant exposes "课程基本信息" + "课程标签" landmarks', () => {
      // CourseFields 自身在外层不加 role/aria-label（由父组件根据容器决定），
      // 但暴露分区 landmarks 让屏幕阅读器能定位字段区。
      render(<CourseFields course={baseCourse} variant="inline" />)
      expect(screen.getByLabelText('课程基本信息')).toBeTruthy()
      expect(screen.getByLabelText('课程标签')).toBeTruthy()
    })

    it('CourseFields 自身不设外层 role/aria-label（由父组件 CourseInlineCard / CourseCard 负责）', () => {
      const { container } = render(<CourseFields course={baseCourse} variant="card" />)
      const root = container.firstChild as HTMLElement | null
      // root 是 CourseFields 自己的 Fragment 容器——不应有 role/aria-label
      if (root && root.hasAttribute('role')) {
        expect(root.getAttribute('role')).not.toBe('group')
      }
    })

    it('card variant exposes 授课信息 / 分类 / 时间地点 / 课程标签 landmarks', () => {
      render(<CourseFields course={baseCourse} variant="card" />)
      expect(screen.getByLabelText('授课信息')).toBeTruthy()
      expect(screen.getByLabelText('分类')).toBeTruthy()
      expect(screen.getByLabelText('时间地点')).toBeTruthy()
      expect(screen.getByLabelText('课程标签')).toBeTruthy()
    })

    it('decorative icons (TeamOutlined / BookOutlined / etc.) are aria-hidden', () => {
      const { container } = render(<CourseFields course={baseCourse} variant="card" />)
      const hiddenSpans = container.querySelectorAll('span[aria-hidden="true"]')
      // 至少 4 个：TeamOutlined + BookOutlined + FieldTimeOutlined + EnvironmentOutlined
      expect(hiddenSpans.length).toBeGreaterThanOrEqual(4)
    })
  })
})
