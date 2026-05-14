import { useState, useEffect, useCallback } from 'react'
import {
  Card,
  Descriptions,
  Tag,
  Row,
  Col,
  Table,
  Button,
  Spin,
  Empty,
  Space,
  Typography,
  Collapse,
} from 'antd'
import {
  HeartOutlined,
  DashboardOutlined,
  ExperimentOutlined,
  ReloadOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { api } from '../services/api'
import type { HealthResponse, MetricsResponse, ExperimentInfo } from '../types'

const { Text, Title } = Typography

export default function MonitorPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null)
  const [experiments, setExperiments] = useState<Record<string, ExperimentInfo> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [h, m, e] = await Promise.all([api.health(), api.getMetrics(), api.getExperiments()])
      setHealth(h)
      setMetrics(m)
      setExperiments(e)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '获取监控数据失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAll()
    const interval = setInterval(fetchAll, 10000)
    return () => clearInterval(interval)
  }, [fetchAll])

  if (loading && !health) {
    return (
      <div style={{ textAlign: 'center', padding: 120 }}>
        <Spin size="large" />
        <div style={{ marginTop: 20, color: '#8a8980' }}>加载系统监控数据...</div>
      </div>
    )
  }

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <DashboardOutlined style={{ color: '#c88c3e', fontSize: 20 }} />
          <Title level={4} className="serif-heading" style={{ margin: 0 }}>
            系统监控面板
          </Title>
        </div>
        <Button
          icon={<ReloadOutlined />}
          onClick={fetchAll}
          loading={loading}
          style={{ borderRadius: 8 }}
        >
          刷新
        </Button>
      </div>

      {error && (
        <Card style={{ marginBottom: 20, background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 10 }}>
          <Space>
            <CloseCircleOutlined style={{ color: '#a52a2a' }} />
            <Text type="danger">{error}</Text>
          </Space>
        </Card>
      )}

      {/* ========== Health ========== */}
      <Card
        className="animate-fade-scale"
        style={{ marginBottom: 20, border: '1px solid #e8e0d5' }}
        styles={{
          header: { borderBottom: '1px solid #f0ece5', padding: '16px 20px' },
          body: { padding: 20 },
        }}
        title={
          <Space>
            <HeartOutlined style={{ color: health?.status === 'healthy' ? '#2d6a4f' : '#a52a2a' }} />
            <span className="serif-heading">服务健康状态</span>
            <Tag
              style={{
                border: 'none',
                background: health?.status === 'healthy' ? '#f0faf4' : '#fef2f2',
                color: health?.status === 'healthy' ? '#166534' : '#991b1b',
                fontWeight: 500,
              }}
            >
              {health?.status === 'healthy' ? 'Healthy' : 'Unhealthy'}
            </Tag>
          </Space>
        }
      >
        {health ? (
          <Descriptions column={{ xs: 1, sm: 2, md: 3 }} size="small" bordered>
            <Descriptions.Item label="LLM Model">
              <Tag style={{ background: '#e8eef4', color: '#1e3a5f', border: 'none' }}>{health.model}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="LLM Base URL">
              <Text code style={{ fontSize: 11, color: '#5c5c6e' }}>{health.llm.base_url_host}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="灵积">
              <Tag style={{
                border: 'none',
                background: health.llm.looks_like_dashscope ? '#f0faf4' : '#fef3c7',
                color: health.llm.looks_like_dashscope ? '#166534' : '#92400e',
              }}>
                {health.llm.looks_like_dashscope ? '是' : '否'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Embedding Provider">
              <Tag style={{ background: '#f5e6d0', color: '#92400e', border: 'none' }}>{health.embedding_provider}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="MySQL">
              <Space size={4}>
                {health.deps.mysql
                  ? <CheckCircleOutlined style={{ color: '#2d6a4f', fontSize: 12 }} />
                  : <CloseCircleOutlined style={{ color: '#a52a2a', fontSize: 12 }} />
                }
                <Text>{health.deps.mysql ? '已连接' : '未连接'}</Text>
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label="Redis">
              <Space size={4}>
                {health.deps.redis
                  ? <CheckCircleOutlined style={{ color: '#2d6a4f', fontSize: 12 }} />
                  : <CloseCircleOutlined style={{ color: '#a52a2a', fontSize: 12 }} />
                }
                <Text>{health.deps.redis ? '已连接' : '未连接'}</Text>
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label="Milvus">
              <Space size={4}>
                {health.deps.milvus
                  ? <CheckCircleOutlined style={{ color: '#2d6a4f', fontSize: 12 }} />
                  : <CloseCircleOutlined style={{ color: '#a52a2a', fontSize: 12 }} />
                }
                <Text>{health.deps.milvus ? '已连接' : '未连接'}</Text>
              </Space>
            </Descriptions.Item>
          </Descriptions>
        ) : (
          <Empty description="无法获取健康状态" />
        )}
      </Card>

      {/* ========== Agent Metrics ========== */}
      <Card
        className="animate-fade-in"
        style={{ marginBottom: 20, border: '1px solid #e8e0d5' }}
        styles={{
          header: { borderBottom: '1px solid #f0ece5', padding: '16px 20px' },
          body: { padding: 20 },
        }}
        title={
          <Space>
            <ThunderboltOutlined style={{ color: '#1e3a5f' }} />
            <span className="serif-heading">Agent 性能指标</span>
          </Space>
        }
      >
        {metrics?.agents ? (
          <Row gutter={[16, 16]} className="stagger">
            {Object.entries(metrics.agents).map(([name, stats]) => (
              <Col xs={24} sm={12} md={8} lg={6} key={name}>
                <div
                  style={{
                    background: '#fff',
                    borderRadius: 10,
                    padding: '16px 18px',
                    border: '1px solid #e8e0d5',
                    cursor: 'default',
                    transition: 'box-shadow 200ms cubic-bezier(0.16, 1, 0.3, 1)',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.boxShadow = '0 4px 16px rgba(26,26,46,0.06), 0 2px 4px rgba(26,26,46,0.03)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.boxShadow = 'none' }}
                >
                  <div style={{ marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                    {stats.success_rate >= 0.9
                      ? <CheckCircleOutlined style={{ color: '#2d6a4f', fontSize: 13 }} />
                      : <CloseCircleOutlined style={{ color: '#a52a2a', fontSize: 13 }} />
                    }
                    <Text style={{ fontSize: 12, fontWeight: 500, color: '#1a1a2e' }}>{name}</Text>
                  </div>
                  <div style={{ fontSize: 28, fontWeight: 700, color: stats.success_rate >= 0.9 ? '#2d6a4f' : '#a52a2a', fontFamily: "'Noto Serif SC', serif", lineHeight: 1.1 }}>
                    {(stats.success_rate * 100).toFixed(1)}%
                  </div>
                  <div style={{ marginTop: 10, display: 'flex', justifyContent: 'space-between', borderTop: '1px solid #f0ece5', paddingTop: 10 }}>
                    <div>
                      <Text type="secondary" style={{ fontSize: 10 }}>调用次数</Text>
                      <div><Text strong style={{ fontSize: 14 }}>{stats.total_calls}</Text></div>
                    </div>
                    <div>
                      <Text type="secondary" style={{ fontSize: 10 }}>平均延迟</Text>
                      <div><Text strong style={{ fontSize: 14 }}>{stats.avg_latency_ms.toFixed(0)} ms</Text></div>
                    </div>
                  </div>
                </div>
              </Col>
            ))}
          </Row>
        ) : (
          <Empty description="暂无 Agent 指标数据 — 提交推荐请求后自动生成" />
        )}
      </Card>

      {/* ========== A/B Experiments ========== */}
      <Card
        className="animate-fade-in"
        style={{ border: '1px solid #e8e0d5' }}
        styles={{
          header: { borderBottom: '1px solid #f0ece5', padding: '16px 20px' },
          body: { padding: 20 },
        }}
        title={
          <Space>
            <ExperimentOutlined style={{ color: '#2d5a8e' }} />
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
                  <Tag style={{
                    border: 'none',
                    background: exp.enabled ? '#f0faf4' : '#f0ece5',
                    color: exp.enabled ? '#166534' : '#8a8980',
                  }}>
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
                            <Tag style={{
                              border: 'none',
                              background: Number(rate) > 50 ? '#f0faf4' : '#fef2f2',
                              color: Number(rate) > 50 ? '#166534' : '#991b1b',
                            }}>
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
                    <div style={{ marginTop: 12 }}>
                      <Text type="secondary" style={{ fontSize: 11 }}>统计信息：</Text>
                      <pre style={{
                        fontSize: 11, background: '#faf8f5', padding: 10, borderRadius: 8, marginTop: 4,
                        border: '1px solid #e8e0d5', color: '#5c5c6e',
                      }}>
                        {JSON.stringify(exp.stats, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              ),
            }))}
          />
        ) : (
          <Empty description="暂无 A/B 实验数据" />
        )}
      </Card>
    </div>
  )
}
