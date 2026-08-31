'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  Card,
  Collapse,
  Col,
  Row,
  Spin,
  Space,
  Table,
  Tag,
  Typography,
  Button,
  Empty,
  Input,
} from 'antd'
import {
  BulbOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  CodeOutlined,
  ExperimentOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { api } from '../../../lib/api'
import { useNotify } from '../../../lib/api/useNotify'
import type { ExperimentInfo, SSEDoneData } from '../../../types'

const { Text, Title } = Typography
const { TextArea } = Input

async function consumeStreamDone(
  generator: AsyncGenerator<{ event: string; data: unknown }>
): Promise<SSEDoneData> {
  for await (const evt of generator) {
    if (evt.event === 'done') return evt.data as SSEDoneData
    if (evt.event === 'error') throw new Error((evt.data as { message: string }).message || 'Stream error')
  }
  throw new Error('Stream ended without done event')
}

export default function ExperimentsPage() {
  const notify = useNotify()
  const [experiments, setExperiments] = useState<Record<string, ExperimentInfo> | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [comparePrompt, setComparePrompt] = useState('')
  const [compareLoading, setCompareLoading] = useState(false)
  const [pipelineDone, setPipelineDone] = useState<SSEDoneData | null>(null)
  const [reactDone, setReactDone] = useState<SSEDoneData | null>(null)
  const [compareError, setCompareError] = useState<string | null>(null)

  const fetchAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setExperiments(await api.getExperiments())
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '获取实验数据失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchAll()
    const interval = setInterval(fetchAll, 15000)
    return () => clearInterval(interval)
  }, [fetchAll])

  const handleCompare = useCallback(async () => {
    const q = comparePrompt.trim()
    if (!q) {
      notify.toast.warning('请输入选课需求描述')
      return
    }
    setCompareLoading(true)
    setCompareError(null)
    setPipelineDone(null)
    setReactDone(null)
    const uid = `compare_${Date.now()}`
    const body = { user_id: uid, prompt: q, num_items: 5, scene: 'course_selection' as const }
    try {
      const [p, r] = await Promise.all([
        consumeStreamDone(api.recommendStream({ ...body, mode: 'pipeline' })),
        consumeStreamDone(api.recommendStream({ ...body, mode: 'react' })),
      ])
      setPipelineDone(p)
      setReactDone(r)
    } catch (e: unknown) {
      setCompareError(e instanceof Error ? e.message : '对比测试失败')
    } finally {
      setCompareLoading(false)
    }
  }, [comparePrompt, notify.toast])

  return (
    <div className="stagger">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <BulbOutlined style={{ color: '#E8A23D', fontSize: 20 }} />
          <Title level={4} className="serif-heading" style={{ margin: 0 }}>
            实验中心
          </Title>
          <Text type="secondary" style={{ fontSize: 12 }}>A/B 实验状态 · 分组统计 · 架构对比</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={fetchAll} loading={loading} style={{ borderRadius: 8 }}>
          刷新
        </Button>
      </div>

      {error && (
        <Card size="small" style={{ marginBottom: 16, background: '#FDECEC', border: '1px solid #F5C6C6' }}>
          <Space>
            <CloseCircleOutlined style={{ color: '#D64545' }} />
            <Text type="danger">{error}</Text>
          </Space>
        </Card>
      )}

      {/* A/B 实验状态 */}
      <Card
        className="animate-fade-scale"
        style={{ marginBottom: 20, border: '1px solid #CFE3F5', borderRadius: 12 }}
        styles={{ header: { borderBottom: '1px solid #EAF2FB', padding: '16px 20px' }, body: { padding: 20 } }}
        title={
          <Space>
            <ExperimentOutlined style={{ color: '#2E6FBF' }} />
            <span className="serif-heading">A/B 实验状态</span>
          </Space>
        }
      >
        {experiments && Object.keys(experiments).length > 0 ? (
          <Collapse
            items={Object.entries(experiments).map(([expId, exp]) => ({
              key: expId,
              label: (
                <Space>
                  <Text strong>{exp.name}</Text>
                  <Tag style={{ border: 'none', background: exp.enabled ? '#E6F7F3' : '#EAF2FB', color: exp.enabled ? '#147D64' : '#8A8980' }}>
                    {exp.enabled ? '运行中' : '已暂停'}
                  </Tag>
                </Space>
              ),
              children: (
                <div>
                  <Table
                    dataSource={exp.groups}
                    rowKey="name"
                    pagination={false}
                    size="small"
                    columns={[
                      { title: '实验组', dataIndex: 'name', key: 'name' },
                      { title: '权重', dataIndex: 'weight', key: 'weight', render: (v: number) => `${v}%` },
                      {
                        title: '成功率',
                        key: 'rate',
                        render: (_: unknown, r: typeof exp.groups[number]) => {
                          const total = r.successes + r.failures
                          if (total === 0) return <Text type="secondary">无数据</Text>
                          const rate = ((r.successes / total) * 100).toFixed(1)
                          return (
                            <Tag style={{ border: 'none', background: Number(rate) > 50 ? '#E6F7F3' : '#FDECEC', color: Number(rate) > 50 ? '#147D64' : '#C0392B' }}>
                              {rate}%
                            </Tag>
                          )
                        },
                      },
                      { title: '成功', dataIndex: 'successes', key: 'successes' },
                      { title: '失败', dataIndex: 'failures', key: 'failures' },
                    ]}
                  />
                  {exp.stats && Object.keys(exp.stats as Record<string, unknown>).length > 0 && (
                    expId === 'react_vs_pipeline' ? (
                      <div style={{ marginTop: 12 }}>
                        <Text type="secondary" style={{ fontSize: 11, marginBottom: 8, display: 'block' }}>指标统计</Text>
                        <Row gutter={12}>
                          {exp.groups.map((g) => {
                            const groupStats = (exp.stats as Record<string, Record<string, { mean: number; count: number }>>)[g.name]
                            if (!groupStats) return null
                            const items = [
                              { label: '平均延迟', key: 'total_latency_ms', unit: 'ms', color: '#16365C' },
                              { label: '平均课程', key: 'course_count', unit: '门', color: '#1FA88D' },
                              { label: '平均提醒', key: 'warning_count', unit: '条', color: '#14B8A6' },
                            ]
                            return (
                              <Col xs={24} sm={12} key={g.name}>
                                <Card
                                  size="small"
                                  title={<Text strong style={{ fontSize: 12 }}>{g.name === 'react' ? 'ReAct 模式' : 'Pipeline 模式'}</Text>}
                                  style={{ marginBottom: 8 }}
                                  styles={{ header: { borderBottom: '1px solid #EAF2FB', padding: '8px 12px' }, body: { padding: '8px 12px' } }}
                                >
                                  {items.map(({ label, key, unit, color }) => {
                                    const m = groupStats[key]
                                    return (
                                      <div key={key} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                        <Text type="secondary" style={{ fontSize: 11 }}>{label}</Text>
                                        <Text strong style={{ fontSize: 12, color, fontFamily: "'Noto Serif SC', serif" }}>
                                          {m ? `${m.mean.toFixed(0)} ${unit}` : '-'}
                                          {m ? <span style={{ fontSize: 10, color: '#8A8980', marginLeft: 4 }}>({m.count}次)</span> : null}
                                        </Text>
                                      </div>
                                    )
                                  })}
                                </Card>
                              </Col>
                            )
                          })}
                        </Row>
                      </div>
                    ) : (
                      <div style={{ marginTop: 12 }}>
                        <Text type="secondary" style={{ fontSize: 11 }}>统计信息：</Text>
                        <pre style={{ fontSize: 11, background: '#EAF3FC', padding: 10, borderRadius: 8, marginTop: 4, border: '1px solid #CFE3F5', color: '#6B7A8D' }}>
                          {JSON.stringify(exp.stats, null, 2)}
                        </pre>
                      </div>
                    )
                  )}
                </div>
              ),
            }))}
          />
        ) : (
          <Empty description="暂无 A/B 实验数据" />
        )}
      </Card>

      {/* React vs Pipeline 对比测试 */}
      <Card
        className="animate-fade-in"
        style={{ border: '1px solid #CFE3F5', borderRadius: 12 }}
        styles={{ header: { borderBottom: '1px solid #EAF2FB', padding: '16px 20px' }, body: { padding: 20 } }}
        title={
          <Space>
            <ThunderboltOutlined style={{ color: '#14B8A6' }} />
            <span className="serif-heading">React vs Pipeline 对比测试</span>
          </Space>
        }
      >
        <div style={{ marginBottom: 16 }}>
          <TextArea
            value={comparePrompt}
            onChange={(e) => setComparePrompt(e.target.value)}
            placeholder="输入选课需求描述，同时对比 Pipeline 和 React 两种架构的表现..."
            autoSize={{ minRows: 2, maxRows: 4 }}
            style={{ marginBottom: 12, fontSize: 13, borderRadius: 8 }}
          />
          <Button type="primary" icon={<ThunderboltOutlined />} onClick={handleCompare} loading={compareLoading} style={{ borderRadius: 8 }}>
            开始对比
          </Button>
        </div>

        {compareError && (
          <Card size="small" style={{ marginBottom: 12, background: '#FDECEC', border: '1px solid #F5C6C6' }}>
            <Space>
              <CloseCircleOutlined style={{ color: '#D64545' }} />
              <Text type="danger">{compareError}</Text>
            </Space>
          </Card>
        )}

        {compareLoading && (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin size="large" tip="同时发起 Pipeline 和 React 流式推荐...">
              <div style={{ marginTop: 30 }} />
            </Spin>
          </div>
        )}

        {(pipelineDone || reactDone) && !compareLoading && (
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Card
                size="small"
                title={
                  <Space>
                    <ExperimentOutlined style={{ color: '#16365C' }} />
                    <Text strong>Pipeline 架构</Text>
                    <Tag style={{ fontSize: 10, background: '#EAF2FB', color: '#16365C', border: 'none' }}>
                      {pipelineDone?.experiment_group || 'pipeline'}
                    </Tag>
                  </Space>
                }
                styles={{ header: { borderBottom: '1px solid #EAF2FB' } }}
              >
                {pipelineDone ? (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        <ClockCircleOutlined style={{ marginRight: 4 }} />总耗时
                      </Text>
                      <Text strong style={{ fontSize: 16, fontFamily: "'Noto Serif SC', serif", color: '#16365C' }}>
                        {pipelineDone.total_latency_ms.toFixed(0)} ms
                      </Text>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>返回课程</Text>
                      <Text strong style={{ fontSize: 16, fontFamily: "'Noto Serif SC', serif", color: '#1FA88D' }}>
                        {pipelineDone.courses.length} 门
                      </Text>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>执行 Agent</Text>
                      <Text style={{ fontSize: 12, color: '#6B7A8D' }}>
                        {Object.keys(pipelineDone.agent_results || {}).join(' / ')}
                      </Text>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>选课提醒</Text>
                      <Text style={{ fontSize: 12, color: '#6B7A8D' }}>
                        {pipelineDone.selection_warnings.length} 条
                      </Text>
                    </div>
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        Top 3: {pipelineDone.courses.slice(0, 3).map((c) => c.course_name).join(' → ')}
                      </Text>
                    </div>
                  </div>
                ) : (
                  <Text type="secondary">等待中...</Text>
                )}
              </Card>
            </Col>
            <Col xs={24} md={12}>
              <Card
                size="small"
                title={
                  <Space>
                    <CodeOutlined style={{ color: '#14B8A6' }} />
                    <Text strong>React 架构</Text>
                    <Tag style={{ fontSize: 10, background: '#E0F5F2', color: '#B9772E', border: 'none' }}>
                      {reactDone?.experiment_group || 'react'}
                    </Tag>
                  </Space>
                }
                styles={{ header: { borderBottom: '1px solid #EAF2FB' } }}
              >
                {reactDone ? (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        <ClockCircleOutlined style={{ marginRight: 4 }} />总耗时
                      </Text>
                      <Text strong style={{ fontSize: 16, fontFamily: "'Noto Serif SC', serif", color: '#14B8A6' }}>
                        {reactDone.total_latency_ms.toFixed(0)} ms
                      </Text>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>返回课程</Text>
                      <Text strong style={{ fontSize: 16, fontFamily: "'Noto Serif SC', serif", color: '#1FA88D' }}>
                        {reactDone.courses.length} 门
                      </Text>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>执行 Agent</Text>
                      <Text style={{ fontSize: 12, color: '#6B7A8D' }}>
                        {Object.keys(reactDone.agent_results || {}).join(' / ')}
                      </Text>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>选课提醒</Text>
                      <Text style={{ fontSize: 12, color: '#6B7A8D' }}>
                        {reactDone.selection_warnings.length} 条
                      </Text>
                    </div>
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        Top 3: {reactDone.courses.slice(0, 3).map((c) => c.course_name).join(' → ')}
                      </Text>
                    </div>
                  </div>
                ) : (
                  <Text type="secondary">等待中...</Text>
                )}
              </Card>
            </Col>
          </Row>
        )}
      </Card>
    </div>
  )
}
