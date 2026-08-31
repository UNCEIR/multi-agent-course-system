import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import StatCard from '@/components/recommend/StatCard'

describe('StatCard', () => {
  it('renders title, value, and icon', () => {
    render(
      <StatCard
        icon={<span data-testid="test-icon">★</span>}
        title="总耗时"
        value="1200 ms"
        color="#16365C"
      />,
    )
    expect(screen.getByText('总耗时')).toBeTruthy()
    expect(screen.getByText('1200 ms')).toBeTruthy()
    expect(screen.getByTestId('test-icon')).toBeTruthy()
  })

  it('exposes value to screen readers via aria-label', () => {
    render(
      <StatCard
        icon={<span data-testid="test-icon">★</span>}
        title="推荐课程"
        value="5 门"
        color="#16365C"
      />,
    )
    // aria-label 挂在 antd Text 渲染的 span 上（包含 <strong>），用 getByLabelText 命中
    const labelledEl = screen.getByLabelText('推荐课程：5 门')
    expect(labelledEl).toBeTruthy()
    expect(labelledEl.getAttribute('role')).toBe('status')
  })

  it('marks decorative icons as aria-hidden', () => {
    render(
      <StatCard
        icon={<span data-testid="test-icon">★</span>}
        title="X"
        value="Y"
        color="#000"
      />,
    )
    const iconSpan = screen.getByTestId('test-icon').parentElement
    expect(iconSpan?.getAttribute('aria-hidden')).toBe('true')
  })
})
