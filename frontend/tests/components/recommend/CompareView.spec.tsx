import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import CompareView from '@/components/recommend/CompareView'
import type { RecommendationResponse } from '@/types'

const baseCourse = {
  course_id: 'c1',
  course_name: 'AI 入门',
  teacher: '李老师',
  credits: 2,
  course_type: '公选',
  course_category: '信息技术',
  domain: '人工智能',
  campus: '龙洞',
  time_slot: '周二 5-6 节',
  location: 'B201',
  capacity: 100,
  current_enrolled: 50,
  current_enrollment_ratio: 0.5,
  popularity_level: 1,
  rush_advice: '',
  description: '',
  assessment: '',
  difficulty: '中',
  workload: '中',
  grade_friendly: '好',
  has_exam: 0,
  group_work_required: 0,
  suitable_for: '',
  tags: [],
  score: 4.5,
  match_reasons: [],
}

const fastJob = {
  id: 'cs_1',
  label: '计算机爱好者',
  prompt: '我想选编程课',
  error: null,
  response: {
    request_id: 'req_001',
    user_id: 'u1',
    courses: [baseCourse],
    recommendation_reasons: [],
    selection_warnings: [{ course_id: 'c1', level: 'medium', message: '中等风险' }],
    priority_advice: {},
    experiment_group: 'pipeline',
    agent_results: {
      student_profile: {
        agent_name: 'student_profile', success: true, latency_ms: 200, confidence: 0.9, error: null, data: {},
      },
    },
    agent_latencies: {},
    total_latency_ms: 1200,
    timestamp: new Date().toISOString(),
  } as RecommendationResponse,
}

const slowJob = {
  ...fastJob,
  id: 'art_1',
  label: '文艺青年',
  prompt: '我想选艺术课',
  response: {
    ...fastJob.response!,
    total_latency_ms: 5000,
  },
}

describe('CompareView', () => {
  it('renders intro callout with role="note"', () => {
    render(<CompareView jobs={[fastJob, slowJob]} />)
    const note = screen.getByRole('note', { name: /批量对比说明/ })
    expect(note).toBeTruthy()
  })

  it('renders one row per job with label and prompt', () => {
    render(<CompareView jobs={[fastJob, slowJob]} />)
    expect(screen.getByText('计算机爱好者')).toBeTruthy()
    expect(screen.getByText('我想选编程课')).toBeTruthy()
    expect(screen.getByText('文艺青年')).toBeTruthy()
    expect(screen.getByText('我想选艺术课')).toBeTruthy()
  })

  it('renders latency tag with aria-label for accessibility', () => {
    render(<CompareView jobs={[fastJob, slowJob]} />)
    expect(screen.getByLabelText('1200 ms')).toBeTruthy()
    expect(screen.getByLabelText('5000 ms')).toBeTruthy()
  })

  it('renders warning count tag with aria-label when warnings exist', () => {
    render(<CompareView jobs={[fastJob]} />)
    expect(screen.getByLabelText('1 条选课提醒')).toBeTruthy()
  })

  it('handles jobs with error (no response) gracefully', () => {
    const errorJob = { ...fastJob, response: null, error: '后端超时' }
    render(<CompareView jobs={[errorJob]} />)
    // 表行渲染但 rowExpandable=false（response 为 null）；展开行内容不会出现在 DOM。
    // 验证：job 的 label 仍然在表格中可见，证明 jobs 列表渲染本身未崩。
    expect(screen.getByText('计算机爱好者')).toBeTruthy()
  })
})
