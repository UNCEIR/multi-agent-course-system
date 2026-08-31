'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Input,
  Modal,
  Progress,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  Upload,
} from 'antd'
import { InboxOutlined, FilePdfOutlined, ReloadOutlined, HistoryOutlined } from '@ant-design/icons'
import type { UploadFile } from 'antd'
import { api } from '../../../lib/api'
import { useAuthStore } from '../../../stores/auth'
import { useNotify } from '../../../lib/api/useNotify'
import type {
  ReportArtifactDetail,
  ReportBatchDetailResult,
  ReportStudentDoneData,
  ReportStudentErrorData,
  ReportUploadBatch,
} from '../../../types'

const { Text } = Typography

const REPORT_MAX_FILES = 20
const REPORT_MAX_FILE_BYTES = 10 * 1024 * 1024

export default function ReportPage() {
  const notify = useNotify()
  const user = useAuthStore((s) => s.user)
  const [files, setFiles] = useState<UploadFile[]>([])
  const [semester, setSemester] = useState('')
  const [className, setClassName] = useState('')
  const [userMessage, setUserMessage] = useState('')
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState(0)
  const [students, setStudents] = useState<ReportStudentDoneData[]>([])
  const [failed, setFailed] = useState<ReportStudentErrorData[]>([])
  const [batchId, setBatchId] = useState('')
  const [error, setError] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  // 原始文件自管（uid + File 成对）：不依赖 antd 内部 originFileObj，版本间行为稳定
  const rawFilesRef = useRef<Array<{ uid: string; file: File }>>([])

  // 已生成批次（输入侧上传记录，落库 report_uploads；与知识库 document_records 分表）
  const [batches, setBatches] = useState<ReportUploadBatch[]>([])
  const [listLoading, setListLoading] = useState(false)

  // 批次详情弹窗（逐学生产物：查看/下载）
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailData, setDetailData] = useState<ReportBatchDetailResult | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const handleViewBatch = useCallback(
    async (batchId: string) => {
      if (!user?.user_id) return
      setDetailLoading(true)
      setDetailData(null)
      setDetailOpen(true)
      try {
        const res = await api.reportBatchDetail(batchId, user.user_id)
        setDetailData(res)
      } catch (e: unknown) {
        notify.toast.error(e, '加载批次详情失败')
        setDetailOpen(false)
      } finally {
        setDetailLoading(false)
      }
    },
    [user, notify],
  )

  const userId = user?.user_id
  const refreshBatches = useCallback(async () => {
    if (!userId) {
      setBatches([])
      return
    }
    setListLoading(true)
    try {
      const res = await api.reportBatches(userId)
      setBatches(res.batches)
    } catch (e: unknown) {
      // 列表是辅助展示，静默失败不阻塞上传主流程
      console.warn('reportBatches failed', e)
    } finally {
      setListLoading(false)
    }
  }, [userId])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 挂载加载批次列表（既有 fetch-on-mount 模式）
    void refreshBatches()
  }, [refreshBatches])

  const handleRun = useCallback(
    async (retryBatch?: boolean) => {
      if (!user?.user_id) {
        notify.toast.warning('请先登录后再生成成绩报告')
        return
      }
      const uploads = rawFilesRef.current.map((e) => e.file)
      if (!retryBatch && uploads.length === 0) {
        notify.toast.warning('请先上传成绩单 Excel 文件')
        return
      }
      setRunning(true)
      setError('')
      setProgress(0)
      setStudents([])
      setFailed([])
      setBatchId('')
      const ac = new AbortController()
      abortRef.current = ac
      const realFiles = uploads.slice(0, REPORT_MAX_FILES)
      try {
        for await (const evt of api.reportUpload(
          realFiles,
          semester,
          className,
          userMessage,
          user.user_id,
          ac.signal,
        )) {
          if (evt.event === 'progress') {
            const p = evt.data as Record<string, unknown>
            const done = typeof p.done === 'number' ? p.done : undefined
            const total = typeof p.total === 'number' ? p.total : undefined
            if (done !== undefined && total) setProgress(Math.round((done / total) * 100))
          } else if (evt.event === 'student_done') {
            setStudents((prev) => [...prev, evt.data])
            setProgress((prev) => Math.min(prev + 5, 95))
          } else if (evt.event === 'student_error') {
            setFailed((prev) => [...prev, evt.data])
          } else if (evt.event === 'done') {
            setBatchId(evt.data.batch_id)
            setStudents(evt.data.students)
            setFailed(evt.data.failed_students)
            setProgress(100)
            // 生成完成 → 刷新「已生成批次」列表（落库闭环可见）
            void refreshBatches()
          } else if (evt.event === 'error') {
            setError(evt.data.message || evt.data.code)
          }
        }
      } catch (e: unknown) {
        notify.toast.error(e, '报告生成失败')
        setError(e instanceof Error ? e.message : '报告生成失败')
      } finally {
        setRunning(false)
      }
    },
    [semester, className, userMessage, user, notify, refreshBatches],
  )

  return (
    <Card
      style={{ border: '1px solid #CFE3F5' }}
      styles={{ body: { padding: 24 } }}
      title={
        <Space>
          <FilePdfOutlined style={{ color: '#D64545' }} />
          <span className="serif-heading" style={{ fontSize: 15 }}>
            成绩报告生成
          </span>
          <Text type="secondary" style={{ fontSize: 12 }}>
            批量 Excel → 逐学生成绩单 PDF（每学生独有下载链接）
          </Text>
        </Space>
      }
    >
      {!user?.user_id && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          title="未登录无法生成成绩报告"
          description="请先到 /login 完成注册/登录，再回到本页面上传成绩单 Excel。登录后本页面会展示你自己的生成批次记录。"
        />
      )}

      <Upload.Dragger
        multiple
        accept=".xlsx,.xls"
        fileList={files}
        beforeUpload={(file) => {
          // 单文件容量校验（与后端 report_max_file_mb 对齐）；超限不加入列表
          if (file.size > REPORT_MAX_FILE_BYTES) {
            notify.toast.error(
              `${file.name} 超过 10MB 上限（实际 ${(file.size / 1024 / 1024).toFixed(2)}MB）`,
            )
            return Upload.LIST_IGNORE
          }
          if (rawFilesRef.current.length >= REPORT_MAX_FILES) {
            notify.toast.warning(`单次最多 ${REPORT_MAX_FILES} 个文件`)
            return Upload.LIST_IGNORE
          }
          // 自管 uid + 原始 File（不依赖 antd 内部 originFileObj，版本间行为稳定）
          const uid = `rf_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
          rawFilesRef.current = [...rawFilesRef.current, { uid, file }]
          setFiles((prev) => [
            ...prev,
            { uid, name: file.name, size: file.size, originFileObj: file } as UploadFile,
          ])
          return false // 阻止 antd 自动上传，由 handleRun 统一走 SSE 接口
        }}
        onRemove={(f) => {
          rawFilesRef.current = rawFilesRef.current.filter((e) => e.uid !== f.uid)
          setFiles((prev) => prev.filter((x) => x.uid !== f.uid))
        }}
        disabled={running || !user?.user_id}
        style={{ marginBottom: 16 }}
      >
        <p className="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p className="ant-upload-text">
          点击或拖拽成绩单 Excel 到此处（≤{REPORT_MAX_FILES} 个文件，单文件 ≤10MB）
        </p>
      </Upload.Dragger>

      <Space orientation="vertical" style={{ width: '100%', marginBottom: 16 }}>
        <Input
          placeholder="班级（可选，如 四（7）班；留空则用 Excel 里的班级）"
          value={className}
          onChange={(e) => setClassName(e.target.value)}
          disabled={running}
        />
        <Input
          placeholder="学期（可选，如 2023-2024 第二学期）"
          value={semester}
          onChange={(e) => setSemester(e.target.value)}
          disabled={running}
        />
        <Input
          placeholder="补充要求（可选，会传给生成 Agent）"
          value={userMessage}
          onChange={(e) => setUserMessage(e.target.value)}
          disabled={running}
        />
      </Space>

      <Button
        type="primary"
        onClick={() => handleRun()}
        loading={running}
        disabled={files.length === 0 || !user?.user_id}
        style={{ marginBottom: 16 }}
      >
        {running ? '生成中…' : '开始生成'}
      </Button>
      {running && batchId === '' && (
        <Button style={{ marginLeft: 8 }} onClick={() => abortRef.current?.abort()}>
          取消
        </Button>
      )}

      {running && <Progress percent={progress} style={{ marginBottom: 16 }} />}

      {error && (
        <Text type="danger" style={{ display: 'block', marginBottom: 12 }}>
          {error}
          <Button
            size="small"
            icon={<ReloadOutlined />}
            style={{ marginLeft: 8 }}
            onClick={() => handleRun(true)}
            disabled={running}
          >
            重试
          </Button>
        </Text>
      )}

      {students.length > 0 && (
        <Table<ReportStudentDoneData>
          size="small"
          style={{ marginBottom: 16 }}
          rowKey={(r) => r.student_id || r.url}
          dataSource={students}
          pagination={false}
          columns={[
            { title: '学生', dataIndex: 'name', width: 160 },
            { title: '学号', dataIndex: 'student_id', width: 160 },
            { title: '格式', dataIndex: 'format', width: 80, render: (v) => <Tag>{v}</Tag> },
            {
              title: '状态',
              dataIndex: 'status',
              width: 100,
              render: (v) => (
                <Tag color={v === 'ok' || v === 'done' ? 'green' : 'processing'}>{v}</Tag>
              ),
            },
            {
              title: '操作',
              key: 'actions',
              width: 140,
              render: (_, r) =>
                r.url ? (
                  <Space size={4}>
                    <a href={`${r.url}&inline=1`} target="_blank" rel="noreferrer">
                      查看
                    </a>
                    <a href={r.url} target="_blank" rel="noreferrer">
                      下载
                    </a>
                  </Space>
                ) : (
                  <Text type="secondary">—</Text>
                ),
            },
          ]}
        />
      )}

      {failed.length > 0 && (
        <Table<ReportStudentErrorData>
          size="small"
          rowKey={(r, i) => `${r.student_id}-${i}`}
          dataSource={failed}
          pagination={false}
          columns={[
            { title: '学生', dataIndex: 'name', width: 160 },
            {
              title: '原因',
              dataIndex: 'reason',
              render: (v) => <Text type="danger">{v || '—'}</Text>,
            },
          ]}
          title={() => (
            <Text strong type="danger">
              失败学生（{failed.length}）
            </Text>
          )}
        />
      )}

      {batchId && (
        <Text type="secondary" style={{ display: 'block', fontSize: 12 }}>
          批次号：{batchId}（生成 {students.length} 份，失败 {failed.length} 份）
        </Text>
      )}

      {/* 已生成批次（输入侧上传记录，落库 report_uploads） */}
      <Card
        size="small"
        style={{ marginTop: 24, borderColor: 'rgba(207,227,245,0.8)' }}
        title={
          <Space>
            <HistoryOutlined style={{ color: '#2E6FBF' }} />
            <span className="serif-heading" style={{ fontSize: 14 }}>
              已生成批次
            </span>
            <Text type="secondary" style={{ fontSize: 12 }}>
              每次上传落库 report_uploads（与知识库分表），状态机 processing → done/error
            </Text>
          </Space>
        }
        extra={
          <Button
            size="small"
            type="link"
            onClick={() => void refreshBatches()}
            loading={listLoading}
            disabled={!user?.user_id}
          >
            刷新
          </Button>
        }
      >
        {batches.length === 0 ? (
          <Text type="secondary" style={{ display: 'block', padding: '12px 0' }}>
            {user?.user_id
              ? '暂无生成记录，上传成绩单后会自动出现在这里。'
              : '登录后展示你的生成批次记录。'}
          </Text>
        ) : (
          <Table<ReportUploadBatch>
            size="small"
            rowKey={(r) => r.batch_id}
            dataSource={batches}
            pagination={{ pageSize: 10, hideOnSinglePage: true }}
            columns={[
              {
                title: '批次',
                dataIndex: 'batch_id',
                width: 120,
                render: (v) => <Text code>{v}</Text>,
              },
              { title: '学期', dataIndex: 'semester', width: 180, render: (v) => v || '—' },
              {
                title: '文件',
                key: 'files',
                render: (_, r) => (
                  <Text style={{ fontSize: 12 }}>
                    {r.file_names.join('、') || `${r.file_count} 份`}
                  </Text>
                ),
              },
              {
                title: '状态',
                dataIndex: 'status',
                width: 110,
                render: (v: string) => {
                  const map: Record<string, { color: string; label: string }> = {
                    processing: { color: 'processing', label: '生成中' },
                    done: { color: 'green', label: '完成' },
                    error: { color: 'red', label: '失败' },
                  }
                  const m = map[v] ?? { color: 'default', label: v }
                  return <Tag color={m.color}>{m.label}</Tag>
                },
              },
              {
                title: '结果',
                key: 'summary',
                width: 140,
                render: (_, r) => (
                  <Text style={{ fontSize: 12 }}>
                    {r.status === 'done'
                      ? `成功 ${r.students_ok ?? 0} / 失败 ${r.students_failed ?? 0}`
                      : '—'}
                  </Text>
                ),
              },
              {
                title: '操作',
                key: 'actions',
                width: 80,
                render: (_, r) => (
                  <Button
                    size="small"
                    type="link"
                    onClick={() => void handleViewBatch(r.batch_id)}
                    disabled={!user?.user_id}
                  >
                    详情
                  </Button>
                ),
              },
            ]}
          />
        )}
      </Card>

      {/* 批次详情弹窗：逐学生产物（report_artifacts）查看/下载 */}
      <Modal
        title={
          <Space>
            <HistoryOutlined style={{ color: '#2E6FBF' }} />
            <span className="serif-heading" style={{ fontSize: 15 }}>
              批次详情{detailData ? `（${detailData.batch_id}）` : ''}
            </span>
          </Space>
        }
        open={detailOpen}
        onCancel={() => setDetailOpen(false)}
        footer={null}
        width={760}
      >
        {detailLoading && (
          <div style={{ textAlign: 'center', padding: 32 }}>
            <Spin />
          </div>
        )}
        {detailData && (
          <Table<ReportArtifactDetail>
            size="small"
            rowKey={(a) => `${a.student_id}-${a.file_key}`}
            dataSource={detailData.students}
            pagination={{ pageSize: 10, hideOnSinglePage: true }}
            columns={[
              { title: '学生', dataIndex: 'student_name', width: 140 },
              { title: '学号', dataIndex: 'student_id', width: 120 },
              {
                title: '格式',
                dataIndex: 'format',
                width: 70,
                render: (v) => <Tag>{v}</Tag>,
              },
              {
                title: '状态',
                dataIndex: 'status',
                width: 90,
                render: (v) => <Tag color={v === 'ok' ? 'green' : 'red'}>{v}</Tag>,
              },
              {
                title: '原因',
                dataIndex: 'error_message',
                render: (v) => (v ? <Text type="danger">{v}</Text> : '—'),
              },
              {
                title: '操作',
                key: 'actions',
                width: 130,
                render: (_, a) =>
                  a.url ? (
                    <Space size={4}>
                      <a href={`${a.url}&inline=1`} target="_blank" rel="noreferrer">
                        查看
                      </a>
                      <a href={a.url} target="_blank" rel="noreferrer">
                        下载
                      </a>
                    </Space>
                  ) : (
                    <Text type="secondary">—</Text>
                  ),
              },
            ]}
          />
        )}
      </Modal>
    </Card>
  )
}
