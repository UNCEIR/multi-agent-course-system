'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Input,
  Segmented,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd'
import { DatabaseOutlined, InboxOutlined } from '@ant-design/icons'
import type { UploadFile } from 'antd'
import { api } from '../../../lib/api'
import { useAuthStore } from '../../../stores/auth'
import { useNotify } from '../../../lib/api/useNotify'

const { Text } = Typography

const CHUNK_STRATEGIES = [
  { value: 'auto', label: 'auto（自动选择）' },
  { value: 'recursive', label: 'recursive（递归分块）' },
  { value: 'fixed', label: 'fixed（定长分块）' },
  { value: 'paragraph', label: 'paragraph（段落分块）' },
]

// 路 5（2026-08-25）：单/批量上传统一，后端 max_length=5；
// 单文件 10MB 上限与 service.ingest_many.max_file_bytes 对齐。
const MAX_FILES = 5
const MAX_FILE_BYTES = 10 * 1024 * 1024

type ScopeTab = 'all' | 'handbook' | 'transcript'

export default function DocumentsPage() {
  const notify = useNotify()
  const user = useAuthStore((s) => s.user)

  const [scopeTab, setScopeTab] = useState<ScopeTab>('all')
  const [files, setFiles] = useState<UploadFile[]>([])
  const [datasetName, setDatasetName] = useState('')
  const [strategy, setStrategy] = useState('auto')
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<{
    count: number
    datasets: Array<{
      dataset_id: string | null
      filename?: string
      chunks_count: number
      status: string
      error?: string
      message?: string
      max_file_bytes?: number
    }>
  } | null>(null)
  const [error, setError] = useState('')

  // 已上传列表
  const [datasets, setDatasets] = useState<
    Array<{
      dataset_id: string
      dataset_name: string
      source_doc_name: string
      file_type: string
      chunks_count: number
      status: string
      user_id?: string
    }>
  >([])
  const [listLoading, setListLoading] = useState(false)

  const userId = user?.user_id
  const refreshList = useCallback(async () => {
    if (!userId) {
      setDatasets([])
      return
    }
    setListLoading(true)
    try {
      const res = await api.documentsList(userId, true)
      setDatasets(res.datasets)
    } catch (e: unknown) {
      // 静默失败：列表是辅助展示，不阻塞上传主流程
      console.warn('documentsList failed', e)
      setDatasets([])
    } finally {
      setListLoading(false)
    }
  }, [userId])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 挂载加载已上传列表（既有 fetch-on-mount 模式）
    refreshList()
  }, [refreshList])

  // beforeUpload 单文件容量校验
  const beforeUpload = (file: File) => {
    if (file.size > MAX_FILE_BYTES) {
      message.error(`${file.name} 超过 10MB 上限（实际 ${(file.size / 1024 / 1024).toFixed(2)}MB）`)
      return Upload.LIST_IGNORE
    }
    return false // 阻止 antd 自动上传，由我们自己走 fetch
  }

  const handleUpload = async () => {
    if (!user?.user_id) {
      notify.toast.warning('请先登录后再上传文档')
      return
    }
    const ready = files
      .map((f) => f.originFileObj as File | undefined)
      .filter((f): f is File => Boolean(f))
    if (ready.length === 0) {
      notify.toast.warning('请先选择文件')
      return
    }
    if (ready.length > MAX_FILES) {
      notify.toast.warning(`单次最多 ${MAX_FILES} 份文件`)
      return
    }
    if (!datasetName.trim()) {
      notify.toast.warning('请输入数据集名称（dataset_name）')
      return
    }
    setUploading(true)
    setError('')
    setResult(null)
    try {
      // 2026-08-25：student_name 从 auth store 的 name 取；成绩单场景触发脱敏
      // （service.ingest 仅在 user_id != 'public' 且 student_name 非空时才脱敏）
      const res = await api.documentsUpload(
        ready,
        datasetName.trim(),
        strategy,
        user.user_id,
        user.name ?? '',
      )
      setResult(res)
      const okCount = res.datasets.filter(
        (d) => d.status === 'ok' || d.status === 'completed',
      ).length
      const failCount = res.datasets.length - okCount
      if (failCount === 0) {
        notify.toast.success(`已摄入 ${okCount} 份文件`)
      } else {
        notify.toast.warning(`已摄入 ${okCount} 份，${failCount} 份失败`)
      }
      // 上传成功后刷新列表（不 await，UI 立即可见）
      void refreshList()
    } catch (e: unknown) {
      notify.toast.error(e, '上传失败')
      setError(e instanceof Error ? e.message : '上传失败')
    } finally {
      setUploading(false)
    }
  }

  // 按 scopeTab 过滤已上传列表
  const filteredDatasets = datasets.filter((d) => {
    const uid = d.user_id ?? ''
    if (scopeTab === 'handbook') return uid === 'public'
    if (scopeTab === 'transcript') return uid === user?.user_id && uid !== 'public'
    return true
  })

  return (
    <Card
      style={{ border: '1px solid #CFE3F5' }}
      styles={{ body: { padding: 24 } }}
      title={
        <Space>
          <DatabaseOutlined style={{ color: '#2E6FBF' }} />
          <span className="serif-heading" style={{ fontSize: 15 }}>
            知识库文档摄入
          </span>
          <Text type="secondary" style={{ fontSize: 12 }}>
            上传文档 → 解析/分块/向量化入库（chat 用 query_handbook / query_transcript 检索）
          </Text>
        </Space>
      }
    >
      {!user?.user_id && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          title="未登录无法上传文档"
          description="请先到 /login 完成注册/登录，再回到本页面上传。已登录后，本页面会展示你自己的文档列表（按手册 / 成绩单分组）。"
        />
      )}

      <Upload.Dragger
        accept=".csv,.pdf,.txt,.md,.docx"
        multiple
        maxCount={MAX_FILES}
        fileList={files}
        beforeUpload={beforeUpload}
        onChange={({ fileList }) => {
          setFiles(fileList.slice(0, MAX_FILES))
        }}
        onRemove={(removed) => {
          setFiles((prev) => prev.filter((f) => f.uid !== removed.uid))
        }}
        disabled={uploading || !user?.user_id}
        style={{ marginBottom: 16 }}
      >
        <p className="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p className="ant-upload-drag-text">点击或拖拽文档到此处（CSV / PDF / TXT / MD / DOCX）</p>
        <p className="ant-upload-hint" style={{ color: '#94a3b8' }}>
          支持单个或批量上传，最多 {MAX_FILES} 份；单文件不超过 10MB。
          <br />
          <strong>手册类</strong>（学校公开规章）写入 public 分区，chat 用{' '}
          <code>query_handbook</code> 检索；
          <strong>个人成绩单</strong>写入 <code>user_id={user?.user_id ?? '<你>'}</code> 分区，chat
          用 <code>query_transcript</code> 检索（自动脱敏姓名/学号/班级）。
        </p>
      </Upload.Dragger>

      <Space orientation="vertical" style={{ width: '100%', marginBottom: 16 }}>
        <Input
          placeholder="数据集名称 dataset_name（如 my_transcript_2024 / 公开手册）"
          value={datasetName}
          onChange={(e) => setDatasetName(e.target.value)}
          disabled={uploading}
        />
        <Select
          options={CHUNK_STRATEGIES}
          value={strategy}
          onChange={setStrategy}
          style={{ width: 240 }}
          disabled={uploading}
        />
      </Space>

      <Button
        type="primary"
        onClick={handleUpload}
        loading={uploading}
        disabled={files.length === 0 || !user?.user_id}
      >
        {uploading ? '摄入中…' : '上传并摄入'}
      </Button>

      {error && (
        <Text type="danger" style={{ display: 'block', marginTop: 12 }}>
          {error}
        </Text>
      )}

      {result && result.datasets.length === 1 && (
        <Card size="small" style={{ marginTop: 16 }} title="摄入结果（本次）">
          <Descriptions size="small" column={1}>
            <Descriptions.Item label="filename">
              {result.datasets[0].filename ?? '—'}
            </Descriptions.Item>
            <Descriptions.Item label="dataset_id">
              <Tag>{result.datasets[0].dataset_id ?? '—'}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="chunks_count">
              {result.datasets[0].chunks_count}
            </Descriptions.Item>
            <Descriptions.Item label="status">
              <Tag
                color={
                  result.datasets[0].status === 'ok' || result.datasets[0].status === 'completed'
                    ? 'green'
                    : 'red'
                }
              >
                {result.datasets[0].status}
              </Tag>
            </Descriptions.Item>
          </Descriptions>
        </Card>
      )}

      {result && result.datasets.length > 1 && (
        <Card size="small" style={{ marginTop: 16 }} title={`摄入结果（本次 ${result.count} 份）`}>
          <Table
            size="small"
            rowKey={(r) => (r.dataset_id ?? '') + (r.filename ?? '')}
            pagination={false}
            dataSource={result.datasets}
            columns={[
              { title: '文件名', dataIndex: 'filename', ellipsis: true },
              {
                title: 'dataset_id',
                dataIndex: 'dataset_id',
                render: (v: string | null) =>
                  v ? <Tag>{v}</Tag> : <Text type="secondary">—</Text>,
              },
              { title: 'chunks', dataIndex: 'chunks_count', width: 80 },
              {
                title: 'status',
                dataIndex: 'status',
                width: 100,
                render: (v: string, r) =>
                  v === 'ok' || v === 'completed' ? (
                    <Tag color="green">{v}</Tag>
                  ) : (
                    <Space size={4}>
                      <Tag color="red">{v}</Tag>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {r.error ?? r.message ?? ''}
                      </Text>
                    </Space>
                  ),
              },
            ]}
          />
        </Card>
      )}

      {/* 已上传列表（知识库管理模块） */}
      <Card
        size="small"
        style={{ marginTop: 24 }}
        title={
          <Space>
            <DatabaseOutlined />
            <span>已上传文档</span>
            {listLoading && <Spin size="small" />}
          </Space>
        }
        extra={
          user?.user_id && (
            <Segmented
              options={[
                { label: `全部 (${datasets.length})`, value: 'all' },
                { label: '手册 (public)', value: 'handbook' },
                { label: '我的成绩单', value: 'transcript' },
              ]}
              value={scopeTab}
              onChange={(v) => setScopeTab(v as ScopeTab)}
            />
          )
        }
      >
        {!user?.user_id ? (
          <Empty description="登录后可查看你的文档列表" />
        ) : filteredDatasets.length === 0 ? (
          <Empty
            description={
              scopeTab === 'all'
                ? '暂无上传记录'
                : `暂无${scopeTab === 'handbook' ? '手册类' : '成绩单'}上传`
            }
          />
        ) : (
          <Table
            size="small"
            rowKey="dataset_id"
            pagination={{ pageSize: 10, showSizeChanger: false }}
            dataSource={filteredDatasets}
            columns={[
              {
                title: 'dataset_name',
                dataIndex: 'dataset_name',
                ellipsis: true,
              },
              {
                title: '文件名',
                dataIndex: 'source_doc_name',
                ellipsis: true,
              },
              {
                title: '类型',
                dataIndex: 'file_type',
                width: 80,
                render: (v: string) => <Tag>{v}</Tag>,
              },
              { title: 'chunks', dataIndex: 'chunks_count', width: 80 },
              {
                title: '状态',
                dataIndex: 'status',
                width: 100,
                render: (v: string) => (
                  <Tag color={v === 'ok' || v === 'completed' ? 'green' : 'red'}>{v}</Tag>
                ),
              },
              {
                title: '归属',
                dataIndex: 'user_id',
                width: 100,
                render: (v: string) => (
                  <Tag color={v === 'public' ? 'blue' : 'purple'}>
                    {v === 'public' ? '手册 (public)' : '我的'}
                  </Tag>
                ),
              },
            ]}
          />
        )}
      </Card>
    </Card>
  )
}
