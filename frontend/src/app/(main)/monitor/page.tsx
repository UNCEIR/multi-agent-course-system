'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  Card,
  Descriptions,
  Tag,
  Row,
  Col,
  Button,
  Spin,
  Empty,
  Space,
  Typography,
} from 'antd'
import {
  HeartOutlined,
  DashboardOutlined,
  ReloadOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { api } from '../../../lib/api'
import type { HealthResponse, MetricsResponse } from '../../../types'

const { Text, Title } = Typography

export default function MonitorPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null)
  const [promText, setPromText] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [h, m] = await Promise.all([api.health(), api.getMetrics()])
      setHealth(h)
      setMetrics(m)
      try {
        const text = await api.getPrometheusText()
        setPromText(text.slice(0, 2000))
      } catch {
        setPromText(null)
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '获取监控数据失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
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
          <DashboardOutlined style={{ color: '#14B8A6', fontSize: 20 }} />
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

      {promText && (
        <Card
          style={{ marginBottom: 20, border: '1px solid #E8E5DA' }}
          title={<Space><ThunderboltOutlined /><span className="serif-heading">Prometheus 原始指标（/metrics）</span></Space>}
        >
          <pre style={{ fontSize: 11, color: '#4A5568', maxHeight: 240, overflow: 'auto', whiteSpace: 'pre-wrap' }}>
            {promText}
          </pre>
        </Card>
      )}

      {error && (
        <Card style={{ marginBottom: 20, background: '#FDECEC', border: '1px solid #fecaca', borderRadius: 10 }}>
          <Space>
            <CloseCircleOutlined style={{ color: '#D64545' }} />
            <Text type="danger">{error}</Text>
          </Space>
        </Card>
      )}

      {/* ========== Health ========== */}
      <Card
        className="animate-fade-scale"
        style={{ marginBottom: 20, border: '1px solid #CFE3F5' }}
        styles={{
          header: { borderBottom: '1px solid #EAF2FB', padding: '16px 20px' },
          body: { padding: 20 },
        }}
        title={
          <Space>
            <HeartOutlined style={{ color: health?.status === 'healthy' ? '#1FA88D' : '#D64545' }} />
            <span className="serif-heading">服务健康状态</span>
            <Tag
              style={{
                border: 'none',
                background: health?.status === 'healthy' ? '#E6F7F3' : '#FDECEC',
                color: health?.status === 'healthy' ? '#147D64' : '#C0392B',
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
              <Tag style={{ background: '#EAF2FB', color: '#16365C', border: 'none' }}>{health.model}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="LLM Base URL">
              <Text code style={{ fontSize: 11, color: '#6B7A8D' }}>{health.llm.base_url_host}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="灵积">
              <Tag style={{
                border: 'none',
                background: health.llm.looks_like_dashscope ? '#E6F7F3' : '#fef3c7',
                color: health.llm.looks_like_dashscope ? '#147D64' : '#B9772E',
              }}>
                {health.llm.looks_like_dashscope ? '是' : '否'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Embedding Provider">
              <Tag style={{ background: '#E0F5F2', color: '#B9772E', border: 'none' }}>{health.embedding_provider}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="MySQL">
              <Space size={4}>
                {health.deps.mysql
                  ? <CheckCircleOutlined style={{ color: '#1FA88D', fontSize: 12 }} />
                  : <CloseCircleOutlined style={{ color: '#D64545', fontSize: 12 }} />
                }
                <Text>{health.deps.mysql ? '已连接' : '未连接'}</Text>
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label="Redis">
              <Space size={4}>
                {health.deps.redis
                  ? <CheckCircleOutlined style={{ color: '#1FA88D', fontSize: 12 }} />
                  : <CloseCircleOutlined style={{ color: '#D64545', fontSize: 12 }} />
                }
                <Text>{health.deps.redis ? '已连接' : '未连接'}</Text>
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label="Milvus">
              <Space size={4}>
                {health.deps.milvus
                  ? <CheckCircleOutlined style={{ color: '#1FA88D', fontSize: 12 }} />
                  : <CloseCircleOutlined style={{ color: '#D64545', fontSize: 12 }} />
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
        style={{ marginBottom: 20, border: '1px solid #CFE3F5' }}
        styles={{
          header: { borderBottom: '1px solid #EAF2FB', padding: '16px 20px' },
          body: { padding: 20 },
        }}
        title={
          <Space>
            <ThunderboltOutlined style={{ color: '#16365C' }} />
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
                    border: '1px solid #CFE3F5',
                    cursor: 'default',
                    transition: 'box-shadow 200ms cubic-bezier(0.16, 1, 0.3, 1)',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.boxShadow = '0 4px 16px rgba(26,26,46,0.06), 0 2px 4px rgba(26,26,46,0.03)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.boxShadow = 'none' }}
                >
                  <div style={{ marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                    {stats.success_rate >= 0.9
                      ? <CheckCircleOutlined style={{ color: '#1FA88D', fontSize: 13 }} />
                      : <CloseCircleOutlined style={{ color: '#D64545', fontSize: 13 }} />
                    }
                    <Text style={{ fontSize: 12, fontWeight: 500, color: '#16365C' }}>{name}</Text>
                  </div>
                  <div style={{ fontSize: 28, fontWeight: 700, color: stats.success_rate >= 0.9 ? '#1FA88D' : '#D64545', fontFamily: "'Noto Serif SC', serif", lineHeight: 1.1 }}>
                    {(stats.success_rate * 100).toFixed(1)}%
                  </div>
                  <div style={{ marginTop: 10, display: 'flex', justifyContent: 'space-between', borderTop: '1px solid #EAF2FB', paddingTop: 10 }}>
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
    </div>
  )
}
