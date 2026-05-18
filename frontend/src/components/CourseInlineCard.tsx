import { Tag, Tooltip } from 'antd'
import {
  BookOutlined,
  EnvironmentOutlined,
  FieldTimeOutlined,
  StarOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import type { Course } from '../types'

const DIFFICULTY_COLORS: Record<string, string> = {
  '高': '#a52a2a', '中': '#c88c3e', '低': '#2d6a4f',
}

interface Props {
  course: Course
  index: number
}

export default function CourseInlineCard({ course, index }: Props) {
  return (
    <div
      className="card-slide-in"
      style={{
        background: '#fff',
        borderRadius: 12,
        border: '1px solid #e8e0d5',
        padding: '14px 18px',
        marginTop: 8,
        marginBottom: 14,
        boxShadow: '0 2px 8px rgba(26,26,46,0.04)',
        transition: 'box-shadow 200ms cubic-bezier(0.16, 1, 0.3, 1)',
        cursor: 'default',
        animationDelay: `${index * 0.06}s`,
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.boxShadow = '0 4px 20px rgba(26,26,46,0.08), 0 2px 4px rgba(26,26,46,0.04)'
        e.currentTarget.style.borderColor = '#d0c8b8'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.boxShadow = '0 2px 8px rgba(26,26,46,0.04)'
        e.currentTarget.style.borderColor = '#e8e0d5'
      }}
    >
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 28,
              height: 28,
              borderRadius: 8,
              background: 'linear-gradient(135deg, #1e3a5f, #2d5a8e)',
              color: '#fff',
              fontSize: 13,
              fontWeight: 700,
              fontFamily: "'Noto Serif SC', serif",
            }}
          >
            {index + 1}
          </span>
          <span
            style={{
              fontSize: 15,
              fontWeight: 600,
              fontFamily: "'Noto Serif SC', serif",
              color: '#1a1a2e',
            }}
          >
            {course.course_name}
          </span>
        </div>
        {course.score > 0 && (
          <Tooltip title="综合评分">
            <span style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 13, color: '#c88c3e' }}>
              <StarOutlined style={{ fontSize: 11 }} />
              <span style={{ fontWeight: 600 }}>{course.score.toFixed(1)}</span>
            </span>
          </Tooltip>
        )}
      </div>

      {/* Info row */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
        {course.teacher && (
          <span style={{ fontSize: 12, color: '#5c5c6e', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <TeamOutlined style={{ fontSize: 10 }} />
            {course.teacher}
          </span>
        )}
        {course.credits > 0 && (
          <span style={{ fontSize: 12, color: '#8a8980' }}>
            <BookOutlined style={{ fontSize: 10, marginRight: 2 }} />
            {course.credits}学分
          </span>
        )}
        {course.campus && (
          <span style={{ fontSize: 12, color: '#8a8980' }}>
            <EnvironmentOutlined style={{ fontSize: 10, marginRight: 2 }} />
            {course.campus}
          </span>
        )}
        {course.time_slot && (
          <span style={{ fontSize: 12, color: '#8a8980' }}>
            <FieldTimeOutlined style={{ fontSize: 10, marginRight: 2 }} />
            {course.time_slot}
          </span>
        )}
      </div>

      {/* Tags row */}
      <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {course.domain && (
          <Tag style={{ fontSize: 10, background: '#f5e6d0', color: '#92400e', border: 'none', margin: 0 }}>
            {course.domain}
          </Tag>
        )}
        {course.course_category && course.course_category !== course.domain && (
          <Tag style={{ fontSize: 10, background: '#e8eef4', color: '#1e3a5f', border: 'none', margin: 0 }}>
            {course.course_category}
          </Tag>
        )}
        {course.difficulty && (
          <Tag style={{ fontSize: 10, background: `${DIFFICULTY_COLORS[course.difficulty] || '#8a8980'}12`, color: DIFFICULTY_COLORS[course.difficulty] || '#8a8980', border: 'none', margin: 0 }}>
            难度{course.difficulty}
          </Tag>
        )}
        {course.workload && (
          <Tag style={{ fontSize: 10, background: '#f0ece5', color: '#5c5c6e', border: 'none', margin: 0 }}>
            作业{course.workload}
          </Tag>
        )}
        {course.grade_friendly && (
          <Tag style={{ fontSize: 10, background: '#f0faf4', color: '#166534', border: 'none', margin: 0 }}>
            给分{course.grade_friendly}
          </Tag>
        )}
        <Tag style={{
          fontSize: 10, border: 'none', margin: 0,
          background: course.has_exam === 1 ? '#fef2f2' : '#f0faf4',
          color: course.has_exam === 1 ? '#991b1b' : '#166534',
        }}>
          {course.has_exam === 1 ? '有考试' : '无考试'}
        </Tag>
        {course.popularity_level >= 3 && (
          <Tag style={{ fontSize: 10, background: '#fef3c7', color: '#92400e', border: 'none', margin: 0 }}>
            {course.popularity_level >= 4 ? '爆满' : '热门'}
          </Tag>
        )}
      </div>
    </div>
  )
}
