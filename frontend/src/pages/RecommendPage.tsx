import { useState, useCallback } from 'react'
import {
  Card,
  Input,
  Button,
  Slider,
  Tag,
  Tabs,
  Spin,
  Empty,
  Collapse,
  Badge,
  Table,
  Space,
  Row,
  Col,
  Statistic,
  Tooltip,
  Typography,
  message,
} from 'antd'
import {
  SendOutlined,
  ThunderboltOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  UserOutlined,
  SearchOutlined,
  OrderedListOutlined,
  SafetyOutlined,
  CommentOutlined,
  SettingOutlined,
  CodeOutlined,
  HighlightOutlined,
  RiseOutlined,
  TrophyOutlined,
  HeartOutlined,
  ExperimentOutlined,
  LoadingOutlined,
  BulbOutlined,
  BookOutlined,
  TeamOutlined,
  EnvironmentOutlined,
  FieldTimeOutlined,
  StarOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { api } from '../services/api'
import { useRecommendStore, useActiveJobStore, useInputStore } from '../stores'
import type { Course, RecommendationResponse, PresetQuery, StreamDonePayload } from '../types'
import StreamView from '../components/StreamView'

const { TextArea } = Input
const { Text, Title } = Typography

const PRESET_QUERIES: PresetQuery[] = [
  {
    id: 'cs',
    label: '计算机爱好者',
    icon: 'CodeOutlined',
    prompt: '我对计算机和人工智能非常感兴趣，想选一些编程相关的课程，最好是实践为主、能学到真东西的课。',
  },
  {
    id: 'art',
    label: '文艺青年',
    icon: 'HighlightOutlined',
    prompt: '我是文科生，想选一些轻松有趣的人文艺术类课程，比如文学、书法、音乐鉴赏之类的，不要太多作业和考试。',
  },
  {
    id: 'finance',
    label: '商科精英',
    icon: 'RiseOutlined',
    prompt: '我想选和金融经济相关的课程，未来想去投行或咨询公司工作，希望课程含金量高、对职业发展有帮助。',
  },
  {
    id: 'senior',
    label: '大四学霸',
    icon: 'TrophyOutlined',
    prompt: '我大四了还差几个学分毕业，需要选一些容易过、给分高、不点名的课，最好是线上或晚上上课的。',
  },
  {
    id: 'sport',
    label: '运动达人',
    icon: 'HeartOutlined',
    prompt: '我对体育和健康很感兴趣，想选运动类的课程，比如篮球、游泳、瑜伽或健康管理相关的课。',
  },
]

const PRESET_ICON_MAP: Record<string, React.ReactNode> = {
  CodeOutlined: <CodeOutlined />,
  HighlightOutlined: <HighlightOutlined />,
  RiseOutlined: <RiseOutlined />,
  TrophyOutlined: <TrophyOutlined />,
  HeartOutlined: <HeartOutlined />,
}

const PHASE_MAP: Record<string, { phase: number; label: string; icon: React.ReactNode }> = {
  student_profile: { phase: 1, label: '学生画像', icon: <UserOutlined /> },
  course_recall: { phase: 1, label: '课程召回', icon: <SearchOutlined /> },
  course_rerank: { phase: 2, label: '课程重排', icon: <OrderedListOutlined /> },
  course_feasibility: { phase: 2, label: '选课可行性', icon: <SafetyOutlined /> },
  recommendation_reason: { phase: 3, label: '推荐理由', icon: <CommentOutlined /> },
}

const DIFFICULTY_COLORS: Record<string, string> = {
  '高': '#a52a2a', '中': '#c88c3e', '低': '#2d6a4f',
  'hard': '#a52a2a', 'medium': '#c88c3e', 'easy': '#2d6a4f',
}

export default function RecommendPage() {
  const prompt = useInputStore((s) => s.prompt)
  const numItems = useInputStore((s) => s.numItems)
  const setPrompt = useInputStore((s) => s.setPrompt)
  const setNumItems = useInputStore((s) => s.setNumItems)

  const [activeTab, setActiveTab] = useState('stream')
  const [streamKey, setStreamKey] = useState(0)
  const [streamPrompt, setStreamPrompt] = useState('')
  const [streamNumItems, setStreamNumItems] = useState(5)

  const { jobs, addJob, setResponse, setError } = useRecommendStore()
  const { activeId, setActive } = useActiveJobStore()

  const handleStreamSubmit = useCallback(() => {
    const query = prompt.trim()
    if (!query) {
      message.warning('请输入选课需求描述')
      return
    }
    setStreamPrompt(query)
    setStreamNumItems(numItems)
    setStreamKey((k) => k + 1)
    setActiveTab('stream')
  }, [prompt, numItems])

  const handleSubmit = useCallback(async () => {
    const query = prompt.trim()
    if (!query) {
      message.warning('请输入选课需求描述')
      return
    }
    setActiveTab('single')
    const uid = `user_${Date.now()}`
    addJob(uid, '自定义查询', query)
    setActive(uid)
    try {
      const res = await api.recommend({ user_id: uid, prompt: query, num_items: numItems, scene: 'course_selection' })
      setResponse(uid, res)
    } catch (e: unknown) {
      setError(uid, e instanceof Error ? e.message : '请求失败')
      message.error(e instanceof Error ? e.message : '推荐请求失败，请检查API服务是否运行')
    }
  }, [prompt, numItems, addJob, setActive, setResponse, setError])

  const handlePresetClick = useCallback(async (pq: PresetQuery) => {
    setPrompt(pq.prompt)
    setStreamPrompt(pq.prompt)
    setStreamNumItems(numItems)
    setStreamKey((k) => k + 1)
    setActiveTab('stream')
  }, [numItems, setPrompt])

  const handleCompareAll = useCallback(async () => {
    setActiveTab('compare')
    const jobDefs = PRESET_QUERIES.map((pq) => ({
      id: `${pq.id}_${Date.now()}`,
      label: pq.label,
      prompt: pq.prompt,
    }))
    for (const j of jobDefs) addJob(j.id, j.label, j.prompt)
    const results = await Promise.allSettled(
      jobDefs.map((j) => api.recommend({ user_id: j.id, prompt: j.prompt, num_items: numItems, scene: 'course_selection' }))
    )
    results.forEach((r, i) => {
      if (r.status === 'fulfilled') setResponse(jobDefs[i].id, r.value)
      else setError(jobDefs[i].id, r.reason?.message || '请求失败')
    })
    setActive(jobDefs[0].id)
  }, [numItems, addJob, setResponse, setError, setActive])

  const activeJob = jobs.find((j) => j.id === activeId)
  const compareJobs = jobs.filter((j) => j.response && !j.error).slice(-5)

  return (
    <div>
      {/* ── Input Panel ── */}
      <Card
        className="animate-fade-scale"
        style={{ marginBottom: 24, border: '1px solid #e8e0d5' }}
        styles={{
          body: { padding: 24 },
          header: { borderBottom: '1px solid #f0ece5', padding: '16px 24px', fontWeight: 600 },
        }}
        title={
          <Space>
            <BulbOutlined style={{ color: '#c88c3e' }} />
            <span className="serif-heading" style={{ fontSize: 15 }}>选课需求描述</span>
            <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
              用自然语言描述你想选什么样的课
            </Text>
          </Space>
        }
      >
        <TextArea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="例如：我对计算机和人工智能很感兴趣，想选一些编程相关的课程，最好是实践为主的..."
          autoSize={{ minRows: 3, maxRows: 6 }}
          style={{ marginBottom: 16, fontSize: 14, borderRadius: 8 }}
        />

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <Space size="small" style={{ background: '#faf8f5', padding: '6px 14px', borderRadius: 8 }}>
            <SettingOutlined style={{ color: '#5c5c6e' }} />
            <Text type="secondary" style={{ fontSize: 13 }}>推荐数量</Text>
            <Slider min={1} max={10} value={numItems} onChange={setNumItems} style={{ width: 100 }} />
            <Tag style={{ background: '#e8eef4', color: '#1e3a5f', border: 'none', fontWeight: 500 }}>{numItems}</Tag>
          </Space>

          <div style={{ flex: 1 }} />

          <Space>
            <Button type="primary" icon={<SendOutlined />} onClick={handleStreamSubmit} size="large">
              开始推荐
            </Button>
            <Button
              icon={<ExperimentOutlined />}
              onClick={handleSubmit}
              size="large"
            >
              经典模式
            </Button>
            <Button
              style={{ borderColor: '#c88c3e', color: '#c88c3e' }}
              icon={<ThunderboltOutlined />}
              onClick={handleCompareAll}
              size="large"
            >
              批量对比 5 组查询
            </Button>
          </Space>
        </div>

        <div style={{ marginTop: 16 }}>
          <Text type="secondary" style={{ fontSize: 12, marginRight: 10 }}>快速预设：</Text>
          <Space wrap size={[6, 6]}>
            {PRESET_QUERIES.map((pq) => (
              <button
                key={pq.id}
                onClick={() => handlePresetClick(pq)}
                style={{
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 5,
                  padding: '4px 14px',
                  borderRadius: 20,
                  border: '1px solid #e8e0d5',
                  background: '#fff',
                  fontSize: 13,
                  color: '#5c5c6e',
                  transition: 'all 180ms cubic-bezier(0.16, 1, 0.3, 1)',
                  fontFamily: 'inherit',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = '#1e3a5f'
                  e.currentTarget.style.color = '#1e3a5f'
                  e.currentTarget.style.background = '#e8eef4'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = '#e8e0d5'
                  e.currentTarget.style.color = '#5c5c6e'
                  e.currentTarget.style.background = '#fff'
                }}
                onFocus={(e) => {
                  e.currentTarget.style.borderColor = '#1e3a5f'
                  e.currentTarget.style.boxShadow = '0 0 0 2px rgba(30,58,95,0.12)'
                }}
                onBlur={(e) => {
                  e.currentTarget.style.boxShadow = 'none'
                }}
                aria-label={`使用预设: ${pq.label}`}
              >
                {PRESET_ICON_MAP[pq.icon]}
                {pq.label}
              </button>
            ))}
          </Space>
        </div>
      </Card>

      {/* ── Results Panel ── */}
      <Card
        className="animate-fade-in"
        style={{ border: '1px solid #e8e0d5' }}
        styles={{ body: { padding: 20 } }}
      >
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'stream',
              label: (
                <Space size={4}>
                  <SendOutlined />
                  <span>流式对话</span>
                  {streamKey > 0 && (
                    <Tag style={{ background: '#f0faf4', color: '#166534', border: 'none', marginLeft: 4 }}>
                      实时
                    </Tag>
                  )}
                </Space>
              ),
              children: streamKey > 0 ? (
                <StreamView
                  key={streamKey}
                  prompt={streamPrompt}
                  numItems={streamNumItems}
                  onRetry={() => {
                    setStreamKey((k) => k + 1)
                  }}
                />
              ) : (
                <div className="animate-fade-in">
                  <Empty
                    image={<SendOutlined style={{ fontSize: 48, color: '#c88c3e' }} />}
                    description="输入选课需求，点击「开始推荐」或选择预设查询，AI 将逐字生成推荐反馈"
                  />
                </div>
              ),
            },
            {
              key: 'single',
              label: (
                <Space size={4}>
                  <ExperimentOutlined />
                  <span>经典结果</span>
                </Space>
              ),
              children: activeJob?.response ? (
                <SingleResultView response={activeJob.response} prompt={activeJob.prompt} />
              ) : activeJob?.loading ? (
                <div style={{ textAlign: 'center', padding: 80 }}>
                  <Spin size="large" tip="AI Agent 正在分析中...">
                    <div style={{ marginTop: 40 }} />
                  </Spin>
                </div>
              ) : activeJob?.error ? (
                <div className="animate-fade-in">
                  <Empty
                    image={<CloseCircleOutlined style={{ fontSize: 48, color: '#a52a2a' }} />}
                    description={<Text type="danger">{activeJob.error}</Text>}
                  />
                </div>
              ) : (
                <div className="animate-fade-in">
                  <Empty
                    image={<BookOutlined style={{ fontSize: 48, color: '#c88c3e' }} />}
                    description="输入选课需求，点击「开始推荐」或选择预设查询查看结果"
                  />
                </div>
              ),
            },
            {
              key: 'compare',
              label: (
                <Space size={4}>
                  <ThunderboltOutlined />
                  <span>多查询对比</span>
                  {compareJobs.length > 0 && (
                    <Tag style={{ background: '#e8eef4', color: '#1e3a5f', border: 'none', marginLeft: 4 }}>
                      {compareJobs.length}
                    </Tag>
                  )}
                </Space>
              ),
              children: compareJobs.length > 0 ? (
                <CompareView jobs={jobs.filter((j) => j.response && !j.error).slice(-5)} />
              ) : (
                <Empty
                  image={<ThunderboltOutlined style={{ fontSize: 48, color: '#c88c3e' }} />}
                  description="点击「批量对比」同时提交 5 组不同查询，对比推荐结果"
                />
              ),
            },
          ]}
        />
      </Card>
    </div>
  )
}

