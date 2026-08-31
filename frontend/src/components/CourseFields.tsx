'use client'

import { Space, Tag, Typography } from 'antd'
import {
  BookOutlined,
  EnvironmentOutlined,
  FieldTimeOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import { DIFFICULTY_COLORS } from './recommend/constants'
import type { Course } from '@/types'

const { Text } = Typography

/**
 * 路 7：CourseFields —— 流式 + 静态两个课程卡片的共享字段渲染层。
 *
 * 抽取动机（参见 docs/v2.0.0/frontend-architecture.md）：
 * - components/CourseInlineCard.tsx 与 components/recommend/CourseCard.tsx 字段重叠 ~80%
 * - 两份维护成本高（路 6 已暴露 a11y 行为漂移风险）
 *
 * 设计边界：
 * - CourseFields 只负责"字段 + tags"渲染，**不含外层容器**（div / antd Card）
 * - **不含 a11y 语义标记**（role/aria-label）—— 这些由父组件根据容器类型决定
 * - **不含独有字段**：序号（CourseInlineCard 独有）、match_reasons（CourseCard 独有）、评分 Tooltip（CourseInlineCard 独有）
 *
 * variant 决定样式风格而非字段差异：
 * - 'inline'：流式场景，每 token 重渲染——扁平 flexWrap，信息密集
 * - 'card'：静态场景，结果页——分组（teacher/学分 + 校区/时间），更易扫读
 */

export type CourseFieldsVariant = 'inline' | 'card'

export interface CourseFieldsProps {
  course: Course
  variant?: CourseFieldsVariant
}

const ICON_STYLE = { fontSize: 10 }

export default function CourseFields({ course, variant = 'card' }: CourseFieldsProps) {
  // inline 风格：扁平 flexWrap（流式输出密集渲染）
  if (variant === 'inline') {
    return (
      <>
        <div
          style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}
          aria-label="课程基本信息"
        >
          {course.teacher && (
            <span
              style={{
                fontSize: 12,
                color: '#6B7A8D',
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
              }}
            >
              <TeamOutlined style={ICON_STYLE} aria-hidden="true" />
              {course.teacher}
            </span>
          )}
          {course.credits > 0 && (
            <span style={{ fontSize: 12, color: '#8a8980' }}>
              <BookOutlined style={ICON_STYLE} aria-hidden="true" />
              {course.credits}学分
            </span>
          )}
          {course.campus && (
            <span style={{ fontSize: 12, color: '#8a8980' }}>
              <EnvironmentOutlined style={ICON_STYLE} aria-hidden="true" />
              {course.campus}
            </span>
          )}
          {course.time_slot && (
            <span style={{ fontSize: 12, color: '#8a8980' }}>
              <FieldTimeOutlined style={ICON_STYLE} aria-hidden="true" />
              {course.time_slot}
            </span>
          )}
        </div>

        <TagsBlock course={course} />
      </>
    )
  }

  // card 风格：分组（teacher/学分 + 校区/时间）+ Space wrap tags
  return (
    <div style={{ fontSize: 12, lineHeight: '22px' }}>
      <div
        style={{ marginBottom: 4, display: 'flex', gap: 12 }}
        aria-label="授课信息"
      >
        {course.teacher !== undefined && (
          <span>
            <TeamOutlined style={{ color: '#8a8980', ...ICON_STYLE }} aria-hidden="true" />
            <Text type="secondary">{course.teacher || '待定'}</Text>
          </span>
        )}
        {course.credits > 0 && (
          <span>
            <BookOutlined
              style={{ color: '#8a8980', ...ICON_STYLE, marginRight: 2 }}
              aria-hidden="true"
            />
            <Text type="secondary">{course.credits} 学分</Text>
          </span>
        )}
      </div>

      <div
        style={{ marginBottom: 4 }}
        aria-label="分类"
      >
        {course.domain && (
          <Tag
            style={{
              fontSize: 10,
              background: '#E0F5F2',
              color: '#B9772E',
              border: 'none',
            }}
          >
            {course.domain}
          </Tag>
        )}
        {course.course_category && course.course_category !== course.domain && (
          <Tag
            style={{
              fontSize: 10,
              background: '#EAF2FB',
              color: '#16365C',
              border: 'none',
              marginLeft: 4,
            }}
          >
            {course.course_category}
          </Tag>
        )}
      </div>

      <div
        style={{ marginBottom: 4, display: 'flex', gap: 12 }}
        aria-label="时间地点"
      >
        {course.time_slot && (
          <span>
            <FieldTimeOutlined
              style={{ color: '#8a8980', ...ICON_STYLE, marginRight: 2 }}
              aria-hidden="true"
            />
            <Text type="secondary">{course.time_slot}</Text>
          </span>
        )}
        {course.campus && (
          <span>
            <EnvironmentOutlined
              style={{ color: '#8a8980', ...ICON_STYLE, marginRight: 2 }}
              aria-hidden="true"
            />
            <Text type="secondary">{course.campus}</Text>
          </span>
        )}
      </div>

      <Space size={4} wrap style={{ marginBottom: 4 }} aria-label="课程标签">
        {course.difficulty && (
          <Tag
            style={{
              fontSize: 10,
              background: `${DIFFICULTY_COLORS[course.difficulty] || '#8a8980'}12`,
              color: DIFFICULTY_COLORS[course.difficulty] || '#8a8980',
              border: 'none',
            }}
          >
            难度 {course.difficulty}
          </Tag>
        )}
        {course.workload && (
          <Tag
            style={{
              fontSize: 10,
              background: '#EAF2FB',
              color: '#6B7A8D',
              border: 'none',
            }}
          >
            作业 {course.workload}
          </Tag>
        )}
        {course.grade_friendly && (
          <Tag
            style={{
              fontSize: 10,
              background: '#E6F7F3',
              color: '#147D64',
              border: 'none',
            }}
          >
            给分 {course.grade_friendly}
          </Tag>
        )}
        {(course.has_exam === 0 || course.has_exam === 1) && (
          <Tag
            style={{
              fontSize: 10,
              border: 'none',
              background: course.has_exam === 1 ? '#FDECEC' : '#E6F7F3',
              color: course.has_exam === 1 ? '#C0392B' : '#147D64',
            }}
            aria-label={course.has_exam === 1 ? '有考试' : '无考试'}
          >
            {course.has_exam === 1 ? '有考试' : '无考试'}
          </Tag>
        )}
        {course.popularity_level >= 3 && (
          <Tag
            style={{
              fontSize: 10,
              background: '#fef3c7',
              color: '#B9772E',
              border: 'none',
            }}
            aria-label={course.popularity_level >= 4 ? '爆满' : '热门'}
          >
            {course.popularity_level >= 4 ? '爆满' : '热门'}
          </Tag>
        )}
      </Space>
    </div>
  )
}

