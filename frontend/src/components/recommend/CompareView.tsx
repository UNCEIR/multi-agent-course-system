import { Card, Col, Collapse, Row, Space, Table, Tag, Tooltip, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  CheckCircleOutlined,
  CommentOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { PHASE_MAP, PRESET_QUERIES, PRESET_ICON_MAP } from './constants'
import PipelineTimeline from './PipelineTimeline'
import CourseCard from './CourseCard'
import type { RecommendationResponse } from '@/types'

const { Text } = Typography

interface CompareJob {
  id: string
  label: string
  prompt: string
  response: RecommendationResponse | null
  error: string | null
}

interface CompareViewProps {
  jobs: CompareJob[]
}

export default function CompareView({ jobs }: CompareViewProps) {
  const columns: ColumnsType<CompareJob> = [
    {
      title: '查询画像',
      dataIndex: 'label',
      key: 'label',
      width: 130,
      render: (_: string, record: CompareJob) => {
        const pq = PRESET_QUERIES.find((p) => record.label === p.label)
        return (
          <Space size={4}>
            <span aria-hidden="true">{pq ? PRESET_ICON_MAP[pq.icon] : null}</span>
            <Text strong style={{ fontSize: 13 }}>
              {record.label}
            </Text>
          </Space>
        )
      },
    },
    {
      title: '输入摘要',
      dataIndex: 'prompt',
      key: 'prompt',
      width: 190,
      render: (val: string) => (
        <Text ellipsis style={{ maxWidth: 170, fontSize: 11 }} type="secondary">
          {val}
        </Text>
      ),
    },
    {
      title: '推荐数',
      key: 'count',
      width: 70,
      align: 'center',
      render: (_: unknown, record: CompareJob) => (
        <Tag style={{ background: '#EAF2FB', color: '#16365C', border: 'none' }}>
          {record.response?.courses.length ?? 0}
        </Tag>
      ),
    },
    {
      title: 'Top 3 推荐',
      key: 'top',
      width: 200,
      render: (_: unknown, record: CompareJob) => (
        <Space orientation="vertical" size={1}>
          {record.response?.courses.slice(0, 3).map((c, i) => (
            <Text key={i} style={{ fontSize: 11 }} ellipsis>
              {i + 1}. {c.course_name}
            </Text>
          ))}
        </Space>
      ),
    },
    {
      title: '耗时',
      key: 'latency',
      width: 85,
      align: 'center',
      sorter: (a, b) =>
        (a.response?.total_latency_ms ?? 0) - (b.response?.total_latency_ms ?? 0),
      render: (_: unknown, record: CompareJob) => {
        const t = record.response?.total_latency_ms
        const label = t ? `${t.toFixed(0)} ms` : '-'
        return (
          <Tag
            style={{
              fontSize: 11,
              border: 'none',
              background: t && t < 3000 ? '#E6F7F3' : '#fef3c7',
              color: t && t < 3000 ? '#147D64' : '#B9772E',
            }}
            aria-label={label}
          >
            {label}
          </Tag>
        )
      },
    },
    {
      title: 'Agent 状态',
      key: 'agents',
      width: 140,
      render: (_: unknown, record: CompareJob) => {
        if (!record.response) return <Text type="secondary">-</Text>
        const agents = Object.values(record.response.agent_results)
        const ok = agents.filter((a) => a.success).length
        return (
          <Space size={3}>
            {agents.map((a) => (
              <Tooltip
                key={a.agent_name}
                title={`${PHASE_MAP[a.agent_name]?.label || a.agent_name}: ${a.latency_ms.toFixed(0)}ms`}
              >
                <CheckCircleOutlined
                  style={{
                    fontSize: 11,
                    color: a.success ? '#1FA88D' : '#D64545',
                  }}
                  aria-hidden="true"
                />
              </Tooltip>
            ))}
            <Text type="secondary" style={{ fontSize: 10, marginLeft: 2 }}>
              {ok}/{agents.length}
            </Text>
          </Space>
        )
      },
    },
    {
      title: '提醒',
      key: 'warnings',
      width: 55,
      align: 'center',
      render: (_: unknown, record: CompareJob) => {
        const n = record.response?.selection_warnings.length ?? 0
        return n > 0 ? (
          <Tag
            style={{ border: 'none', background: '#fef3c7', color: '#B9772E' }}
            aria-label={`${n} 条选课提醒`}
          >
            {n}
          </Tag>
        ) : (
          <Text type="secondary">0</Text>
        )
      },
    },
  ]

  return (
    <div>
      <div
        role="note"
        aria-label="批量对比说明"
        style={{
          marginBottom: 16,
          padding: '12px 16px',
          borderRadius: 8,
          background: '#EAF2FB',
          border: '1px solid #d0dce8',
        }}
      >
        <Text type="secondary" style={{ fontSize: 13 }}>
          <ThunderboltOutlined style={{ marginRight: 6, color: '#16365C' }} aria-hidden="true" />
          同时提交 <Text strong style={{ color: '#16365C' }}>5 组不同学生画像</Text> 的选课需求，对比多 Agent 系统的推荐差异 ——
          验证<Text strong>正确性、无幻觉、快速响应</Text>能力。
        </Text>
      </div>
      <Table
        dataSource={jobs}
        columns={columns}
        rowKey="id"
        pagination={false}
        size="middle"
        expandable={{
          expandedRowRender: (record) => (
            <div style={{ padding: '8px 0' }}>
              {record.response ? (
                <>
                  <PipelineTimeline
                    agentResults={record.response.agent_results}
                    totalLatency={record.response.total_latency_ms}
                  />
                  <Row gutter={[8, 8]}>
                    {record.response.courses.map((course) => (
                      <Col xs={24} sm={12} lg={8} key={course.course_id}>
                        <CourseCard course={course} />
                      </Col>
                    ))}
                  </Row>
                  {record.response.recommendation_reasons.length > 0 && (
                    <Collapse
                      style={{ marginTop: 12 }}
                      items={[{
                        key: 'reasons',
                        label: (
                          <Space>
                            <CommentOutlined aria-hidden="true" />
                            <Text strong style={{ fontSize: 12 }}>AI 推荐理由</Text>
                          </Space>
                        ),
                        children: (
                          <div style={{ maxHeight: 200, overflow: 'auto' }}>
                            {record.response.recommendation_reasons.map((reason, i) => (
                              <Card key={i} size="small" style={{ marginBottom: 8 }}>
                                {Object.entries(reason).map(([k, v]) => (
                                  <div key={k} style={{ marginBottom: 2 }}>
                                    <Text strong style={{ fontSize: 11 }}>{k}: </Text>
                                    <Text style={{ fontSize: 11 }}>{v}</Text>
                                  </div>
                                ))}
                              </Card>
                            ))}
                          </div>
                        ),
                      }]}
                    />
                  )}
                </>
              ) : (
                <Text type="danger">{record.error}</Text>
              )}
            </div>
          ),
          rowExpandable: (record) => !!record.response,
        }}
      />
    </div>
  )
}
