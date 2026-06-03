import { useEffect, useRef, useState, useCallback } from 'react'
import { Tag, Typography, Button, Space, Collapse, Card } from 'antd'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  WarningOutlined,
  ReloadOutlined,
  ExperimentOutlined,
} from '@ant-design/icons'
import { api } from '../services/api'
import type {
  SSEEvent,
  StreamSegment,
  StreamDonePayload,
  Course,
} from '../types'
import CourseInlineCard from './CourseInlineCard'

const { Text } = Typography

const PHASE_LABELS: Record<string, string> = {
  start: '初始化',
  phase1: '分析画像 & 课程召回',
  phase2: '课程重排 & 可行性检查',
  phase3: '生成推荐理由',
  phase1_complete: '画像 & 召回完成',
  phase2_complete: '重排 & 检查完成',
  phase3_start: '正在生成推荐...',
  phase3_complete: '推荐完成',
  react_start: 'ReAct: 初始化',
  react_extract_profile: 'ReAct: 提取学生画像',
  react_search_courses: 'ReAct: 课程召回',
  react_filter_hard_constraints: 'ReAct: 硬约束过滤',
  react_semantic_filter_courses: 'ReAct: 语义初筛',
  react_rerank_courses: 'ReAct: 课程重排',
  react_check_feasibility: 'ReAct: 可行性检查',
  react_generate_reasons: 'ReAct: 正在生成推荐...',
  react_round: 'ReAct: LLM 决策中...',
}

interface Props {
  prompt: string
  numItems: number
  mode?: 'pipeline' | 'react'
  onDone?: (payload: StreamDonePayload) => void
  onRetry?: () => void
}

