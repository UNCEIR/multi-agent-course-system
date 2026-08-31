import { Space, Tag, Tooltip, Typography } from 'antd'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExperimentOutlined,
} from '@ant-design/icons'
import { PHASE_MAP } from './constants'
import type { AgentResult } from '@/types'

const { Text } = Typography

interface PipelineTimelineProps {
  agentResults: Record<string, AgentResult>
  totalLatency: number
}

interface PhaseRow {
  phase: number
  label: string
  sub: string
  color: string
  agents: string[]
}

const PHASE_ROWS: PhaseRow[] = [
  {
    phase: 1,
    label: 'Phase 1 — 并行',
    sub: '画像 + 召回',
    color: '#16365C',
    agents: ['student_profile', 'course_recall'],
  },
  {
    phase: 2,
    label: 'Phase 2 — 并行',
    sub: '重排 + 可行性',
    color: '#2E6FBF',
    agents: ['course_rerank', 'course_feasibility'],
  },
  {
    phase: 3,
    label: 'Phase 3 — 串行',
    sub: '推荐理由生成',
    color: '#1FA88D',
    agents: ['recommendation_reason'],
  },
]

export default function PipelineTimeline({
  agentResults,
  totalLatency,
}: PipelineTimelineProps) {
  return (
    <section
      aria-labelledby="pipeline-timeline-heading"
      style={{ marginBottom: 24 }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginBottom: 14,
        }}
      >
        <ExperimentOutlined style={{ color: '#14B8A6' }} aria-hidden="true" />
        <Text
          id="pipeline-timeline-heading"
          strong
          className="serif-heading"
          style={{ fontSize: 14 }}
        >
          Agent 流水线执行过程
        </Text>
      </div>
      <div
        style={{
          display: 'flex',
          gap: 10,
          flexWrap: 'wrap',
          alignItems: 'stretch',
        }}
      >
        {PHASE_ROWS.map((phase) => (
          <div
            key={phase.phase}
            className="stagger"
            style={{
              flex: 1,
              minWidth: 190,
              borderRadius: 10,
              padding: 14,
              background: `${phase.color}06`,
              border: `1px solid ${phase.color}18`,
            }}
          >
            <div style={{ marginBottom: 10 }}>
              <div
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: phase.color,
                  marginBottom: 2,
                }}
              >
                {phase.label}
              </div>
              <div style={{ fontSize: 11, color: '#8a8980' }}>{phase.sub}</div>
            </div>
            {phase.agents.map((agentName) => {
              const agent = agentResults[agentName]
              if (!agent) return null
              const info = PHASE_MAP[agentName]
              const statusLabel = agent.success ? '成功' : '失败'
              return (
                <div
                  key={agentName}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '6px 10px',
                    marginBottom: 6,
                    borderRadius: 6,
                    background: agent.success ? '#E6F7F3' : '#FDECEC',
                    border: `1px solid ${agent.success ? '#c6f0d7' : '#fecaca'}`,
                    cursor: 'default',
                    transition: 'box-shadow 180ms',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.boxShadow = `0 2px 8px ${phase.color}12`
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.boxShadow = 'none'
                  }}
                  role="group"
                  aria-label={`${info?.label || agent.agent_name}：${statusLabel}，耗时 ${agent.latency_ms.toFixed(0)} 毫秒`}
                >
                  <Space size={4}>
                    {agent.success ? (
                      <CheckCircleOutlined
                        style={{ color: '#1FA88D', fontSize: 13 }}
                        aria-hidden="true"
                      />
                    ) : (
                      <CloseCircleOutlined
                        style={{ color: '#D64545', fontSize: 13 }}
                        aria-hidden="true"
                      />
                    )}
                    <span
                      style={{
                        fontSize: 12,
                        maxWidth: 72,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {info?.label || agent.agent_name}
                    </span>
                  </Space>
                  <Tooltip
                    title={`耗时 ${agent.latency_ms.toFixed(0)}ms · 置信度 ${(agent.confidence * 100).toFixed(0)}%`}
                  >
                    <Tag
                      style={{
                        fontSize: 10,
                        margin: 0,
                        border: 'none',
                        background: agent.success ? '#d1fae5' : '#fee2e2',
                        color: agent.success ? '#147D64' : '#C0392B',
                      }}
                      aria-hidden="true"
                    >
                      {agent.latency_ms.toFixed(0)} ms
                    </Tag>
                  </Tooltip>
                </div>
              )
            })}
          </div>
        ))}
        <div
          style={{
            minWidth: 90,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: 10,
            border: '1px solid #CFE3F5',
            background: '#EAF3FC',
            padding: 14,
          }}
          className="animate-slide-right"
          role="status"
          aria-label={`总耗时 ${totalLatency.toFixed(0)} 毫秒`}
        >
          <Text
            type="secondary"
            style={{
              fontSize: 10,
              letterSpacing: '0.05em',
              textTransform: 'uppercase',
            }}
          >
            总耗时
          </Text>
          <Text
            strong
            style={{
              fontSize: 24,
              color: '#16365C',
              fontFamily: "'Noto Serif SC', serif",
              lineHeight: 1.2,
            }}
          >
            {totalLatency.toFixed(0)}
          </Text>
          <Text type="secondary" style={{ fontSize: 10 }}>
            ms
          </Text>
        </div>
      </div>
    </section>
  )
}
