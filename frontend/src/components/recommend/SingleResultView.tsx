import { Card, Col, Collapse, Empty, Row, Space, Tag, Typography } from 'antd'
import {
  BookOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CommentOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { getWarningLevel } from '@/lib/warningLevel'
import StatCard from './StatCard'
import PipelineTimeline from './PipelineTimeline'
import CourseCard from './CourseCard'
import type { RecommendationResponse } from '@/types'

const { Text, Title } = Typography

interface SingleResultViewProps {
  response: RecommendationResponse
}

export default function SingleResultView({ response }: SingleResultViewProps) {
  const successfulAgents = Object.values(response.agent_results).filter((a) => a.success).length
  const totalAgents = Object.keys(response.agent_results).length

  return (
    <div className="animate-fade-in" aria-labelledby="single-result-heading">
      <h2 id="single-result-heading" className="sr-only">
        经典模式推荐结果
      </h2>

      {/* Stats Row */}
      <Row gutter={16} className="stagger" style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}>
          <StatCard
            icon={<ClockCircleOutlined aria-hidden="true" />}
            title="总耗时"
            value={`${response.total_latency_ms.toFixed(0)} ms`}
            color={response.total_latency_ms < 3000 ? '#1FA88D' : '#14B8A6'}
          />
        </Col>
        <Col xs={12} sm={6}>
          <StatCard
            icon={<BookOutlined aria-hidden="true" />}
            title="推荐课程"
            value={`${response.courses.length} 门`}
            color="#16365C"
          />
        </Col>
        <Col xs={12} sm={6}>
          <StatCard
            icon={<CheckCircleOutlined aria-hidden="true" />}
            title="可用 Agent"
            value={`${successfulAgents}/${totalAgents}`}
            color="#1FA88D"
          />
        </Col>
        <Col xs={12} sm={6}>
          <StatCard
            icon={<WarningOutlined aria-hidden="true" />}
            title="选课提醒"
            value={`${response.selection_warnings.length} 条`}
            color={response.selection_warnings.length > 0 ? '#14B8A6' : '#6B7A8D'}
          />
        </Col>
      </Row>

      {/* Pipeline Timeline */}
      <PipelineTimeline agentResults={response.agent_results} totalLatency={response.total_latency_ms} />

      {/* Course Cards */}
      <Title
        level={5}
        className="serif-heading"
        style={{ marginTop: 28, marginBottom: 16, color: '#16365C' }}
      >
        <BookOutlined style={{ marginRight: 6, color: '#14B8A6' }} aria-hidden="true" />
        推荐课程列表
      </Title>
      {response.courses.length === 0 ? (
        <Empty description="未找到匹配的课程" />
      ) : (
        <Row gutter={[12, 12]} className="stagger">
          {response.courses.map((course, i) => (
            <Col xs={24} sm={12} lg={8} key={course.course_id}>
              <CourseCard course={course} index={i} />
            </Col>
          ))}
        </Row>
      )}

      {/* Reasons & Warnings */}
      <div className="stagger" style={{ marginTop: 20 }}>
        {response.recommendation_reasons.length > 0 && (
          <Collapse
            style={{ marginBottom: 12 }}
            items={[{
              key: 'reasons',
              label: (
                <Space>
                  <CommentOutlined style={{ color: '#14B8A6' }} aria-hidden="true" />
                  <Text strong className="serif-heading">AI 推荐理由</Text>
                  <Tag style={{ background: '#E0F5F2', color: '#B9772E', border: 'none' }}>
                    {response.recommendation_reasons.length} 条
                  </Tag>
                </Space>
              ),
              children: (
                <div style={{ maxHeight: 340, overflow: 'auto' }}>
                  {response.recommendation_reasons.map((reason, i) => (
                    <Card key={i} size="small" style={{ marginBottom: 8 }}>
                      {Object.entries(reason).map(([k, v]) => (
                        <div key={k} style={{ marginBottom: 4 }}>
                          <Text strong style={{ fontSize: 13 }}>{k}：</Text>
                          <Text style={{ fontSize: 13 }}>{v}</Text>
                        </div>
                      ))}
                    </Card>
                  ))}
                </div>
              ),
            }]}
          />
        )}
        {response.selection_warnings.length > 0 && (
          <Collapse
            style={{ marginBottom: 12 }}
            items={[{
              key: 'warnings',
              label: (
                <Space>
                  <WarningOutlined style={{ color: '#14B8A6' }} aria-hidden="true" />
                  <Text strong className="serif-heading" style={{ color: '#B9772E' }}>
                    选课可行性提醒
                  </Text>
                  <Tag style={{ background: '#fef3c7', color: '#B9772E', border: 'none' }}>
                    {response.selection_warnings.length} 条
                  </Tag>
                </Space>
              ),
              children: (
                <div style={{ maxHeight: 340, overflow: 'auto' }}>
                  {response.selection_warnings.map((w, i) => {
                    const lvl = getWarningLevel(w.level)
                    const courseName = String(w.course_name || w.course_id || '')
                    const message = String(w.message || '')
                    return (
                      <Card key={i} size="small" style={{ marginBottom: 8 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                          <Text strong style={{ fontSize: 13 }}>{courseName}</Text>
                          {typeof w.level === 'string' && (
                            <Tag
                              style={{
                                fontSize: 11,
                                border: 'none',
                                background: lvl.bg,
                                color: lvl.color,
                              }}
                              aria-label={`风险等级：${lvl.label}`}
                            >
                              {lvl.label}
                            </Tag>
                          )}
                        </div>
                        <Text style={{ fontSize: 13, color: '#6B7A8D' }}>{message}</Text>
                      </Card>
                    )
                  })}
                </div>
              ),
            }]}
          />
        )}
      </div>

      {/* Raw Response (ghost) */}
      <Collapse
        ghost
        style={{ marginTop: 16 }}
        items={[{
          key: 'raw',
          label: <Text type="secondary" style={{ fontSize: 11 }}>查看原始响应数据</Text>,
          children: (
            <pre style={{
              fontSize: 11, maxHeight: 300, overflow: 'auto', background: '#EAF3FC',
              padding: 14, borderRadius: 8, border: '1px solid #CFE3F5', color: '#6B7A8D',
            }}>
              {JSON.stringify(response, null, 2)}
            </pre>
          ),
        }]}
      />
    </div>
  )
}
