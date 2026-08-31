'use client'

import { Tooltip } from 'antd'
import { StarOutlined } from '@ant-design/icons'

import type { Course } from '@/types'
import CourseFields from './CourseFields'

interface Props {
  course: Course
  index: number
}

export default function CourseInlineCard({ course, index }: Props) {
  // 路 1 a11y 升级：与 recommend/CourseCard 的 aria-label 文案对齐，便于屏幕阅读器朗读
  const ariaLabel = `第 ${index + 1} 门课程：${course.course_name}，${course.teacher || '待定'}，${course.credits} 学分`
  return (
    <div
      className="card-slide-in"
      role="group"
      aria-label={ariaLabel}
      style={{
        background: '#fff',
        borderRadius: 12,
        border: '1px solid #CFE3F5',
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
        e.currentTarget.style.borderColor = '#CFE3F5'
      }}
    >
      {/* Header row：序号 + 课程名 + 评分 Tooltip（CourseInlineCard 独有，CourseFields 不含） */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span
            aria-hidden="true"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 28,
              height: 28,
              borderRadius: 8,
              background: 'linear-gradient(135deg, #16365C, #2E6FBF)',
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
              color: '#16365C',
            }}
          >
            {course.course_name}
          </span>
        </div>
        {course.score > 0 && (
          <Tooltip title="综合评分">
            <span style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 13, color: '#14B8A6' }}>
              <StarOutlined style={{ fontSize: 11 }} aria-hidden="true" />
              <span style={{ fontWeight: 600 }}>{course.score.toFixed(1)}</span>
            </span>
          </Tooltip>
        )}
      </div>

      {/* 共享字段渲染（路 7 抽取） */}
      <CourseFields course={course} variant="inline" />
    </div>
  )
}
