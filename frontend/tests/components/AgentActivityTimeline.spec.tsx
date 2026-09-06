import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import AgentActivityTimeline from '@/components/AgentActivityTimeline'

// Phase 4 E4：think→act→observe 三阶段（chat 消费链）——act=start，observe=end+result

describe('AgentActivityTimeline', () => {
  it('renders nothing when no tools', () => {
    const { container } = render(<AgentActivityTimeline tools={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders act for start and observe+result for end', () => {
    render(
      <AgentActivityTimeline
        tools={[
          { name: 'query_handbook', status: 'start' },
          { name: 'query_handbook', status: 'end', result: '命中奖学金章节' },
        ]}
      />,
    )
    expect(screen.getAllByText('query_handbook').length).toBeGreaterThan(0)
    expect(screen.getByText('act')).toBeDefined()
    expect(screen.getByText('observe')).toBeDefined()
    expect(screen.getByText('命中奖学金章节')).toBeDefined()
  })

  it('truncates long result', () => {
    const long = 'x'.repeat(300)
    render(<AgentActivityTimeline tools={[{ name: 't', status: 'end', result: long }]} />)
    expect(screen.getByText(/x{100,}…/)).toBeDefined()
  })
})
