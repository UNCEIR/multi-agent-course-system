// Phase 4 E4：think→act→observe 三阶段可视化（chat 消费链）。
// act = 工具 start；observe = 工具 end（附 result 摘要）。thinking 缺省不渲染。
'use client'

import { ToolOutlined, CheckCircleOutlined, LoadingOutlined } from '@ant-design/icons'
import { Space, Tag, Typography } from 'antd'

const { Text } = Typography

export interface ToolActivity {
  name: string
  status: 'start' | 'end'
  result?: string
}

interface Props {
  tools: ToolActivity[]
}

export default function AgentActivityTimeline({ tools }: Props) {
  if (!tools || tools.length === 0) return null
  return (
    <Space direction="vertical" size={4} style={{ width: '100%', marginTop: 8 }}>
      {tools.map((t, i) => {
        const observing = t.status === 'end'
        return (
          <Space key={`${t.name}-${i}`} size={6} wrap>
            <Tag
              icon={observing ? <CheckCircleOutlined /> : <LoadingOutlined />}
              color={observing ? 'green' : 'processing'}
            >
              {t.name}
            </Tag>
            {observing ? <Text type="secondary" style={{ fontSize: 12 }}>observe</Text> : <Text type="secondary" style={{ fontSize: 12 }}>act</Text>}
            {observing && t.result ? (
              <Text type="secondary" style={{ fontSize: 12, wordBreak: 'break-all' }} ellipsis={{ tooltip: t.result }}>
                {t.result.length > 120 ? `${t.result.slice(0, 120)}…` : t.result}
              </Text>
            ) : (
              <ToolOutlined style={{ fontSize: 12, color: '#8CA3C0' }} />
            )}
          </Space>
        )
      })}
    </Space>
  )
}