/* ================================================================
   Single Result View
   ================================================================ */

function SingleResultView({ response, prompt }: { response: RecommendationResponse; prompt: string }) {
  return (
    <div className="animate-fade-in">
      {/* Stats Row */}
      <Row gutter={16} className="stagger" style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}>
          <StatCard
            icon={<ClockCircleOutlined />}
            title="总耗时"
            value={`${response.total_latency_ms.toFixed(0)} ms`}
            color={response.total_latency_ms < 3000 ? '#2d6a4f' : '#c88c3e'}
          />
        </Col>
        <Col xs={12} sm={6}>
          <StatCard
            icon={<BookOutlined />}
            title="推荐课程"
            value={`${response.courses.length} 门`}
            color="#1e3a5f"
          />
        </Col>
        <Col xs={12} sm={6}>
          <StatCard
            icon={<CheckCircleOutlined />}
            title="可用 Agent"
            value={`${Object.values(response.agent_results).filter((a) => a.success).length}/${Object.keys(response.agent_results).length}`}
            color="#2d6a4f"
          />
        </Col>
        <Col xs={12} sm={6}>
          <StatCard
            icon={<WarningOutlined />}
            title="选课提醒"
            value={`${response.selection_warnings.length} 条`}
            color={response.selection_warnings.length > 0 ? '#c88c3e' : '#5c5c6e'}
          />
        </Col>
      </Row>

      {/* Pipeline Timeline */}
      <PipelineTimeline agentResults={response.agent_results} totalLatency={response.total_latency_ms} />

      {/* Course Cards */}
      <Title level={5} className="serif-heading" style={{ marginTop: 28, marginBottom: 16, color: '#1a1a2e' }}>
        <BookOutlined style={{ marginRight: 6, color: '#c88c3e' }} />
        推荐课程列表
      </Title>
      {response.courses.length === 0 ? (
        <Empty description="未找到匹配的课程" />
      ) : (
        <Row gutter={[12, 12]} className="stagger">
          {response.courses.map((course) => (
            <Col xs={24} sm={12} lg={8} key={course.course_id}>
              <CourseCard course={course} />
            </Col>
          ))}
        </Row>
      )}

      {/* Reasons & Warnings */}
      <div className="stagger" style={{ marginTop: 20 }}>
        {response.recommendation_reasons.length > 0 && (
          <Collapse
            style={{ marginBottom: 12 }}
            items={[{
              key: 'reasons',
              label: (
                <Space>
                  <CommentOutlined style={{ color: '#c88c3e' }} />
                  <Text strong className="serif-heading">
                    AI 推荐理由
                  </Text>
                  <Tag style={{ background: '#f5e6d0', color: '#92400e', border: 'none' }}>
                    {response.recommendation_reasons.length} 条
                  </Tag>
                </Space>
              ),
              children: (
                <div style={{ maxHeight: 340, overflow: 'auto' }}>
                  {response.recommendation_reasons.map((reason, i) => (
                    <Card key={i} size="small" style={{ marginBottom: 8 }}>
                      {Object.entries(reason).map(([k, v]) => (
                        <div key={k} style={{ marginBottom: 4 }}>
                          <Text strong style={{ fontSize: 13 }}>{k}：</Text>
                          <Text style={{ fontSize: 13 }}>{v}</Text>
                        </div>
                      ))}
                    </Card>
                  ))}
                </div>
              ),
            }]}
          />
        )}
        {response.selection_warnings.length > 0 && (
          <Collapse
            style={{ marginBottom: 12 }}
            items={[{
              key: 'warnings',
              label: (
                <Space>
                  <WarningOutlined style={{ color: '#c88c3e' }} />
                  <Text strong className="serif-heading" style={{ color: '#92400e' }}>
                    选课可行性提醒
                  </Text>
                  <Tag style={{ background: '#fef3c7', color: '#92400e', border: 'none' }}>
                    {response.selection_warnings.length} 条
                  </Tag>
                </Space>
              ),
              children: (
                <div style={{ maxHeight: 340, overflow: 'auto' }}>
                  {response.selection_warnings.map((w, i) => (
                    <Card key={i} size="small" style={{ marginBottom: 8 }}>
                      {Object.entries(w).map(([k, v]) => (
                        <div key={k} style={{ marginBottom: 4 }}>
                          <Text strong style={{ fontSize: 13 }}>{k}：</Text>
                          <Text style={{ fontSize: 13 }}>{String(v)}</Text>
                        </div>
                      ))}
                    </Card>
                  ))}
                </div>
              ),
            }]}
          />
        )}
        {response.priority_advice && Object.keys(response.priority_advice).length > 0 && (
          <Collapse
            items={[{
              key: 'priority_advice',
              label: (
                <Space>
                  <RiseOutlined style={{ color: '#1e3a5f' }} />
                  <Text strong className="serif-heading" style={{ color: '#1e3a5f' }}>
                    抢课优先级建议
                  </Text>
                  <Tag style={{ background: '#e8eef4', color: '#1e3a5f', border: 'none' }}>
                    {Object.keys(response.priority_advice).length} 门
                  </Tag>
                </Space>
              ),
              children: (
                <div style={{ maxHeight: 340, overflow: 'auto' }}>
                  {Object.entries(response.priority_advice).map(([courseId, advice]) => {
                    const course = response.courses.find((c) => c.course_id === courseId)
                    const priorityColors: Record<string, string> = {
                      high: '#166534',
                      medium: '#92400e',
                      low: '#991b1b',
                    }
                    const priorityBgs: Record<string, string> = {
                      high: '#f0faf4',
                      medium: '#fef3c7',
                      low: '#fef2f2',
                    }
                    const priorityLabels: Record<string, string> = {
                      high: '稳妥',
                      medium: '偏紧',
                      low: '冲刺',
                    }
                    const p = advice.priority || 'medium'
                    return (
                      <Card key={courseId} size="small" style={{ marginBottom: 8 }}>
                        <div style={{ marginBottom: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <Text strong style={{ fontSize: 13 }}>
                            {course?.course_name || courseId}
                          </Text>
                          <Tag style={{
                            fontSize: 11, border: 'none',
                            background: priorityBgs[p] || priorityBgs.medium,
                            color: priorityColors[p] || priorityColors.medium,
                          }}>
                            {priorityLabels[p] || p}
                          </Tag>
                        </div>
                        <Text style={{ fontSize: 13, color: '#5c5c6e' }}>{advice.advice}</Text>
                      </Card>
                    )
                  })}
                </div>
              ),
            }]}
          />
        )}
      </div>

      {/* Raw Response (ghost) */}
      <Collapse
        ghost
        style={{ marginTop: 16 }}
        items={[{
          key: 'raw',
          label: <Text type="secondary" style={{ fontSize: 11 }}>查看原始响应数据</Text>,
          children: (
            <pre style={{
              fontSize: 11, maxHeight: 300, overflow: 'auto', background: '#faf8f5',
              padding: 14, borderRadius: 8, border: '1px solid #e8e0d5', color: '#5c5c6e',
            }}>
              {JSON.stringify(response, null, 2)}
            </pre>
          ),
        }]}
      />
    </div>
  )
}

/* ================================================================
   Stat Card
   ================================================================ */

function StatCard({ icon, title, value, color }: { icon: React.ReactNode; title: string; value: string; color: string }) {
  return (
    <div
      style={{
        background: '#fff',
        borderRadius: 10,
        padding: '16px 18px',
        border: '1px solid #e8e0d5',
        cursor: 'default',
        transition: 'box-shadow 200ms cubic-bezier(0.16, 1, 0.3, 1)',
      }}
      onMouseEnter={(e) => { e.currentTarget.style.boxShadow = '0 4px 16px rgba(26,26,46,0.06), 0 2px 4px rgba(26,26,46,0.03)' }}
      onMouseLeave={(e) => { e.currentTarget.style.boxShadow = 'none' }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <span style={{ color, fontSize: 13 }}>{icon}</span>
        <Text type="secondary" style={{ fontSize: 12 }}>{title}</Text>
      </div>
      <Text strong style={{ fontSize: 20, color, fontFamily: "'Noto Serif SC', serif" }}>{value}</Text>
    </div>
  )
}

/* ================================================================
   Pipeline Timeline
   ================================================================ */

function PipelineTimeline({
  agentResults,
  totalLatency,
}: {
  agentResults: Record<string, { agent_name: string; success: boolean; latency_ms: number; confidence: number; error: string | null }>
  totalLatency: number
}) {
  const phases = [
    { phase: 1, label: 'Phase 1 — 并行', sub: '画像 + 召回', color: '#1e3a5f', agents: ['student_profile', 'course_recall'] },
    { phase: 2, label: 'Phase 2 — 并行', sub: '重排 + 可行性', color: '#2d5a8e', agents: ['course_rerank', 'course_feasibility'] },
    { phase: 3, label: 'Phase 3 — 串行', sub: '推荐理由生成', color: '#2d6a4f', agents: ['recommendation_reason'] },
  ]

  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
        <ExperimentOutlined style={{ color: '#c88c3e' }} />
        <Text strong className="serif-heading" style={{ fontSize: 14 }}>Agent 流水线执行过程</Text>
      </div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'stretch' }}>
        {phases.map((phase) => (
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
              <div style={{ fontSize: 12, fontWeight: 600, color: phase.color, marginBottom: 2 }}>
                {phase.label}
              </div>
              <div style={{ fontSize: 11, color: '#8a8980' }}>{phase.sub}</div>
            </div>
            {phase.agents.map((agentName) => {
              const agent = agentResults[agentName]
              if (!agent) return null
              const info = PHASE_MAP[agentName]
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
                    background: agent.success ? '#f0faf4' : '#fef2f2',
                    border: `1px solid ${agent.success ? '#c6f0d7' : '#fecaca'}`,
                    cursor: 'default',
                    transition: 'box-shadow 180ms',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.boxShadow = `0 2px 8px ${phase.color}12` }}
                  onMouseLeave={(e) => { e.currentTarget.style.boxShadow = 'none' }}
                >
                  <Space size={4}>
                    {agent.success
                      ? <CheckCircleOutlined style={{ color: '#2d6a4f', fontSize: 13 }} />
                      : <CloseCircleOutlined style={{ color: '#a52a2a', fontSize: 13 }} />
                    }
                    <span style={{ fontSize: 12, maxWidth: 72, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {info?.label || agent.agent_name}
                    </span>
                  </Space>
                  <Tooltip title={`耗时 ${agent.latency_ms.toFixed(0)}ms · 置信度 ${(agent.confidence * 100).toFixed(0)}%`}>
                    <Tag style={{
                      fontSize: 10, margin: 0, border: 'none',
                      background: agent.success ? '#d1fae5' : '#fee2e2',
                      color: agent.success ? '#166534' : '#991b1b',
                    }}>
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
            border: '1px solid #e8e0d5',
            background: '#faf8f5',
            padding: 14,
          }}
          className="animate-slide-right"
        >
          <Text type="secondary" style={{ fontSize: 10, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
            总耗时
          </Text>
          <Text strong style={{ fontSize: 24, color: '#1e3a5f', fontFamily: "'Noto Serif SC', serif", lineHeight: 1.2 }}>
            {totalLatency.toFixed(0)}
          </Text>
          <Text type="secondary" style={{ fontSize: 10 }}>ms</Text>
        </div>
      </div>
    </div>
  )
}

/* ================================================================
   Course Card
   ================================================================ */

function CourseCard({ course }: { course: Course }) {
  return (
    <Card
      size="small"
      hoverable
      className="animate-fade-scale"
      style={{ cursor: 'pointer' }}
      styles={{
        header: { borderBottom: '1px solid #f0ece5', padding: '12px 16px' },
        body: { padding: '14px 16px' },
      }}
      title={
        <Tooltip title={course.course_name}>
          <Text strong ellipsis style={{ maxWidth: 190, fontSize: 13 }}>
            {course.course_name}
          </Text>
        </Tooltip>
      }
      extra={
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <StarOutlined style={{ color: '#c88c3e', fontSize: 11 }} />
          <Text strong style={{ fontSize: 13, color: '#1a1a2e' }}>{course.score.toFixed(1)}</Text>
        </div>
      }
    >
      <div style={{ fontSize: 12, lineHeight: '22px' }}>
        <div style={{ marginBottom: 4, display: 'flex', gap: 12 }}>
          <span>
            <TeamOutlined style={{ color: '#8a8980', fontSize: 10, marginRight: 2 }} />
            <Text type="secondary">{course.teacher || '待定'}</Text>
          </span>
          <span>
            <BookOutlined style={{ color: '#8a8980', fontSize: 10, marginRight: 2 }} />
            <Text type="secondary">{course.credits} 学分</Text>
          </span>
        </div>

        <div style={{ marginBottom: 4 }}>
          <Tag style={{ fontSize: 10, background: '#f5e6d0', color: '#92400e', border: 'none' }}>{course.domain}</Tag>
          <Tag style={{ fontSize: 10, background: '#e8eef4', color: '#1e3a5f', border: 'none', marginLeft: 4 }}>{course.course_category}</Tag>
        </div>

        <div style={{ marginBottom: 4, display: 'flex', gap: 12 }}>
          <span>
            <FieldTimeOutlined style={{ color: '#8a8980', fontSize: 10, marginRight: 2 }} />
            <Text type="secondary">{course.time_slot}</Text>
          </span>
          <span>
            <EnvironmentOutlined style={{ color: '#8a8980', fontSize: 10, marginRight: 2 }} />
            <Text type="secondary">{course.campus}</Text>
          </span>
        </div>

        <Space size={4} wrap style={{ marginBottom: 4 }}>
          {course.difficulty && (
            <Tag style={{ fontSize: 10, background: `${DIFFICULTY_COLORS[course.difficulty] || '#8a8980'}12`, color: DIFFICULTY_COLORS[course.difficulty] || '#8a8980', border: 'none' }}>
              难度 {course.difficulty}
            </Tag>
          )}
          {course.workload && (
            <Tag style={{ fontSize: 10, background: '#f0ece5', color: '#5c5c6e', border: 'none' }}>
              作业 {course.workload}
            </Tag>
          )}
          {course.grade_friendly && (
            <Tag style={{ fontSize: 10, background: '#f0faf4', color: '#166534', border: 'none' }}>
              给分 {course.grade_friendly}
            </Tag>
          )}
          {(course.has_exam === 0 || course.has_exam === 1) && (
            <Tag style={{ fontSize: 10, border: 'none',
              background: course.has_exam === 1 ? '#fef2f2' : '#f0faf4',
              color: course.has_exam === 1 ? '#991b1b' : '#166534',
            }}>
              {course.has_exam === 1 ? '有考试' : '无考试'}
            </Tag>
          )}
        </Space>

        {course.match_reasons.length > 0 && (
          <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid #f0ece5' }}>
            <Text type="secondary" style={{ fontSize: 10 }}>匹配理由</Text>
            <div style={{ marginTop: 4 }}>
              <Space size={[3, 3]} wrap>
                {course.match_reasons.slice(0, 3).map((r, i) => (
                  <Tag key={i} style={{ fontSize: 10, background: '#e8eef4', color: '#1e3a5f', border: 'none', maxWidth: 160 }}>
                    <Text ellipsis style={{ fontSize: 10 }}>{r}</Text>
                  </Tag>
                ))}
              </Space>
            </div>
          </div>
        )}
      </div>
    </Card>
  )
}

/* ================================================================
   Compare View
   ================================================================ */

function CompareView({ jobs }: { jobs: Array<{ id: string; label: string; prompt: string; response: RecommendationResponse | null; error: string | null }> }) {
  const columns: ColumnsType<typeof jobs[number]> = [
    {
      title: '查询画像',
      dataIndex: 'label',
      key: 'label',
      width: 130,
      render: (_: string, record: typeof jobs[number]) => {
        const pq = PRESET_QUERIES.find((p) => record.label === p.label)
        return (
          <Space size={4}>
            {pq ? PRESET_ICON_MAP[pq.icon] : null}
            <Text strong style={{ fontSize: 13 }}>{record.label}</Text>
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
        <Text ellipsis style={{ maxWidth: 170, fontSize: 11 }} type="secondary">{val}</Text>
      ),
    },
    {
      title: '推荐数',
      key: 'count',
      width: 70,
      align: 'center',
      render: (_: unknown, record: typeof jobs[number]) => (
        <Tag style={{ background: '#e8eef4', color: '#1e3a5f', border: 'none' }}>
          {record.response?.courses.length ?? 0}
        </Tag>
      ),
    },
    {
      title: 'Top 3 推荐',
      key: 'top',
      width: 200,
      render: (_: unknown, record: typeof jobs[number]) => (
        <Space direction="vertical" size={1}>
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
      sorter: (a, b) => (a.response?.total_latency_ms ?? 0) - (b.response?.total_latency_ms ?? 0),
      render: (_: unknown, record: typeof jobs[number]) => {
        const t = record.response?.total_latency_ms
        return (
          <Tag style={{
            fontSize: 11, border: 'none',
            background: t && t < 3000 ? '#f0faf4' : '#fef3c7',
            color: t && t < 3000 ? '#166534' : '#92400e',
          }}>
            {t ? `${t.toFixed(0)} ms` : '-'}
          </Tag>
        )
      },
    },
    {
      title: 'Agent 状态',
      key: 'agents',
      width: 140,
      render: (_: unknown, record: typeof jobs[number]) => {
        if (!record.response) return <Text type="secondary">-</Text>
        const agents = Object.values(record.response.agent_results)
        const ok = agents.filter((a) => a.success).length
        return (
          <Space size={3}>
            {agents.map((a) => (
              <Tooltip key={a.agent_name} title={`${PHASE_MAP[a.agent_name]?.label || a.agent_name}: ${a.latency_ms.toFixed(0)}ms`}>
                <CheckCircleOutlined style={{ fontSize: 11, color: a.success ? '#2d6a4f' : '#a52a2a' }} />
              </Tooltip>
            ))}
            <Text type="secondary" style={{ fontSize: 10, marginLeft: 2 }}>{ok}/{agents.length}</Text>
          </Space>
        )
      },
    },
    {
      title: '提醒',
      key: 'warnings',
      width: 55,
      align: 'center',
      render: (_: unknown, record: typeof jobs[number]) => {
        const n = record.response?.selection_warnings.length ?? 0
        return n > 0
          ? <Tag style={{ border: 'none', background: '#fef3c7', color: '#92400e' }}>{n}</Tag>
          : <Text type="secondary">0</Text>
      },
    },
  ]

  return (
    <div>
      <div style={{
        marginBottom: 16, padding: '12px 16px', borderRadius: 8,
        background: '#e8eef4', border: '1px solid #d0dce8',
      }}>
        <Text type="secondary" style={{ fontSize: 13 }}>
          <ThunderboltOutlined style={{ marginRight: 6, color: '#1e3a5f' }} />
          同时提交 <Text strong style={{ color: '#1e3a5f' }}>5 组不同学生画像</Text> 的选课需求，对比多 Agent 系统的推荐差异 ——
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
                  <PipelineTimeline agentResults={record.response.agent_results} totalLatency={record.response.total_latency_ms} />
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
                            <CommentOutlined />
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
