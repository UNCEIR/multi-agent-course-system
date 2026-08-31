import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import CourseCard from '@/components/recommend/CourseCard'
import type { Course } from '@/types'

const mockCourse: Course = {
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
  popularity_level: 2,
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

describe('CourseCard', () => {
  it('renders course name, teacher, credits, and match score', () => {
    render(<CourseCard course={mockCourse} />)
    expect(screen.getByText('人工智能导论')).toBeTruthy()
    expect(screen.getByText('张老师')).toBeTruthy()
    expect(screen.getByText('3 学分')).toBeTruthy()
    expect(screen.getByText('4.8')).toBeTruthy()
  })

  it('shows "无考试" tag when has_exam is 0', () => {
    render(<CourseCard course={mockCourse} />)
    expect(screen.getByText('无考试')).toBeTruthy()
  })

  it('shows "有考试" tag when has_exam is 1', () => {
    render(<CourseCard course={{ ...mockCourse, has_exam: 1 }} />)
    expect(screen.getByText('有考试')).toBeTruthy()
  })

  it('falls back to "待定" when teacher is empty', () => {
    render(<CourseCard course={{ ...mockCourse, teacher: '' }} />)
    expect(screen.getByText('待定')).toBeTruthy()
  })

  it('exposes course info to screen readers via aria-label', () => {
    render(<CourseCard course={mockCourse} index={0} />)
    const card = screen.getByLabelText(/第 1 门课程/)
    expect(card).toBeTruthy()
  })

  it('renders match_reasons chips (capped at 3)', () => {
    const courseWith5Reasons = {
      ...mockCourse,
      match_reasons: ['热门', 'AI', '好给分', '轻松', '人少'],
    }
    render(<CourseCard course={courseWith5Reasons} />)
    // 至少展示前 3 个
    expect(screen.getByText('热门')).toBeTruthy()
    expect(screen.getByText('AI')).toBeTruthy()
    expect(screen.getByText('好给分')).toBeTruthy()
  })

  it('shows "热门" tag when popularity_level is 3 (行为对齐 CourseInlineCard)', () => {
    render(<CourseCard course={{ ...mockCourse, popularity_level: 3 }} />)
    expect(screen.getByLabelText('热门')).toBeTruthy()
  })

  it('shows "爆满" tag when popularity_level is 4 (行为对齐 CourseInlineCard)', () => {
    render(<CourseCard course={{ ...mockCourse, popularity_level: 4 }} />)
    expect(screen.getByLabelText('爆满')).toBeTruthy()
  })

  it('does not show popularity tag when popularity_level < 3', () => {
    render(<CourseCard course={{ ...mockCourse, popularity_level: 2 }} />)
    expect(screen.queryByLabelText('热门')).toBeNull()
    expect(screen.queryByLabelText('爆满')).toBeNull()
  })
})
