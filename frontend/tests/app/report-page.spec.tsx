import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { App } from 'antd'
import ReportPage from '@/app/(main)/report/page'
import { useAuthStore } from '@/stores/auth'

// 路 2 契约：报告页必须消费 SSE 流并断言（事件序 / 终态 done / 结构化 error），
// 上传必须带 user_id 落库，done 后刷新「已生成批次」列表（report_uploads）。
vi.mock('@/lib/api', () => ({
  api: {
    reportUpload: vi.fn(),
    reportBatches: vi.fn(),
    reportBatchDetail: vi.fn(),
  },
}))

import { api } from '@/lib/api'

const mockUpload = api.reportUpload as unknown as ReturnType<typeof vi.fn>
const mockBatches = api.reportBatches as unknown as ReturnType<typeof vi.fn>
const mockBatchDetail = api.reportBatchDetail as unknown as ReturnType<typeof vi.fn>

async function* stream(events: Array<{ event: string; data: unknown }>) {
  for (const e of events) yield e
}

function renderPage() {
  return render(
    <App>
      <ReportPage />
    </App>,
  )
}

async function selectFile(container: HTMLElement, filename: string) {
  const input = container.querySelector('input[type="file"]') as HTMLInputElement
  const file = new File(['dummy'], filename, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
  fireEvent.change(input, { target: { files: [file] } })
  // jsdom 下 antd Upload 的 onChange 异步触发：等「开始生成」按钮变为可用再操作
  await waitFor(() => {
    expect((screen.getByRole('button', { name: /开始生成/ }) as HTMLButtonElement).disabled).toBe(
      false,
    )
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.getState().login({ user_id: 't1', name: '王老师', role: 'teacher' }, 'token')
})

describe('ReportPage', () => {
  it('loads 已生成批次 history with user_id from reportBatches', async () => {
    mockBatches.mockResolvedValue({
      count: 1,
      batches: [
        {
          batch_id: 'rb_1',
          user_id: 't1',
          semester: '2023-2024第二学期',
          file_count: 1,
          file_names: ['道法.xlsx'],
          status: 'done',
          students_ok: 37,
          students_failed: 0,
        },
      ],
    })

    renderPage()

    expect(mockBatches).toHaveBeenCalledWith('t1')
    expect(await screen.findByText('rb_1')).toBeTruthy()
    expect(screen.getByText('道法.xlsx')).toBeTruthy()
    expect(screen.getByText(/成功 37 \/ 失败 0/)).toBeTruthy()
  })

  it('uploads with user_id, consumes SSE stream to done, then refreshes batch list', async () => {
    mockBatches.mockResolvedValue({ count: 0, batches: [] })
    mockUpload.mockImplementation(() =>
      stream([
        { event: 'progress', data: { done: 1, total: 2 } },
        {
          event: 'student_done',
          data: {
            student_id: '1',
            name: '陈烨',
            status: 'ok',
            format: 'html',
            url: '/api/v1/report/download?x=1',
          },
        },
        {
          event: 'done',
          data: {
            batch_id: 'b_tool',
            students: [
              {
                student_id: '1',
                name: '陈烨',
                status: 'ok',
                format: 'html',
                url: '/api/v1/report/download?x=1',
              },
            ],
            failed_students: [],
            warnings: [],
          },
        },
      ]),
    )

    const { container } = renderPage()
    await selectFile(container, '道法.xlsx')
    // 填写班级（手动覆盖，解决「班级：」为空）
    fireEvent.change(screen.getByPlaceholderText(/班级/), { target: { value: '四（7）班' } })
    fireEvent.click(screen.getByRole('button', { name: /开始生成/ }))

    // 终态 done：批次号 + 学生表格出现
    await waitFor(() => expect(screen.getByText(/批次号：b_tool/)).toBeTruthy())
    expect(screen.getByText('陈烨')).toBeTruthy()

    // 预览：查看链接带 inline=1（后端 Content-Disposition: inline）
    const viewLink = screen.getByRole('link', { name: '查看' })
    expect(viewLink.getAttribute('href')).toContain('&inline=1')
    // 下载链接不带 inline
    const dlLink = screen.getByRole('link', { name: '下载' })
    expect(dlLink.getAttribute('href')).not.toContain('inline=1')

    // 上传调用带 user_id（落库归属）
    expect(mockUpload).toHaveBeenCalledTimes(1)
    const args = mockUpload.mock.calls[0]
    expect(args[0]).toHaveLength(1)
    expect(args[1]).toBe('') // semester
    expect(args[2]).toBe('四（7）班') // class_name
    expect(args[3]).toBe('') // userMessage
    expect(args[4]).toBe('t1') // user_id

    // done 后刷新批次列表（落库闭环可见）
    await waitFor(() => expect(mockBatches).toHaveBeenCalledTimes(2))
  })

  it('shows structured error event with retry button', async () => {
    mockBatches.mockResolvedValue({ count: 0, batches: [] })
    mockUpload.mockImplementation(() =>
      stream([
        { event: 'error', data: { code: 'NO_BATCH_RESULT', message: '工具未返回批量结果' } },
      ]),
    )

    const { container } = renderPage()
    await selectFile(container, '道法.xlsx')
    fireEvent.click(screen.getByRole('button', { name: /开始生成/ }))

    expect(await screen.findByText('工具未返回批量结果')).toBeTruthy()
    expect(screen.getByRole('button', { name: /重试/ })).toBeTruthy()
  })

  it('requires login before upload and skips batch list fetch', () => {
    useAuthStore.getState().logout()
    mockBatches.mockResolvedValue({ count: 0, batches: [] })

    renderPage()

    expect(screen.getByText(/未登录无法生成成绩报告/)).toBeTruthy()
    expect(mockBatches).not.toHaveBeenCalled()
    const btn = screen.getByRole('button', { name: /开始生成/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
  })
})

it('opens batch detail modal with artifacts and preview links', async () => {
  mockBatches.mockResolvedValue({
    count: 1,
    batches: [
      {
        batch_id: 'rb_1',
        user_id: 't1',
        semester: '2023-2024第二学期',
        file_count: 1,
        file_names: ['道法.xlsx'],
        status: 'done',
        students_ok: 1,
        students_failed: 0,
      },
    ],
  })
  mockBatchDetail.mockResolvedValue({
    batch_id: 'b_1',
    batch: {
      batch_id: 'rb_1',
      user_id: 't1',
      semester: '2023-2024第二学期',
      file_count: 1,
      file_names: ['道法.xlsx'],
      status: 'done',
      students_ok: 1,
      students_failed: 0,
    },
    students: [
      {
        batch_id: 'b_1',
        student_id: '1',
        student_name: '陈烨',
        format: 'pdf',
        status: 'ok',
        file_key: 'b_1/1.pdf',
        url: '/api/v1/report/download?file_key=b_1/1.pdf&token=t&expires_at=9999999999',
      },
    ],
  })

  renderPage()

  await screen.findByText('rb_1')
  fireEvent.click(screen.getByRole('button', { name: '详情' }))

  expect(mockBatchDetail).toHaveBeenCalledWith('rb_1', 't1')
  expect(await screen.findByText(/批次详情/)).toBeTruthy()
  expect(screen.getByText('陈烨')).toBeTruthy()
  const links = screen.getAllByRole('link')
  expect(links.some((l) => (l.getAttribute('href') ?? '').includes('&inline=1'))).toBe(true)
})
