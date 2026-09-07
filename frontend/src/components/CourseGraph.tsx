// Phase 4 E2：课程图谱 nodes/edges 渲染（轻量，不依赖图表库）。
// nodes: {id, type: course|domain|prerequisite, label}；edges: {source, target, relation}
'use client'

import { ApartmentOutlined, BookOutlined, FlagOutlined, ProjectOutlined } from '@ant-design/icons'
import { Empty, Space, Tag, Typography } from 'antd'

const { Text } = Typography

export interface CourseGraphNode {
  id: string
  type: 'course' | 'domain' | 'prerequisite'
  label: string
}

export interface CourseGraphEdge {
  source: string
  target: string
  relation: 'prerequisite' | 'domain_of' | 'related'
}

interface Props {
  nodes?: CourseGraphNode[]
  edges?: CourseGraphEdge[]
}

const ICONS = {
  course: BookOutlined,
  domain: FlagOutlined,
  prerequisite: ProjectOutlined,
}

const COLORS = {
  course: 'blue',
  domain: 'purple',
  prerequisite: 'orange',
} as const

export default function CourseGraph({ nodes = [], edges = [] }: Props) {
  if (!nodes.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无课程图谱数据" />
  }
  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <Space size={6}>
        <ApartmentOutlined />
        <Text strong style={{ fontSize: 13 }}>课程图谱（{nodes.length} 节点 / {edges.length} 关系）</Text>
      </Space>
      <Space wrap size={6}>
        {nodes.map((n) => {
          const Icon = ICONS[n.type] ?? BookOutlined
          return (
            <Tag key={n.id} icon={<Icon />} color={COLORS[n.type] ?? 'default'}>
              {n.label}
            </Tag>
          )
        })}
      </Space>
      {edges.length > 0 && (
        <Space direction="vertical" size={2}>
          {edges.map((e, i) => (
            <Text key={i} type="secondary" style={{ fontSize: 12 }}>
              {e.source.split(':')[1] ?? e.source} → {e.target.split(':')[1] ?? e.target}（{e.relation}）
            </Text>
          ))}
        </Space>
      )}
    </Space>
  )
}
