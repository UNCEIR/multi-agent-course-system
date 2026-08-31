'use client'

import { useCallback, useState } from 'react'
import { Button, Card, Descriptions, Input, Select, Space, Tabs, Tag, Typography } from 'antd'
import { SmileOutlined, RadarChartOutlined } from '@ant-design/icons'
import { api } from '../../../lib/api'
import { useNotify } from '../../../lib/api/useNotify'
import RadarChart, { type RadarDimension } from '../../../components/RadarChart'

const { Text } = Typography

const COMMENT_TYPES = [
  { value: 'semester_summary', label: '学期总结' },
  { value: 'encouragement', label: '鼓励寄语' },
  { value: 'improvement_advice', label: '改进建议' },
  { value: 'recommendation', label: '学业推荐' },
]

export default function EvaluationPage() {
  const notify = useNotify()
  const [tab, setTab] = useState('teacher')
  const [targetUserId, setTargetUserId] = useState('')
  const [commentType, setCommentType] = useState('semester_summary')
  const [running, setRunning] = useState(false)
  const [stage, setStage] = useState('')
  const [radar, setRadar] = useState<RadarDimension[]>([])
  const [rejected, setRejected] = useState<string[]>([])
  const [overallTheme, setOverallTheme] = useState('')
  const [comment, setComment] = useState('')
  const [commentStatus, setCommentStatus] = useState('')
  const [error, setError] = useState('')
  const [meItems, setMeItems] = useState<Array<Record<string, unknown>>>([])
  const [meUserId, setMeUserId] = useState('')
  const [meLoading, setMeLoading] = useState(false)

  const handleGenerate = useCallback(async () => {
    const uid = targetUserId.trim()
    if (!uid) {
      notify.toast.warning('请输入目标学生 user_id')
      return
    }
    setRunning(true)
    setError('')
    setStage('')
    setRadar([])
    setRejected([])
    setOverallTheme('')
    setComment('')
    setCommentStatus('')
    try {
      for await (const evt of api.evaluation({
        target_user_id: uid,
        comment_type: commentType,
        generated_by: 'web',
      })) {
        if (evt.event === 'stage') {
          setStage(evt.data.stage)
        } else if (evt.event === 'radar') {
          setRadar(evt.data.dimensions)
          setRejected(evt.data.rejected ?? [])
          setOverallTheme(evt.data.overall_theme ?? '')
        } else if (evt.event === 'comment_token') {
          setComment((prev) => prev + evt.data.token)
        } else if (evt.event === 'done') {
          setComment(evt.data.comment)
          setCommentStatus(evt.data.comment_status)
          setStage('done')
        } else if (evt.event === 'error') {
          setError(evt.data.message || evt.data.code)
        }
      }
    } catch (e: unknown) {
      notify.toast.error(e, '评价生成失败')
      setError(e instanceof Error ? e.message : '评价生成失败')
    } finally {
      setRunning(false)
    }
  }, [targetUserId, commentType, notify])

  const handleMe = useCallback(async () => {
    const uid = meUserId.trim()
    if (!uid) {
      notify.toast.warning('请输入学生 user_id')
      return
    }
    setMeLoading(true)
    try {
      const res = await api.evaluationMe(uid)
      setMeItems(res.items)
    } catch (e: unknown) {
      notify.toast.error(e, '查询失败')
    } finally {
      setMeLoading(false)
    }
  }, [meUserId, notify])

  return (
    <Card
      style={{ border: '1px solid #CFE3F5' }}
      styles={{ body: { padding: 24 } }}
      title={
        <Space>
          <SmileOutlined style={{ color: '#1FA88D' }} />
          <span className="serif-heading" style={{ fontSize: 15 }}>
            评价寄语
          </span>
          <Text type="secondary" style={{ fontSize: 12 }}>
            教师端生成（雷达图 + 评语流）/ 学生端查看
          </Text>
        </Space>
      }
    >
      <Tabs
        activeKey={tab}
        onChange={setTab}
        items={[
          {
            key: 'teacher',
            label: '教师端生成',
            children: (
              <Space orientation="vertical" size={12} style={{ width: '100%' }}>
                <Space wrap>
                  <Input
                    placeholder="目标学生 user_id（如 3123003252）"
                    value={targetUserId}
                    onChange={(e) => setTargetUserId(e.target.value)}
                    style={{ width: 260 }}
                    disabled={running}
                  />
                  <Select
                    options={COMMENT_TYPES}
                    value={commentType}
                    onChange={setCommentType}
                    style={{ width: 140 }}
                    disabled={running}
                  />
                  <Button type="primary" onClick={handleGenerate} loading={running}>
                    {running ? '生成中…' : '生成评价'}
                  </Button>
                </Space>
                {running && stage && <Tag color="processing">阶段：{stage}</Tag>}
                {error && <Text type="danger">{error}</Text>}
                {radar.length > 0 && (
                  <Card
                    size="small"
                    title={
                      <Space>
                        <RadarChartOutlined />
                        雷达画像
                      </Space>
                    }
                  >
                    <RadarChart dimensions={radar} theme={overallTheme || '综合学业表现'} />
                    {rejected.length > 0 && (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        未纳入维度（数据不足）：{rejected.join('、')}
                      </Text>
                    )}
                  </Card>
                )}
                {comment && (
                  <Card size="small" title="评语">
                    <Text style={{ whiteSpace: 'pre-wrap', lineHeight: 1.9 }}>{comment}</Text>
                    <div style={{ marginTop: 8 }}>
                      <Tag color={commentStatus === 'rule' ? 'orange' : 'green'}>
                        {commentStatus === 'rule' ? '规则化兜底' : 'LLM 生成'}
                      </Tag>
                    </div>
                  </Card>
                )}
              </Space>
            ),
          },
          {
            key: 'student',
            label: '学生端查看',
            children: (
              <Space orientation="vertical" size={12} style={{ width: '100%' }}>
                <Space>
                  <Input
                    placeholder="学生 user_id"
                    value={meUserId}
                    onChange={(e) => setMeUserId(e.target.value)}
                    style={{ width: 260 }}
                  />
                  <Button onClick={handleMe} loading={meLoading}>
                    查询我的评价
                  </Button>
                </Space>
                {meItems.length === 0 && !meLoading ? (
                  <Text type="secondary">暂无评价记录（或该用户无权限访问）</Text>
                ) : (
                  meItems.map((item, i) => {
                    const radarData =
                      (item.radar as { dimensions?: RadarDimension[] } | null)?.dimensions ?? []
                    return (
                      <Card key={i} size="small">
                        <Descriptions size="small" column={2}>
                          <Descriptions.Item label="类型">
                            {COMMENT_TYPES.find((c) => c.value === item.comment_type)?.label ??
                              String(item.comment_type)}
                          </Descriptions.Item>
                          <Descriptions.Item label="时间">
                            {String(item.created_at ?? '—')}
                          </Descriptions.Item>
                        </Descriptions>
                        {radarData.length > 0 && <RadarChart dimensions={radarData} height={240} />}
                        <Text style={{ whiteSpace: 'pre-wrap', lineHeight: 1.8 }}>
                          {String(item.comment ?? '')}
                        </Text>
                      </Card>
                    )
                  })
                )}
              </Space>
            ),
          },
        ]}
      />
    </Card>
  )
}
