'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Button,
  Card,
  Collapse,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  ReloadOutlined,
  StopOutlined,
  WarningOutlined,
  ExperimentOutlined,
} from '@ant-design/icons'
import { api } from '../lib/api'
import { getWarningLevel } from '../lib/warningLevel'
import type { StreamDonePayload, Course } from '../types'
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
  const [segments, setSegments] = useState<Array<{ course_id: string | null; course_name?: string; tokens: string[] }>>([])
  const [courseCards, setCourseCards] = useState<Map<string, Course>>(new Map())
  const [donePayload, setDonePayload] = useState<StreamDonePayload | null>(null)
  const [error, setError] = useState<{ code: string; message: string } | null>(null)
  const [isStreaming, setIsStreaming] = useState(true)
  const [warningCount, setWarningCount] = useState(0)

  const containerRef = useRef<HTMLDivElement>(null)
  const cursorRef = useRef<HTMLSpanElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  // rAF 节流：用 ref 累积 token，避免每次 event 都触发 setState 浅拷贝整个 segments
  // 数组。rAF 把多次累积合并为一次 flush，O(N) → O(1) per token（详见 A3 优化）。
  const segmentsRef = useRef<Array<{ course_id: string | null; course_name?: string; tokens: string[] }>>([])
  const courseMapRef = useRef<Map<string, Course>>(new Map())
  const rafIdRef = useRef<number | null>(null)
  const flushedRef = useRef(false)

  const scrollToBottom = useCallback(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [])

  const flushSegments = useCallback(() => {
    if (flushedRef.current) return
    flushedRef.current = true
    // 浅拷 ref 持有的数组 → state（保持引用一致以便 React diff 优化）
    setSegments(segmentsRef.current.map((s) => ({ ...s, tokens: [...s.tokens] })))
    setCourseCards(new Map(courseMapRef.current))
    rafIdRef.current = null
    // 滚动到底部
    requestAnimationFrame(() => {
      scrollToBottom()
    })
  }, [scrollToBottom])

  const scheduleFlush = useCallback(() => {
    flushedRef.current = false
    if (rafIdRef.current !== null) return
    rafIdRef.current = requestAnimationFrame(flushSegments)
  }, [flushSegments])

  // 取消按钮：用户主动中断流。AbortController.abort() 会被 useEffect cleanup 也调一次。
  const handleStop = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  useEffect(() => {
    const ac = new AbortController()
    abortRef.current = ac
    segmentsRef.current = []
    courseMapRef.current = new Map()
    // 重置组件状态：依赖项变化（prompt/numItems/mode）时重新触发流；
    // 这是 React 官方允许的"effect 内重置 state"模式（effect 用于同步外部系统）。
    /* eslint-disable react-hooks/set-state-in-effect */
    setSegments([])
    setCourseCards(new Map())
    setDonePayload(null)
    setError(null)
    setIsStreaming(true)
    setPhase('start')
    setWarningCount(0)
    /* eslint-enable react-hooks/set-state-in-effect */

    const uid = `user_${Date.now()}`
    const body = { user_id: uid, prompt, num_items: numItems, scene: 'course_selection' as const, mode }

    void (async () => {
      try {
        for await (const evt of api.recommendStreamWithRetry(body, ac.signal)) {
          if (ac.signal.aborted) return

          switch (evt.event) {
            case 'phase': {
              const pd = evt.data as { phase: string; warning_count?: number }
              setPhase(pd.phase)
              if (pd.warning_count !== undefined) setWarningCount(pd.warning_count)
              break
            }

            case 'course_start': {
              const sd = evt.data as { course_id: string; course_name: string }
              if (sd.course_id && sd.course_name) {
                segmentsRef.current.push({
                  course_id: sd.course_id,
                  course_name: sd.course_name,
                  tokens: [],
                })
                scheduleFlush()
              }
              break
            }

            case 'text': {
              const td = evt.data as { course_id: string | null; token: string }
              const cid = td.course_id
              const segs = segmentsRef.current
              let seg = cid ? segs.find((s) => s.course_id === cid) : segs.find((s) => s.course_id === null)
              if (!seg) {
                seg = cid
                  ? { course_id: cid, tokens: [td.token] }
                  : { course_id: null, tokens: [td.token] }
                segs.push(seg)
              } else {
                seg.tokens.push(td.token)
              }
              scheduleFlush()
              break
            }

            case 'course_end':
              // course card 会在 done 事件到达时填充
              break

            case 'done': {
              const dd = evt.data as StreamDonePayload
              for (const c of dd.courses) {
                courseMapRef.current.set(c.course_id, c)
              }
              setDonePayload(dd)
              setIsStreaming(false)
              onDone?.(dd)
              // 强制 flush（rAF 在 done 时仍可能未触发）
              flushSegments()
              scrollToBottom()
              return
            }

            case 'error': {
              const ed = evt.data as { code: string; message: string }
              setError({ code: ed.code, message: ed.message })
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

    return () => {
      ac.abort()
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current)
      }
    }
  }, [prompt, numItems, mode, onDone, scheduleFlush, flushSegments, scrollToBottom])

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
          borderBottom: '1px solid #EAF2FB',
          marginBottom: 4,
        }}
      >
        {phaseDots.map((p, i) => {
          const done = completedPhases.includes(p)
          const active = !done && i === completedPhases.length
          return (
            <div
              key={p}
              style={{ display: 'flex', alignItems: 'center', flex: p === 'start' ? '0 0 auto' : 1 }}
            >
              <div
                className={active && isStreaming ? 'phase-dot-active' : ''}
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: '50%',
                  background: done ? '#1FA88D' : active ? '#16365C' : '#CFE3F5',
                  transition: 'background 0.3s ease',
                  flexShrink: 0,
                }}
              />
              {p !== 'phase3' && (
                <div
                  style={{
                    flex: 1,
                    height: 2,
                    background: done ? '#1FA88D' : '#CFE3F5',
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
          <ExperimentOutlined style={{ marginRight: 4, color: isStreaming ? '#16365C' : '#1FA88D' }} />
          {currentPhaseLabel}
        </Text>
        {/* ── 取消按钮（路 2：暴露 AbortController UI） ── */}
        {isStreaming && (
          <Button
            size="small"
            type="default"
            danger
            icon={<StopOutlined aria-hidden="true" />}
            onClick={handleStop}
            style={{ marginLeft: 'auto' }}
            aria-label="停止生成推荐"
          >
            停止
          </Button>
        )}
      </div>

      {/* ── Streaming text area（路 2：role="status" aria-live="polite" 让屏幕阅读器朗读） ── */}
      <div
        ref={containerRef}
        role="status"
        aria-live="polite"
        aria-busy={isStreaming}
        aria-label="推荐流式生成区域"
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
            <Space size={6} aria-hidden="true">
              <Spin size="small" />
            </Space>
            <Text type="secondary" style={{ fontSize: 14, fontStyle: 'italic', display: 'block', marginTop: 8 }}>
              正在分析你的选课需求...
            </Text>
          </div>
        )}

        {segments.map((seg, si) => {
          const isIntro = seg.course_id === null
          const course = seg.course_id ? courseCards.get(seg.course_id) : null

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
          <span ref={cursorRef} className="stream-cursor" aria-hidden="true" />
        )}
      </div>

      {/* ── Error ── */}
      {error && (
        <div
          className="card-slide-in"
          role="alert"
          style={{
            margin: '8px 4px',
            padding: '16px 20px',
            borderRadius: 10,
            background: '#FDECEC',
            border: '1px solid #fecaca',
          }}
        >
          <Space orientation="vertical" size={4}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <CloseCircleOutlined style={{ color: '#D64545', fontSize: 15 }} aria-hidden="true" />
              <Text strong style={{ color: '#C0392B', fontSize: 14 }}>请求失败</Text>
              <Tag style={{ fontSize: 10, background: '#fee2e2', color: '#C0392B', border: 'none' }}>
                {error.code}
              </Tag>
            </span>
            <Text type="secondary" style={{ fontSize: 13 }}>{error.message}</Text>
          </Space>
          {onRetry && (
            <Button
              size="small"
              icon={<ReloadOutlined aria-hidden="true" />}
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
            background: '#E6F7F3',
            border: '1px solid #c6f0d7',
            display: 'flex',
            alignItems: 'center',
            gap: 20,
            flexWrap: 'wrap',
          }}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <CheckCircleOutlined style={{ color: '#1FA88D', fontSize: 14 }} aria-hidden="true" />
            <Text strong style={{ color: '#147D64', fontSize: 13 }}>推荐完成</Text>
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#6B7A8D' }}>
            <ClockCircleOutlined aria-hidden="true" />
            {donePayload.total_latency_ms.toFixed(0)} ms
          </span>
          {donePayload.courses.length > 0 && (
            <Text style={{ fontSize: 12, color: '#6B7A8D' }}>
              {donePayload.courses.length} 门课程
            </Text>
          )}
          {warningCount > 0 && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#B9772E' }}>
              <WarningOutlined aria-hidden="true" />
              {warningCount} 条选课提醒
            </span>
          )}
          <Tag style={{ fontSize: 10, background: '#EAF2FB', color: '#16365C', border: 'none', marginLeft: 'auto' }}>
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
                    <WarningOutlined style={{ color: '#14B8A6' }} aria-hidden="true" />
                    <Text strong style={{ color: '#B9772E' }}>选课可行性提醒</Text>
                    <Tag style={{ background: '#fef3c7', color: '#B9772E', border: 'none' }}>
                      {donePayload.selection_warnings.length} 条
                    </Tag>
                  </Space>
                ),
                children: (
                  <div style={{ maxHeight: 340, overflow: 'auto' }}>
                    {donePayload.selection_warnings.map((w, i) => {
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
      )}
    </div>
  )
}
