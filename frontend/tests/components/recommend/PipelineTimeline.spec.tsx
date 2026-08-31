import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import PipelineTimeline from '@/components/recommend/PipelineTimeline'
import type { AgentResult } from '@/types'

const mockAgentResults: Record<string, AgentResult> = {
  student_profile: {
    agent_name: 'student_profile',
    success: true,
    latency_ms: 320,
    confidence: 0.9,
    error: null,
    data: {},
  },
  course_recall: {
    agent_name: 'course_recall',
    success: true,
    latency_ms: 540,
    confidence: 0.85,
    error: null,
    data: {},
  },
  course_rerank: {
    agent_name: 'course_rerank',
    success: true,
    latency_ms: 280,
    confidence: 0.95,
    error: null,
    data: {},
  },
  course_feasibility: {
    agent_name: 'course_feasibility',
    success: false,
    latency_ms: 150,
    confidence: 0.4,
    error: 'hard constraint violation',
    data: {},
  },
  recommendation_reason: {
    agent_name: 'recommendation_reason',
    success: true,
    latency_ms: 1200,
    confidence: 0.92,
    error: null,
    data: {},
  },
}

describe('PipelineTimeline', () => {
  it('renders section heading with Agent pipeline name', () => {
    render(
      <PipelineTimeline agentResults={mockAgentResults} totalLatency={2490} />,
    )
    expect(screen.getByText(/Agent 流水线执行过程/)).toBeTruthy()
  })

  it('renders total latency in the dedicated card', () => {
    render(
      <PipelineTimeline agentResults={mockAgentResults} totalLatency={2490} />,
    )
    // 总耗时卡片：值 + 单位 ms
    expect(screen.getByText('2490')).toBeTruthy()
    expect(screen.getByText('ms')).toBeTruthy()
  })

  it('exposes each agent row to screen readers via aria-label (success path)', () => {
    render(
      <PipelineTimeline agentResults={mockAgentResults} totalLatency={2490} />,
    )
    expect(
      screen.getByLabelText(/学生画像：成功，耗时 320 毫秒/),
    ).toBeTruthy()
  })

  it('exposes failed agent to screen readers', () => {
    render(
      <PipelineTimeline agentResults={mockAgentResults} totalLatency={2490} />,
    )
    expect(
      screen.getByLabelText(/选课可行性：失败，耗时 150 毫秒/),
    ).toBeTruthy()
  })

  it('uses semantic section landmark', () => {
    const { container } = render(
      <PipelineTimeline agentResults={mockAgentResults} totalLatency={2490} />,
    )
    const section = container.querySelector('section')
    expect(section).toBeTruthy()
    expect(section?.getAttribute('aria-labelledby')).toBe('pipeline-timeline-heading')
  })

  it('skips agents not present in agentResults', () => {
    const partial = {
      student_profile: mockAgentResults.student_profile,
      recommendation_reason: mockAgentResults.recommendation_reason,
    }
    render(<PipelineTimeline agentResults={partial} totalLatency={500} />)
    // 不存在的 agent（course_recall）不应渲染
    const section = screen.getByRole('region', { name: /Agent 流水线/ })
    expect(within(section).queryByText('课程召回')).toBeNull()
    // 存在的 agent（recommendation_reason = "推荐理由"）渲染
    expect(within(section).getByText('推荐理由')).toBeTruthy()
  })
})
