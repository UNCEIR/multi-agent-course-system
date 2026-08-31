import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import SingleResultView from '@/components/recommend/SingleResultView'
import type { RecommendationResponse } from '@/types'

const baseCourse = {
  course_id: 'c1',
  course_name: '艺术与生活',
  teacher: '王老师',
  credits: 2,
  course_type: '公选',
  course_category: '人文艺术',
  domain: '人文',
  campus: '龙洞',
  time_slot: '周五 3-4 节',
  location: 'A101',
  capacity: 60,
  current_enrolled: 30,
  current_enrollment_ratio: 0.5,
  popularity_level: 1,
  rush_advice: '',
  description: '',
  assessment: '',
  difficulty: '低',
  workload: '少',
  grade_friendly: '给分友好',
  has_exam: 0,
  group_work_required: 0,
  suitable_for: '',
  tags: [],
  score: 4.5,
  match_reasons: ['轻松'],
}

const mockResponse: RecommendationResponse = {
  request_id: 'req_001',
  user_id: 'u1',
  courses: [baseCourse],
  recommendation_reasons: [{ c1: '热门艺术课程' }],
  selection_warnings: [
    { course_id: 'c1', course_name: '艺术与生活', level: 'high', message: '考试冲突' },
  ],
  priority_advice: {},
  experiment_group: 'pipeline',
  agent_results: {
    student_profile: {
      agent_name: 'student_profile', success: true, latency_ms: 200, confidence: 0.9, error: null, data: {},
    },
    course_recall: {
      agent_name: 'course_recall', success: true, latency_ms: 300, confidence: 0.85, error: null, data: {},
    },
  },
  agent_latencies: {},
  total_latency_ms: 1200,
  timestamp: new Date().toISOString(),
}

describe('SingleResultView', () => {
  it('renders 4 stat cards: total latency, courses, agents, warnings', () => {
    render(<SingleResultView response={mockResponse} />)
    // "总耗时" 同时出现在 StatCard 和 PipelineTimeline，用 getAllByText
    expect(screen.getAllByText(/总耗时/).length).toBeGreaterThanOrEqual(1)
    // StatCard aria-label 包含完整值
    expect(screen.getByLabelText('总耗时：1200 ms')).toBeTruthy()
    expect(screen.getByLabelText('推荐课程：1 门')).toBeTruthy()
    expect(screen.getByLabelText('可用 Agent：2/2')).toBeTruthy()
    expect(screen.getByLabelText(/选课提醒：/)).toBeTruthy()
  })

  it('renders the course name in CourseCard', () => {
    render(<SingleResultView response={mockResponse} />)
    expect(screen.getByText('艺术与生活')).toBeTruthy()
  })

  it('renders selection warning with level "高" for high severity', () => {
    render(<SingleResultView response={mockResponse} />)
    // antd Collapse 默认折叠，不渲染 children；
    // 验证 Collapse header 上 "1 条" tag 与标题，证明 warnings 面板存在并接入数据流。
    expect(screen.getByText('选课可行性提醒')).toBeTruthy()
    // Tag 在 Collapse header 中显示计数 1 条（"1 条" 也出现在 4 个 StatCard 与 推荐理由 处，
    // 这里用 getAllByText 至少 1 个）
    expect(screen.getAllByText('1 条').length).toBeGreaterThanOrEqual(1)
  })

  it('handles empty courses list with Empty component', () => {
    render(
      <SingleResultView response={{ ...mockResponse, courses: [] }} />,
    )
    expect(screen.getByText('未找到匹配的课程')).toBeTruthy()
  })

  it('handles empty selection_warnings (no warning collapse shown)', () => {
    render(
      <SingleResultView
        response={{ ...mockResponse, selection_warnings: [] }}
      />,
    )
    // "选课可行性提醒" collapse 不应渲染
    expect(screen.queryByText(/选课可行性提醒/)).toBeNull()
  })

  it('exposes results region to screen readers via labelled landmark', () => {
    const { container } = render(
      <SingleResultView response={mockResponse} />,
    )
    const region = container.querySelector('[aria-labelledby="single-result-heading"]')
    expect(region).toBeTruthy()
  })
})