/**
 * Tags 区域（domain/category/difficulty/workload/grade_friendly/has_exam/popularity）
 * 单独抽出以便 inline / card variant 复用；样式由 variant 决定
 */
function TagsBlock({ course }: { course: Course }) {
  return (
    <div
      style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 4 }}
      aria-label="课程标签"
    >
      {course.domain && (
        <Tag style={{ fontSize: 10, background: '#E0F5F2', color: '#B9772E', border: 'none', margin: 0 }}>
          {course.domain}
        </Tag>
      )}
      {course.course_category && course.course_category !== course.domain && (
        <Tag
          style={{
            fontSize: 10,
            background: '#EAF2FB',
            color: '#16365C',
            border: 'none',
            margin: 0,
          }}
        >
          {course.course_category}
        </Tag>
      )}
      {course.difficulty && (
        <Tag
          style={{
            fontSize: 10,
            background: `${DIFFICULTY_COLORS[course.difficulty] || '#8a8980'}12`,
            color: DIFFICULTY_COLORS[course.difficulty] || '#8a8980',
            border: 'none',
            margin: 0,
          }}
        >
          难度{course.difficulty}
        </Tag>
      )}
      {course.workload && (
        <Tag
          style={{ fontSize: 10, background: '#EAF2FB', color: '#6B7A8D', border: 'none', margin: 0 }}
        >
          作业{course.workload}
        </Tag>
      )}
      {course.grade_friendly && (
        <Tag
          style={{
            fontSize: 10,
            background: '#E6F7F3',
            color: '#147D64',
            border: 'none',
            margin: 0,
          }}
        >
          给分{course.grade_friendly}
        </Tag>
      )}
      <Tag
        style={{
          fontSize: 10,
          border: 'none',
          margin: 0,
          background: course.has_exam === 1 ? '#FDECEC' : '#E6F7F3',
          color: course.has_exam === 1 ? '#C0392B' : '#147D64',
        }}
        aria-label={course.has_exam === 1 ? '有考试' : '无考试'}
      >
        {course.has_exam === 1 ? '有考试' : '无考试'}
      </Tag>
      {course.popularity_level >= 3 && (
        <Tag
          style={{ fontSize: 10, background: '#fef3c7', color: '#B9772E', border: 'none', margin: 0 }}
          aria-label={course.popularity_level >= 4 ? '爆满' : '热门'}
        >
          {course.popularity_level >= 4 ? '爆满' : '热门'}
        </Tag>
      )}
    </div>
  )
}
