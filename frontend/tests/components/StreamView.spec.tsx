import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import StreamView from '@/components/StreamView'

// 路 2 升级：
// - 推荐流改成 api.recommendStreamWithRetry（带 Last-Event-ID 续传 + 指数退避）
// - StreamView 暴露 "停止生成" 按钮（AbortController UI）
// - 流式输出区 role="status" aria-live="polite"（屏幕阅读器感知）
// - token 累积改 useRef + rAF 节流 flush

vi.mock('@/lib/api', () => ({
  api: {
    recommendStream: vi.fn(),
    recommendStreamWithRetry: vi.fn(),
  },
}))

import { api } from '@/lib/api'
const mockRecommend = api.recommendStreamWithRetry as unknown as ReturnType<typeof vi.fn>

async function* mockStream(events: Array<{ event: string; data: unknown }>) {
  for (const e of events) yield e
}

describe('StreamView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders nothing-while-loading placeholder before any event arrives', async () => {
    mockRecommend.mockImplementation(async function* () {
      await new Promise(() => {})
    })

    render(<StreamView prompt="选几门不用考试的选修课" numItems={5} />)

    expect(await screen.findByText(/正在分析你的选课需求/)).toBeTruthy()
  })

  it('shows 完成 footer after done event with course list', async () => {
    mockRecommend.mockImplementation(() =>
      mockStream([
        { event: 'phase', data: { phase: 'phase1', warning_count: 0 } },
        {
          event: 'done',
          data: {
            courses: [{
              course_id: 'c1',
              course_name: '艺术与生活',
              teacher: '张三',
              credits: 2,
              hours: 32,
              category: '人文艺术',
              campus: '龙洞',
              no_exam: true,
            }],
            selection_warnings: [],
            total_latency_ms: 12000,
            experiment_group: 'pipeline',
          },
        },
      ]),
    )

    render(<StreamView prompt="选几门不用考试的选修课" numItems={5} />)

    await waitFor(() => {
      expect(screen.getByText(/推荐完成/)).toBeTruthy()
    })
    expect(screen.getByText(/1 门课程/)).toBeTruthy()
    expect(screen.getByText(/12000 ms/)).toBeTruthy()
  })

  it('shows error card on error event with retry button', async () => {
    mockRecommend.mockImplementation(() =>
      mockStream([
        { event: 'error', data: { code: 'UPSTREAM_TIMEOUT', message: '后端生成超时' } },
      ]),
    )

    const onRetry = vi.fn()
    render(
      <StreamView prompt="x" numItems={5} onRetry={onRetry} />,
    )

    expect(await screen.findByText(/请求失败/)).toBeTruthy()
    expect(screen.getByText(/UPSTREAM_TIMEOUT/)).toBeTruthy()
    expect(screen.getByText(/后端生成超时/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /重试/ })).toBeTruthy()
  })

  it('cancels in-flight stream on unmount via AbortController', async () => {
    let capturedSignal: AbortSignal | undefined
    mockRecommend.mockImplementation((_body: unknown, signal?: AbortSignal) => {
      capturedSignal = signal
      return mockStream([])
    })

    const { unmount } = render(<StreamView prompt="x" numItems={1} />)
    unmount()

    expect(capturedSignal?.aborted).toBe(true)
  })

  it('renders stop button while streaming (路 2 取消 UI)', async () => {
    mockRecommend.mockImplementation(async function* () {
      await new Promise(() => {})
    })

    render(<StreamView prompt="x" numItems={5} />)
    const stopBtn = await screen.findByRole('button', { name: /停止生成推荐/ })
    expect(stopBtn).toBeTruthy()
  })

  it('clicking stop button aborts the AbortController', async () => {
    let capturedSignal: AbortSignal | undefined
    mockRecommend.mockImplementation((_body: unknown, signal?: AbortSignal) => {
      capturedSignal = signal
      return mockStream([])
    })

    render(<StreamView prompt="x" numItems={5} />)
    const stopBtn = await screen.findByRole('button', { name: /停止生成推荐/ })
    fireEvent.click(stopBtn)
    expect(capturedSignal?.aborted).toBe(true)
  })

  it('hides stop button after stream completes (done event)', async () => {
    mockRecommend.mockImplementation(() =>
      mockStream([
        {
          event: 'done',
          data: {
            courses: [],
            selection_warnings: [],
            total_latency_ms: 500,
            experiment_group: 'pipeline',
          },
        },
      ]),
    )

    render(<StreamView prompt="x" numItems={5} />)
    await waitFor(() => {
      expect(screen.getByText(/推荐完成/)).toBeTruthy()
    })
    expect(screen.queryByRole('button', { name: /停止生成推荐/ })).toBeNull()
  })

  it('CourseInlineCard renders with aria-label after done event (路 1 a11y 升级覆盖流式卡片)', async () => {
    // 完整 Course 字段（mock 用全字段避免 antd 警告）
    const fullCourse = {
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
    mockRecommend.mockImplementation(() =>
      mockStream([
        // text 事件触发 segments 创建（course_id=c1）；done 事件填 courseCards Map；
        // CourseInlineCard 在 segments.map 里渲染，需 course_id 命中 courseCards 才出现
        {
          event: 'text',
          data: { course_id: 'c1', token: 'AI 导论推荐语' },
        },
        {
          event: 'done',
          data: {
            courses: [fullCourse],
            selection_warnings: [],
            total_latency_ms: 5000,
            experiment_group: 'pipeline',
          },
        },
      ]),
    )

    render(<StreamView prompt="x" numItems={5} />)

    // 验证 CourseInlineCard 的 a11y 升级生效
    // rAF 节流 + state flush 需要更长等待（默认 1000ms 不够）
    const group = await screen.findByRole('group', {
      name: '第 1 门课程：人工智能导论，张老师，3 学分',
    }, { timeout: 3000 })
    expect(group).toBeTruthy()
    // popularity tag "爆满" 也在 DOM 内
    expect(await screen.findByLabelText('爆满', {}, { timeout: 3000 })).toBeTruthy()
  })

  it('exposes streaming region to screen readers via aria-live + role', async () => {
    mockRecommend.mockImplementation(async function* () {
      await new Promise(() => {})
    })

    render(<StreamView prompt="x" numItems={5} />)
    const region = await screen.findByRole('status', { name: /推荐流式生成区域/ })
    expect(region.getAttribute('aria-live')).toBe('polite')
    expect(region.getAttribute('aria-busy')).toBe('true')
  })

  it('uses rAF batched flush (single text event still ends up in DOM after rAF tick)', async () => {
    mockRecommend.mockImplementation(() =>
      mockStream([
        { event: 'phase', data: { phase: 'phase1' } },
        { event: 'text', data: { course_id: null, token: 'AI正在为你推荐...' } },
      ]),
    )

    render(<StreamView prompt="x" numItems={5} />)
    // rAF 异步 flush
    await waitFor(() => {
      expect(screen.getByText(/AI正在为你推荐/)).toBeTruthy()
    })
  })

  it('error region uses role="alert" for assistive tech', async () => {
    mockRecommend.mockImplementation(() =>
      mockStream([
        { event: 'error', data: { code: 'GEN_FAILED', message: '生成失败' } },
      ]),
    )

    render(<StreamView prompt="x" numItems={5} />)
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('请求失败')
  })
})
