import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import CourseGraph from '@/components/CourseGraph'

// Phase 4 E2：课程图谱 nodes/edges 渲染 + 空态

describe('CourseGraph', () => {
  it('renders empty state when no nodes', () => {
    render(<CourseGraph nodes={[]} edges={[]} />)
    expect(screen.getByText('暂无课程图谱数据')).toBeDefined()
  })

  it('renders nodes and edge relations', () => {
    render(
      <CourseGraph
        nodes={[
          { id: 'course:机器学习', type: 'course', label: '机器学习' },
          { id: 'domain:AI', type: 'domain', label: 'AI' },
          { id: 'prerequisite:Python', type: 'prerequisite', label: 'Python' },
        ]}
        edges={[
          { source: 'course:机器学习', target: 'domain:AI', relation: 'domain_of' },
          { source: 'course:机器学习', target: 'prerequisite:Python', relation: 'prerequisite' },
        ]}
      />,
    )
    expect(screen.getByText('机器学习')).toBeDefined()
    expect(screen.getByText('AI')).toBeDefined()
    expect(screen.getByText('Python')).toBeDefined()
    expect(screen.getByText(/机器学习 → AI（domain_of）/)).toBeDefined()
  })
})