export default function StreamView({ prompt, numItems, mode = 'pipeline', onDone, onRetry }: Props) {
  const [phase, setPhase] = useState<string>('start')
  const [segments, setSegments] = useState<StreamSegment[]>([])
  const [courseCards, setCourseCards] = useState<Map<string, Course>>(new Map())
  const [donePayload, setDonePayload] = useState<StreamDonePayload | null>(null)
  const [error, setError] = useState<{ code: string; message: string } | null>(null)
  const [isStreaming, setIsStreaming] = useState(true)
  const [warningCount, setWarningCount] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)
  const cursorRef = useRef<HTMLSpanElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  const scrollToBottom = useCallback(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [])

  useEffect(() => {
    const ac = new AbortController()
    abortRef.current = ac
    setIsStreaming(true)
    setSegments([])
    setCourseCards(new Map())
    setDonePayload(null)
    setError(null)
    setPhase('start')
    setWarningCount(0)

    const uid = `user_${Date.now()}`
    const body = { user_id: uid, prompt, num_items: numItems, scene: 'course_selection' as const }

    let currentSegments: StreamSegment[] = []
    const courseMap = new Map<string, Course>()

    ;(async () => {
      try {
        const streamFn = mode === 'react' ? api.recommendReactStream : api.recommendStream
        for await (const evt of streamFn(body)) {
          if (ac.signal.aborted) return

          switch (evt.event) {
            case 'phase': {
              const pd = evt.data
              setPhase(pd.phase)
              if (pd.warning_count !== undefined) setWarningCount(pd.warning_count)
              break
            }

            case 'course_start': {
              const sd = evt.data
              if (sd.course_id && sd.course_name) {
                currentSegments.push({
                  course_id: sd.course_id,
                  course_name: sd.course_name,
                  tokens: [],
                })
              }
              setSegments([...currentSegments])
              break
            }

            case 'text': {
              const td = evt.data
              const cid = td.course_id
              if (cid) {
                const seg = currentSegments.find((s) => s.course_id === cid)
                if (seg) {
                  seg.tokens.push(td.token)
                } else {
                  currentSegments.push({ course_id: cid, tokens: [td.token] })
                }
              } else {
                let intro = currentSegments.find((s) => s.course_id === null)
                if (!intro) {
                  intro = { course_id: null, tokens: [] }
                  currentSegments.push(intro)
                }
                intro.tokens.push(td.token)
              }
              setSegments([...currentSegments])
              scrollToBottom()
              break
            }

            case 'course_end': {
              // course card will be populated when done event arrives with course data
              break
            }

            case 'done': {
              const dd = evt.data
              for (const c of dd.courses) {
                courseMap.set(c.course_id, c)
              }
              setCourseCards(new Map(courseMap))
              setDonePayload(dd)
              setIsStreaming(false)
              onDone?.(dd)
              scrollToBottom()
              return
            }

            case 'error': {
              setError({ code: evt.data.code, message: evt.data.message })
              setIsStreaming(false)
              return
            }
          }
        }
      } catch (e: unknown) {
        if (ac.signal.aborted) return
        setError({
          code: 'NETWORK_ERROR',
          message: e instanceof Error ? e.message : '连接中断',
        })
        setIsStreaming(false)
      }
    })()

    return () => ac.abort()
  }, [prompt, numItems, onDone, scrollToBottom])

  const phaseDots = ['start', 'phase1', 'phase2', 'phase3']
  const completedPhases = (() => {
    if (!isStreaming && donePayload) return phaseDots
    const idx = phaseDots.indexOf(phase)
    if (idx >= 0) return phaseDots.slice(0, idx)
    if (phase === 'phase1_complete') return phaseDots.slice(0, 2)
    if (phase === 'phase2_complete') return phaseDots.slice(0, 3)
    if (phase === 'phase3_start' || phase === 'phase3_complete') return phaseDots.slice(0, 4)
    return phaseDots.slice(0, 1)
  })()

  const currentPhaseLabel = PHASE_LABELS[phase] || phase

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* ── Phase progress bar ── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 0,
          padding: '10px 0 16px',
          borderBottom: '1px solid #f0ece5',
          marginBottom: 4,
        }}
      >
        {phaseDots.map((p, i) => {
          const done = completedPhases.includes(p)
          const active = !done && i === completedPhases.length
          return (
            <div key={p} style={{ display: 'flex', alignItems: 'center', flex: p === 'start' ? '0 0 auto' : 1 }}>
              <div
                className={active && isStreaming ? 'phase-dot-active' : ''}
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: '50%',
                  background: done ? '#2d6a4f' : active ? '#1e3a5f' : '#e8e0d5',
                  transition: 'background 0.3s ease',
                  flexShrink: 0,
                }}
              />
              {p !== 'phase3' && (
                <div
                  style={{
                    flex: 1,
                    height: 2,
                    background: done ? '#2d6a4f' : '#e8e0d5',
                    transition: 'background 1s ease',
                    marginLeft: i === 0 ? 6 : 0,
                    minWidth: 20,
                  }}
                />
              )}
            </div>
          )
        })}
        <Text type="secondary" style={{ fontSize: 11, marginLeft: 10, whiteSpace: 'nowrap', minWidth: 80 }}>
          <ExperimentOutlined style={{ marginRight: 4, color: isStreaming ? '#1e3a5f' : '#2d6a4f' }} />
          {currentPhaseLabel}
        </Text>
      </div>

      {/* ── Streaming text area ── */}
      <div
        ref={containerRef}
        style={{
          flex: 1,
          minHeight: 300,
          maxHeight: 'calc(100vh - 380px)',
          overflowY: 'auto',
          padding: '8px 4px 20px',
        }}
      >
        {segments.length === 0 && isStreaming && (
          <div style={{ padding: '40px 0', textAlign: 'center' }}>
            <Text type="secondary" style={{ fontSize: 14, fontStyle: 'italic' }}>
              正在分析你的选课需求...
            </Text>
          </div>
        )}

        {segments.map((seg, si) => {
          const isIntro = seg.course_id === null
          const course = seg.course_id ? courseCards.get(seg.course_id) : null
          const fullText = seg.tokens.join('')

          return (
            <div key={si} style={{ marginBottom: isIntro ? 0 : 4 }}>
              {/* Course name heading (non-intro) */}
              {!isIntro && seg.course_name && (
                <div className="stream-course-name">
                  {seg.course_name}
                </div>
              )}

              {/* Text block */}
              <div className={`stream-text-block ${isIntro ? 'stream-intro' : ''}`}>
                {seg.tokens.map((token, ti) => (
                  <span key={ti} className="stream-token">
                    {token}
                  </span>
                ))}
              </div>

              {/* Course card after course_end */}
              {!isIntro && course && (
                <div style={{ marginTop: 6, marginBottom: 10 }}>
                  <CourseInlineCard
                    course={course}
                    index={Array.from(courseCards.keys()).indexOf(seg.course_id!)}
                  />
                </div>
              )}
            </div>
          )
        })}

        {/* Blinking cursor while streaming */}
        {isStreaming && !error && (
          <span ref={cursorRef} className="stream-cursor" />
        )}
      </div>

      {/* ── Error ── */}
      {error && (
        <div
          className="card-slide-in"
          style={{
            margin: '8px 4px',
            padding: '16px 20px',
            borderRadius: 10,
            background: '#fef2f2',
            border: '1px solid #fecaca',
          }}
        >
          <Space direction="vertical" size={4}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <CloseCircleOutlined style={{ color: '#a52a2a', fontSize: 15 }} />
              <Text strong style={{ color: '#991b1b', fontSize: 14 }}>请求失败</Text>
              <Tag style={{ fontSize: 10, background: '#fee2e2', color: '#991b1b', border: 'none' }}>
                {error.code}
              </Tag>
            </span>
            <Text type="secondary" style={{ fontSize: 13 }}>{error.message}</Text>
          </Space>
          {onRetry && (
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={onRetry}
              style={{ marginTop: 10 }}
            >
              重试
            </Button>
          )}
        </div>
      )}

      {/* ── Done footer ── */}
      {donePayload && (
        <div
          className="card-slide-in"
          style={{
            margin: '8px 4px 0',
            padding: '12px 18px',
            borderRadius: 10,
            background: '#f0faf4',
            border: '1px solid #c6f0d7',
            display: 'flex',
            alignItems: 'center',
            gap: 20,
            flexWrap: 'wrap',
          }}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <CheckCircleOutlined style={{ color: '#2d6a4f', fontSize: 14 }} />
            <Text strong style={{ color: '#166534', fontSize: 13 }}>推荐完成</Text>
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#5c5c6e' }}>
            <ClockCircleOutlined />
            {donePayload.total_latency_ms.toFixed(0)} ms
          </span>
          {donePayload.courses.length > 0 && (
            <Text style={{ fontSize: 12, color: '#5c5c6e' }}>
              {donePayload.courses.length} 门课程
            </Text>
          )}
          {warningCount > 0 && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#92400e' }}>
              <WarningOutlined />
              {warningCount} 条选课提醒
            </span>
          )}
          <Tag style={{ fontSize: 10, background: '#e8eef4', color: '#1e3a5f', border: 'none', marginLeft: 'auto' }}>
            {donePayload.experiment_group}
          </Tag>
        </div>
      )}

      {/* ── Warnings & Priority Advice ── */}
      {donePayload && (
        <div style={{ marginTop: 12 }}>
          {donePayload.selection_warnings.length > 0 && (
            <Collapse
              style={{ marginBottom: 12 }}
              items={[{
                key: 'warnings',
                label: (
                  <Space>
                    <WarningOutlined style={{ color: '#c88c3e' }} />
                    <Text strong style={{ color: '#92400e' }}>选课可行性提醒</Text>
                    <Tag style={{ background: '#fef3c7', color: '#92400e', border: 'none' }}>
                      {donePayload.selection_warnings.length} 条
                    </Tag>
                  </Space>
                ),
                children: (
                  <div style={{ maxHeight: 340, overflow: 'auto' }}>
                    {donePayload.selection_warnings.map((w, i) => {
                      const levelColors: Record<string, string> = {
                        high: '#991b1b', medium: '#92400e', low: '#5c5c6e',
                      }
                      const levelBgs: Record<string, string> = {
                        high: '#fef2f2', medium: '#fef3c7', low: '#f0ece5',
                      }
                      const levelLabels: Record<string, string> = {
                        high: '高', medium: '中', low: '低',
                      }
                      const lv = String(w.level || '')
                      const courseName = String(w.course_name || w.course_id || '')
                      const message = String(w.message || '')
                      return (
                        <Card key={i} size="small" style={{ marginBottom: 8 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                            <Text strong style={{ fontSize: 13 }}>{courseName}</Text>
                            {lv && (
                              <Tag style={{
                                fontSize: 11, border: 'none',
                                background: levelBgs[lv] || levelBgs.low,
                                color: levelColors[lv] || levelColors.low,
                              }}>
                                {levelLabels[lv] || lv}
                              </Tag>
                            )}
                          </div>
                          <Text style={{ fontSize: 13, color: '#5c5c6e' }}>{message}</Text>
                        </Card>
                      )
                    })}
                  </div>
                ),
              }]}
            />
          )}
        </div>
      )}
    </div>
  )
}
