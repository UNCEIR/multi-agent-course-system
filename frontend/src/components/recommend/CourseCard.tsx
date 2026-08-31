import { Card, Space, Tag, Tooltip, Typography } from 'antd'
import { StarOutlined } from '@ant-design/icons'
import type { Course } from '@/types'
import CourseFields from '../CourseFields'

const { Text } = Typography

interface CourseCardProps {
  course: Course
  index?: number
}

export default function CourseCard({ course, index }: CourseCardProps) {
  const ariaLabel = index !== undefined
    ? `第 ${index + 1} 门课程：${course.course_name}，${course.teacher || '待定'}，${course.credits} 学分`
    : `课程：${course.course_name}`

  return (
    <Card
      size="small"
      hoverable
      className="animate-fade-scale"
      style={{ cursor: 'pointer' }}
      styles={{
        header: { borderBottom: '1px solid #EAF2FB', padding: '12px 16px' },
        body: { padding: '14px 16px' },
      }}
      aria-label={ariaLabel}
      title={
        <Tooltip title={course.course_name}>
          <Text strong ellipsis style={{ maxWidth: 190, fontSize: 13 }}>
            {course.course_name}
          </Text>
        </Tooltip>
      }
      extra={
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <StarOutlined style={{ color: '#14B8A6', fontSize: 11 }} aria-hidden="true" />
          <Text strong style={{ fontSize: 13, color: '#16365C' }}>
            {course.score.toFixed(1)}
          </Text>
        </div>
      }
    >
      {/* 共享字段渲染（路 7 抽取） */}
      <CourseFields course={course} variant="card" />

      {/* 匹配理由 chips：CourseCard 独有（流式卡片不展示，避免每 token 重渲染） */}
      {course.match_reasons.length > 0 && (
        <div
          style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid #EAF2FB' }}
          aria-label={`匹配理由：${course.match_reasons.slice(0, 3).join('；')}`}
        >
          <Text type="secondary" style={{ fontSize: 10 }}>
            匹配理由
          </Text>
          <div style={{ marginTop: 4 }}>
            <Space size={[3, 3]} wrap>
              {course.match_reasons.slice(0, 3).map((r, i) => (
                <Tag
                  key={i}
                  style={{
                    fontSize: 10,
                    background: '#EAF2FB',
                    color: '#16365C',
                    border: 'none',
                    maxWidth: 160,
                  }}
                >
                  <Text ellipsis style={{ fontSize: 10 }}>
                    {r}
                  </Text>
                </Tag>
              ))}
            </Space>
          </div>
        </div>
      )}
    </Card>
  )
}
