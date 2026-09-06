'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button, Card, Dropdown, Empty, Input, List, Space, Spin, Tag, Typography } from 'antd'
import {
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  ReloadOutlined,
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  MoreOutlined,
} from '@ant-design/icons'
import { api } from '../../../lib/api'
import { useAuthStore } from '../../../stores/auth'
import { useSessionStore } from '../../../stores/session'
import { useNotify } from '../../../lib/api/useNotify'
import AgentActivityTimeline, { type ToolActivity } from '../../../components/AgentActivityTimeline'
import MarkdownContent from '../../../components/MarkdownContent'
import type { AgentTreeNode } from '../../../types/sse'

const { TextArea } = Input
const { Text } = Typography

interface ChatItem {
  role: 'user' | 'assistant'
  content: string
  tools: ToolActivity[]
  usage?: Record<string, unknown>
  latency_ms?: number | null
  agentTree?: AgentTreeNode[]
  error?: string
}

export default function ChatPage() {
  const router = useRouter()
  const { user } = useAuthStore()
  const sessionStore = useSessionStore()
  const notify = useNotify()
  const [items, setItems] = useState<ChatItem[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  // 登录态 → 初始化会话 store 并刷新列表
  useEffect(() => {
    useAuthStore.getState().hydrate()
  }, [])
  useEffect(() => {
    if (user?.user_id) {
      sessionStore.setUser(user.user_id)
      refreshSessions()
    }
    // 仅依赖 user_id；refreshSessions / sessionStore 来自 store，引用稳定
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.user_id])

  const refreshSessions = useCallback(async () => {
    if (!user?.user_id) return
    try {
      const res = await api.listSessions(user.user_id)
      sessionStore.setSessions(res.sessions)
    } catch {
      // 列表失败不阻塞对话
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.user_id])

  // 切换/进入会话 → 回显历史消息
  useEffect(() => {
    if (!user?.user_id || !sessionStore.activeSessionId) return
    let cancelled = false
    setLoadingHistory(true)
    setItems([])
    api
      .sessionMessages(sessionStore.activeSessionId, user.user_id)
      .then((res) => {
        if (cancelled) return
        const restored: ChatItem[] = []
        for (const m of res.messages) {
          if (m.role === 'user') {
            restored.push({ role: 'user', content: m.content ?? '', tools: [] })
          } else if (m.role === 'assistant') {
            restored.push({ role: 'assistant', content: m.content ?? '', tools: [] })
          }
        }
        setItems(restored)
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoadingHistory(false)
      })
    return () => {
      cancelled = true
    }
  }, [sessionStore.activeSessionId, user?.user_id])

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [items])

  const handleNewSession = () => {
    sessionStore.newSession()
    setItems([])
  }

  const handleSwitch = (sessionId: string) => {
    sessionStore.setActive(sessionId)
  }

  const handleDelete = async (sessionId: string) => {
    if (!user?.user_id) return
    try {
      await api.closeSession(sessionId, user.user_id)
      sessionStore.removeSession(sessionId)
      notify.toast.success('会话已删除')
    } catch (e: unknown) {
      notify.toast.error(e, '删除失败')
    }
  }

  const handleRename = async (sessionId: string) => {
    const title = renameValue.trim()
    if (!title || !user?.user_id) return
    try {
      await api.renameSession(sessionId, user.user_id, title)
      setRenamingId(null)
      refreshSessions()
      notify.toast.success('已重命名')
    } catch (e: unknown) {
      notify.toast.error(e, '重命名失败')
    }
  }

  const handleSend = useCallback(
    async (retryContent?: string) => {
      const content = (retryContent ?? input).trim()
      if (!content || streaming) return
      if (!user?.user_id) {
        notify.toast.warning('请先登录')
        router.push('/login')
        return
      }
      // 无会话则新建
      const sessionId = sessionStore.activeSessionId ?? sessionStore.newSession()
      if (sessionStore.activeSessionId == null) {
        sessionStore.setActive(sessionId)
      }
      setInput('')
      setStreaming(true)
      setItems((prev) => [
        ...prev,
        { role: 'user', content, tools: [] },
        { role: 'assistant', content: '', tools: [] },
      ])

      const ac = new AbortController()
      const body = { message: content, session_id: sessionId, user_id: user.user_id }
      try {
        for await (const evt of api.chatStreamWithRetry(body, ac.signal)) {
          if (evt.event === 'text') {
            const token = evt.data.token
            setItems((prev) => {
              const next = [...prev]
              const last = next[next.length - 1]
              if (last && last.role === 'assistant') last.content += token
              return next
            })
          } else if (evt.event === 'tool') {
            const tool = evt.data.tool
            const result = evt.data.result
            setItems((prev) => {
              const next = [...prev]
              const last = next[next.length - 1]
              if (last && last.role === 'assistant') {
                const exist = last.tools.find((t) => t.name === tool)
                if (exist) {
                  exist.status = evt.data.status
                  if (result) exist.result = result
                } else {
                  last.tools.push({ name: tool, status: evt.data.status, result })
                }
              }
              return next
            })
          } else if (evt.event === 'done') {
            setItems((prev) => {
              const next = [...prev]
              const last = next[next.length - 1]
              if (last && last.role === 'assistant') {
                last.usage = evt.data.usage
                last.latency_ms = evt.data.latency_ms
                if (evt.data.agent_tree) last.agentTree = evt.data.agent_tree
              }
              return next
            })
          } else if (evt.event === 'error') {
            setItems((prev) => {
              const next = [...prev]
              const last = next[next.length - 1]
              if (last && last.role === 'assistant')
                last.error = `${evt.data.code}: ${evt.data.message}`
              return next
            })
          }
        }
        refreshSessions()
      } catch (e: unknown) {
        setItems((prev) => {
          const next = [...prev]
          const last = next[next.length - 1]
          if (last && last.role === 'assistant')
            last.error = e instanceof Error ? e.message : '请求失败'
          return next
        })
      } finally {
        setStreaming(false)
      }
    },
    // zustand store 对象引用稳定，不参与依赖；refreshSessions / notify.toast 同理
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      input,
      streaming,
      user?.user_id,
      sessionStore.activeSessionId,
      refreshSessions,
      router,
      notify.toast,
    ],
  )

  if (!user) {
    return (
      <Card
        className="glass-card"
        style={{ maxWidth: 480, margin: '80px auto', borderRadius: 16 }}
        styles={{ body: { padding: 40, textAlign: 'center' } }}
      >
        <Empty description="登录后开始智能对话，会话将持久保存" />
        <Button type="primary" style={{ marginTop: 12 }} onClick={() => router.push('/login')}>
          去登录
        </Button>
      </Card>
    )
  }

  return (
    <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
      {/* 左侧会话栏 */}
      <Card
        className="glass-card"
        style={{ width: 260, flexShrink: 0, borderRadius: 14 }}
        styles={{ body: { padding: 12 } }}
      >
        <Button
          type="primary"
          block
          icon={<PlusOutlined />}
          onClick={handleNewSession}
          style={{ marginBottom: 12 }}
        >
          新对话
        </Button>
        <div style={{ maxHeight: '62vh', overflowY: 'auto' }}>
          <List
            size="small"
            dataSource={sessionStore.sessions}
            locale={{
              emptyText: (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  暂无历史会话
                </Text>
              ),
            }}
            renderItem={(s) => (
              <div
                key={s.session_id}
                onClick={() => handleSwitch(s.session_id)}
                style={{
                  padding: '8px 10px',
                  borderRadius: 8,
                  cursor: 'pointer',
                  marginBottom: 4,
                  background:
                    s.session_id === sessionStore.activeSessionId ? '#EAF2FB' : 'transparent',
                  border:
                    s.session_id === sessionStore.activeSessionId
                      ? '1px solid #CFE3F5'
                      : '1px solid transparent',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 6,
                  }}
                >
                  {renamingId === s.session_id ? (
                    <Input
                      size="small"
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onPressEnter={() => handleRename(s.session_id)}
                      onBlur={() => setRenamingId(null)}
                      onClick={(e) => e.stopPropagation()}
                      autoFocus
                    />
                  ) : (
                    <Text
                      ellipsis
                      style={{
                        fontSize: 13,
                        color:
                          s.session_id === sessionStore.activeSessionId ? '#2E6FBF' : '#33475C',
                        fontWeight: 500,
                      }}
                    >
                      {s.display_title || s.title || '新对话'}
                    </Text>
                  )}
                  <Space size={0} onClick={(e) => e.stopPropagation()}>
                    <Dropdown
                      menu={{
                        items: [
                          {
                            key: 'rename',
                            icon: <EditOutlined />,
                            label: '重命名',
                            onClick: () => {
                              setRenamingId(s.session_id)
                              setRenameValue(s.display_title || s.title || '')
                            },
                          },
                          {
                            key: 'delete',
                            icon: <DeleteOutlined />,
                            label: '删除',
                            danger: true,
                            onClick: () => handleDelete(s.session_id),
                          },
                        ],
                      }}
                    >
                      <Button
                        type="text"
                        size="small"
                        icon={<MoreOutlined />}
                        style={{ fontSize: 11 }}
                      />
                    </Dropdown>
                  </Space>
                </div>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {s.message_count} 条消息
                </Text>
              </div>
            )}
          />
        </div>
      </Card>

      {/* 主对话区 */}
      <Card
        className="glass-card"
        style={{ flex: 1, minWidth: 0, borderRadius: 14 }}
        styles={{ body: { padding: 20 } }}
        title={
          <Space>
            <RobotOutlined style={{ color: '#2E6FBF' }} />
            <span className="serif-heading" style={{ fontSize: 15 }}>
              智能对话
            </span>
            <Text type="secondary" style={{ fontSize: 12 }}>
              知识库问答 / 课程推荐 / 写作 / 搜索 / 图片生成 · 会话跨页面持久
            </Text>
          </Space>
        }
      >
        <div
          ref={scrollRef}
          style={{ minHeight: 420, maxHeight: '56vh', overflowY: 'auto', paddingBottom: 16 }}
        >
          {loadingHistory ? (
            <div style={{ textAlign: 'center', padding: 60 }}>
              <Spin />
            </div>
          ) : items.length === 0 && !streaming ? (
            <Empty description="输入你想问的问题，例如：我适合选哪些公选课？奖学金申请条件是什么？" />
          ) : (
            items.map((item, idx) => (
              <div
                key={idx}
                style={{
                  marginBottom: 16,
                  display: 'flex',
                  gap: 10,
                  justifyContent: item.role === 'user' ? 'flex-end' : 'flex-start',
                }}
              >
                <div
                  style={{
                    maxWidth: '82%',
                    padding: '10px 14px',
                    borderRadius: 12,
                    background: item.role === 'user' ? '#EAF2FB' : '#F2F7FD',
                    border: '1px solid #CFE3F5',
                  }}
                >
                  <Space size={6} style={{ marginBottom: 6 }}>
                    {item.role === 'user' ? (
                      <UserOutlined style={{ color: '#2E6FBF' }} />
                    ) : (
                      <RobotOutlined style={{ color: '#14B8A6' }} />
                    )}
                    <Text strong style={{ fontSize: 12 }}>
                      {item.role === 'user' ? '我' : '助手'}
                    </Text>
                  </Space>
                  {item.role === 'user' ? (
                    <div
                      style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: '#33475C' }}
                    >
                      {item.content}
                    </div>
                  ) : (
                    <MarkdownContent content={item.content} />
                  )}
                  {item.tools.length > 0 && <AgentActivityTimeline tools={item.tools} />}
                  {item.agentTree && item.agentTree.length > 0 && (
                    <Space size={4} wrap style={{ marginTop: 4 }}>
                      {item.agentTree.map((n, i) => (
                        <Tag key={i} icon={<RobotOutlined />} color="geekblue">
                          {n.name} · {n.status}
                        </Tag>
                      ))}
                    </Space>
                  )}
                  {item.usage && (
                    <Text type="secondary" style={{ display: 'block', marginTop: 6, fontSize: 12 }}>
                      耗时 {item.latency_ms ? `${(item.latency_ms / 1000).toFixed(1)}s` : '—'}
                    </Text>
                  )}
                  {item.error && (
                    <Space orientation="vertical" style={{ marginTop: 8 }}>
                      <Text type="danger" style={{ fontSize: 12 }}>
                        {item.error}
                      </Text>
                      <Button
                        size="small"
                        icon={<ReloadOutlined />}
                        onClick={() => handleSend(item.content)}
                        disabled={streaming}
                      >
                        重试
                      </Button>
                    </Space>
                  )}
                </div>
              </div>
            ))
          )}
          {streaming && <Spin size="small" style={{ marginLeft: 12 }} />}
        </div>

        <Space.Compact style={{ width: '100%', marginTop: 8 }}>
          <TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            placeholder={`${sessionStore.activeSessionId ? '当前会话继续对话' : '新会话'} · Enter 发送 / Shift+Enter 换行`}
            autoSize={{ minRows: 1, maxRows: 4 }}
            disabled={streaming}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={() => handleSend()}
            loading={streaming}
          >
            发送
          </Button>
        </Space.Compact>
      </Card>
    </div>
  )
}
