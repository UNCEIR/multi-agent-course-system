'use client'

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
  Space,
  Typography,
} from 'antd'
import {
  BulbOutlined,
  CodeOutlined,
  ExperimentOutlined,
  SendOutlined,
  SettingOutlined,
  ThunderboltOutlined,
  BookOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons'
import { api } from '@/lib/api'
import { useNotify } from '@/lib/api/useNotify'
import {
  useRecommendStore,
  useActiveJobStore,
  useInputStore,
} from '@/stores'
import type {
  PresetQuery,
  RecommendationRequest,
  RecommendationResponse,
  StreamDonePayload,
} from '@/types'
import StreamView from '@/components/StreamView'
import SingleResultView from '@/components/recommend/SingleResultView'
import CompareView from '@/components/recommend/CompareView'
import { PRESET_QUERIES, PRESET_ICON_MAP } from '@/components/recommend/constants'

const { TextArea } = Input
const { Text } = Typography

// 统一入口兜底：消费 /recommend/stream 到 done，转同步响应（经典模式 / 批量对比共用）
async function fetchRecommendSync(
  body: RecommendationRequest,
): Promise<RecommendationResponse> {
  let done: StreamDonePayload | null = null
  for await (const evt of api.recommendStream(body)) {
    if (evt.event === 'done') done = evt.data
    if (evt.event === 'error') throw new Error(evt.data.message || '推荐失败')
  }
  if (!done) throw new Error('流式响应未返回 done')
  return {
    request_id: done.request_id,
    user_id: done.user_id,
    courses: done.courses,
    recommendation_reasons: done.recommendation_reasons,
    selection_warnings: done.selection_warnings,
    priority_advice: {},
    experiment_group: done.experiment_group,
    agent_results: done.agent_results,
    agent_latencies: {},
    total_latency_ms: done.total_latency_ms,
    timestamp: new Date().toISOString(),
  }
}

export default function RecommendPage() {
  const notify = useNotify()
  const prompt = useInputStore((s) => s.prompt)
  const numItems = useInputStore((s) => s.numItems)
  const setPrompt = useInputStore((s) => s.setPrompt)
  const setNumItems = useInputStore((s) => s.setNumItems)

  const [activeTab, setActiveTab] = useState('stream')
  const [streamKey, setStreamKey] = useState(0)
  const [streamMode, setStreamMode] = useState<'pipeline' | 'react'>('pipeline')
  const [streamPrompt, setStreamPrompt] = useState('')
  const [streamNumItems, setStreamNumItems] = useState(5)

  const { jobs, addJob, setResponse, setError } = useRecommendStore()
  const { activeId, setActive } = useActiveJobStore()

  const requirePrompt = useCallback((): string | null => {
    const query = prompt.trim()
    if (!query) {
      notify.toast.warning('请输入选课需求描述')
      return null
    }
    return query
  }, [prompt, notify])

  const handleStreamSubmit = useCallback(() => {
    const query = requirePrompt()
    if (query === null) return
    setStreamPrompt(query)
    setStreamNumItems(numItems)
    setStreamMode('pipeline')
    setStreamKey((k) => k + 1)
    setActiveTab('stream')
  }, [requirePrompt, numItems])

  const handleSubmit = useCallback(async () => {
    const query = requirePrompt()
    if (query === null) return
    setActiveTab('single')
    const uid = `user_${Date.now()}`
    addJob(uid, '自定义查询', query)
    setActive(uid)
    try {
      const res = await fetchRecommendSync({
        user_id: uid,
        prompt: query,
        num_items: numItems,
        scene: 'course_selection',
      })
      setResponse(uid, res)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '请求失败'
      setError(uid, msg)
      notify.toast.error(e, `推荐请求失败：${msg}`)
    }
  }, [requirePrompt, numItems, addJob, setActive, setResponse, setError, notify])

  const handleReactSubmit = useCallback(() => {
    const query = requirePrompt()
    if (query === null) return
    setStreamPrompt(query)
    setStreamNumItems(numItems)
    setStreamMode('react')
    setStreamKey((k) => k + 1)
    setActiveTab('stream')
  }, [requirePrompt, numItems])

  const handlePresetClick = useCallback(
    (pq: PresetQuery) => {
      setPrompt(pq.prompt)
      setStreamPrompt(pq.prompt)
      setStreamNumItems(numItems)
      setStreamMode('pipeline')
      setStreamKey((k) => k + 1)
      setActiveTab('stream')
    },
    [numItems, setPrompt],
  )

  const handleCompareAll = useCallback(async () => {
    setActiveTab('compare')
    const jobDefs = PRESET_QUERIES.map((pq) => ({
      id: `${pq.id}_${Date.now()}`,
      label: pq.label,
      prompt: pq.prompt,
    }))
    for (const j of jobDefs) addJob(j.id, j.label, j.prompt)
    const results = await Promise.allSettled(
      jobDefs.map((j) =>
        fetchRecommendSync({
          user_id: j.id,
          prompt: j.prompt,
          num_items: numItems,
          scene: 'course_selection',
        }),
      ),
    )
    results.forEach((r, i) => {
      if (r.status === 'fulfilled') setResponse(jobDefs[i].id, r.value)
      else setError(jobDefs[i].id, r.reason?.message || '请求失败')
    })
    setActive(jobDefs[0].id)
  }, [numItems, addJob, setResponse, setError, setActive])

  const activeJob = jobs.find((j) => j.id === activeId)
  const compareJobs = jobs
    .filter((j) => j.response && !j.error)
    .slice(-5)

  return (
    <div>
      <Card
        className="animate-fade-scale"
        style={{ marginBottom: 24, border: '1px solid #CFE3F5' }}
        styles={{
          body: { padding: 24 },
          header: {
            borderBottom: '1px solid #EAF2FB',
            padding: '16px 24px',
            fontWeight: 600,
          },
        }}
        title={
          <Space>
            <BulbOutlined style={{ color: '#14B8A6' }} aria-hidden="true" />
            <span className="serif-heading" style={{ fontSize: 15 }}>
              选课需求描述
            </span>
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
          aria-label="选课需求描述"
        />

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <Space
            size="small"
            style={{ background: '#EAF3FC', padding: '6px 14px', borderRadius: 8 }}
          >
            <SettingOutlined style={{ color: '#6B7A8D' }} aria-hidden="true" />
            <Text type="secondary" style={{ fontSize: 13 }}>
              推荐数量
            </Text>
            <Slider
              min={1}
              max={10}
              value={numItems}
              onChange={setNumItems}
              style={{ width: 100 }}
              aria-label="推荐数量"
            />
            <Tag
              style={{
                background: '#EAF2FB',
                color: '#16365C',
                border: 'none',
                fontWeight: 500,
              }}
              aria-label={`当前推荐数量 ${numItems}`}
            >
              {numItems}
            </Tag>
          </Space>

          <div style={{ flex: 1 }} />

          <Space>
            <Button
              type="primary"
              icon={<SendOutlined aria-hidden="true" />}
              onClick={handleStreamSubmit}
              size="large"
            >
              开始推荐
            </Button>
            <Button
              icon={<ExperimentOutlined aria-hidden="true" />}
              onClick={handleSubmit}
              size="large"
            >
              经典模式
            </Button>
            <Button
              icon={<CodeOutlined aria-hidden="true" />}
              onClick={handleReactSubmit}
              size="large"
            >
              ReAct 推荐
            </Button>
            <Button
              style={{ borderColor: '#14B8A6', color: '#14B8A6' }}
              icon={<ThunderboltOutlined aria-hidden="true" />}
              onClick={handleCompareAll}
              size="large"
            >
              批量对比 5 组查询
            </Button>
          </Space>
        </div>

        <div style={{ marginTop: 16 }}>
          <Text type="secondary" style={{ fontSize: 12, marginRight: 10 }}>
            快速预设：
          </Text>
          <Space wrap size={[6, 6]}>
            {PRESET_QUERIES.map((pq) => (
              <button
                key={pq.id}
                type="button"
                onClick={() => handlePresetClick(pq)}
                style={{
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 5,
                  padding: '4px 14px',
                  borderRadius: 20,
                  border: '1px solid #CFE3F5',
                  background: '#fff',
                  fontSize: 13,
                  color: '#6B7A8D',
                  transition:
                    'all 180ms cubic-bezier(0.16, 1, 0.3, 1)',
                  fontFamily: 'inherit',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = '#16365C'
                  e.currentTarget.style.color = '#16365C'
                  e.currentTarget.style.background = '#EAF2FB'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = '#CFE3F5'
                  e.currentTarget.style.color = '#6B7A8D'
                  e.currentTarget.style.background = '#fff'
                }}
                onFocus={(e) => {
                  e.currentTarget.style.borderColor = '#16365C'
                  e.currentTarget.style.boxShadow =
                    '0 0 0 2px rgba(30,58,95,0.12)'
                }}
                onBlur={(e) => {
                  e.currentTarget.style.boxShadow = 'none'
                }}
                aria-label={`使用预设：${pq.label}（${pq.prompt.slice(0, 20)}...）`}
              >
                <span aria-hidden="true">{PRESET_ICON_MAP[pq.icon]}</span>
                {pq.label}
              </button>
            ))}
          </Space>
        </div>
      </Card>

      <Card
        className="animate-fade-in"
        style={{ border: '1px solid #CFE3F5' }}
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
                  <SendOutlined aria-hidden="true" />
                  <span>流式对话</span>
                  {streamKey > 0 && (
                    <Tag
                      style={{
                        background: '#E6F7F3',
                        color: '#147D64',
                        border: 'none',
                        marginLeft: 4,
                      }}
                    >
                      实时
                    </Tag>
                  )}
                </Space>
              ),
              children:
                streamKey > 0 ? (
                  <StreamView
                    key={`${streamKey}-${streamMode}`}
                    prompt={streamPrompt}
                    numItems={streamNumItems}
                    mode={streamMode}
                    onRetry={() => {
                      setStreamKey((k) => k + 1)
                    }}
                  />
                ) : (
                  <div className="animate-fade-in">
                    <Empty
                      image={
                        <SendOutlined
                          style={{ fontSize: 48, color: '#14B8A6' }}
                        />
                      }
                      description="输入选课需求，点击「开始推荐」或选择预设查询，AI 将逐字生成推荐反馈"
                    />
                  </div>
                ),
            },
            {
              key: 'single',
              label: (
                <Space size={4}>
                  <ExperimentOutlined aria-hidden="true" />
                  <span>经典结果</span>
                </Space>
              ),
              children: activeJob?.response ? (
                <SingleResultView response={activeJob.response} />
              ) : activeJob?.loading ? (
                <div style={{ textAlign: 'center', padding: 80 }}>
                  <Spin size="large" tip="AI Agent 正在分析中...">
                    <div style={{ marginTop: 40 }} />
                  </Spin>
                </div>
              ) : activeJob?.error ? (
                <div className="animate-fade-in">
                  <Empty
                    image={
                      <CloseCircleOutlined
                        style={{ fontSize: 48, color: '#D64545' }}
                      />
                    }
                    description={
                      <Text type="danger">{activeJob.error}</Text>
                    }
                  />
                </div>
              ) : (
                <div className="animate-fade-in">
                  <Empty
                    image={
                      <BookOutlined
                        style={{ fontSize: 48, color: '#14B8A6' }}
                      />
                    }
                    description="输入选课需求，点击「开始推荐」或选择预设查询查看结果"
                  />
                </div>
              ),
            },
            {
              key: 'compare',
              label: (
                <Space size={4}>
                  <ThunderboltOutlined aria-hidden="true" />
                  <span>多查询对比</span>
                  {compareJobs.length > 0 && (
                    <Tag
                      style={{
                        background: '#EAF2FB',
                        color: '#16365C',
                        border: 'none',
                        marginLeft: 4,
                      }}
                      aria-label={`已对比 ${compareJobs.length} 组查询`}
                    >
                      {compareJobs.length}
                    </Tag>
                  )}
                </Space>
              ),
              children:
                compareJobs.length > 0 ? (
                  <CompareView
                    jobs={jobs
                      .filter((j) => j.response && !j.error)
                      .slice(-5)}
                  />
                ) : (
                  <Empty
                    image={
                      <ThunderboltOutlined
                        style={{ fontSize: 48, color: '#14B8A6' }}
                      />
                    }
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
