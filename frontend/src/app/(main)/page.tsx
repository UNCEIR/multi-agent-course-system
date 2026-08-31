'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Button, Card, Empty, Tag, Typography } from 'antd'
import {
  MessageOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  SmileOutlined,
  DatabaseOutlined,
  DashboardOutlined,
  BulbOutlined,
  ArrowRightOutlined,
  LogoutOutlined,
  CrownOutlined,
  BookOutlined,
} from '@ant-design/icons'
import { useAuthStore } from '../../stores/auth'
import { useSessionStore } from '../../stores/session'
import { api } from '../../lib/api'

const { Text, Title, Paragraph } = Typography

interface AgentCard {
  key: string
  title: string
  desc: string
  icon: React.ReactNode
  path: string
  roles: Array<'student' | 'teacher'>
  accent: string
}

const AGENTS: AgentCard[] = [
  {
    key: 'chat',
    title: '智能对话',
    desc: '知识库问答 · 课程推荐 · 论文写作 · 网页搜索 · 图片生成，多轮会话可延续',
    icon: <MessageOutlined />,
    path: '/chat',
    roles: ['student', 'teacher'],
    accent: 'linear-gradient(135deg, #2E6FBF, #4A90D9)',
  },
  {
    key: 'recommend',
    title: '推荐选课',
    desc: '描述你的偏好，AI 并行分析画像与课程匹配度，生成带理由的公选课推荐',
    icon: <ExperimentOutlined />,
    path: '/recommend',
    roles: ['student'],
    accent: 'linear-gradient(135deg, #14B8A6, #4A90D9)',
  },
  {
    key: 'report',
    title: '成绩报告',
    desc: '批量成绩单 Excel 一键生成逐学生 PDF 报告，含 LLM 综合评价与下载链接',
    icon: <FileTextOutlined />,
    path: '/report',
    roles: ['teacher'],
    accent: 'linear-gradient(135deg, #4A90D9, #2E6FBF)',
  },
  {
    key: 'evaluation',
    title: '评价寄语',
    desc: '基于成绩单数据生成雷达画像与评语寄语，反幻觉核验，学生端可查看',
    icon: <SmileOutlined />,
    path: '/evaluation',
    roles: ['teacher', 'student'],
    accent: 'linear-gradient(135deg, #1FA88D, #14B8A6)',
  },
  {
    key: 'documents',
    title: '知识库',
    desc: '上传文档自动解析、分块、向量化入库，为智能对话提供检索知识',
    icon: <DatabaseOutlined />,
    path: '/documents',
    roles: ['student', 'teacher'],
    accent: 'linear-gradient(135deg, #2E6FBF, #1FA88D)',
  },
  {
    key: 'experiments',
    title: '实验中心',
    desc: 'A/B 实验状态、分组统计与 Pipeline / ReAct 模式对比分析',
    icon: <BulbOutlined />,
    path: '/experiments',
    roles: ['student', 'teacher'],
    accent: 'linear-gradient(135deg, #E8A23D, #14B8A6)',
  },
  {
    key: 'monitor',
    title: '系统监控',
    desc: '服务健康、Agent 指标与系统运行状态实时洞察',
    icon: <DashboardOutlined />,
    path: '/monitor',
    roles: ['student', 'teacher'],
    accent: 'linear-gradient(135deg, #6B7A8D, #4A90D9)',
  },
]

export default function HubPage() {
  const router = useRouter()
  const { user, logout } = useAuthStore()
  const sessionStore = useSessionStore()

  useEffect(() => {
    useAuthStore.getState().hydrate()
    if (user?.user_id) {
      sessionStore.setUser(user.user_id)
      api
        .listSessions(user.user_id)
        .then((res) => sessionStore.setSessions(res.sessions))
        .catch(() => {})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.user_id])

  if (!user) {
    return (
      <Card className="glass-card" style={{ maxWidth: 560, margin: '80px auto', borderRadius: 16 }} styles={{ body: { padding: 40, textAlign: 'center' } }}>
        <Title level={3} style={{ fontFamily: "'Noto Serif SC', serif", color: '#16365C' }}>
          欢迎来到校园智能体平台
        </Title>
        <Paragraph type="secondary">登录后进入各智能体服务，会话与记忆将按你的身份持久保存。</Paragraph>
        <Button type="primary" size="large" icon={<ArrowRightOutlined />} onClick={() => router.push('/login')}>
          登录 / 注册
        </Button>
      </Card>
    )
  }

  const visible = AGENTS.filter((a) => a.roles.includes(user.role))
  const totalSessions = sessionStore.sessions.length

  return (
    <div className="stagger">
      {/* 品牌区 */}
      <div style={{ textAlign: 'center', margin: '28px 0 36px' }}>
        <div
          style={{
            width: 64,
            height: 64,
            margin: '0 auto 16px',
            borderRadius: 18,
            background: 'linear-gradient(135deg, #2E6FBF, #14B8A6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontSize: 30,
            boxShadow: '0 8px 28px rgba(46,111,191,0.35)',
          }}
        >
          <BookOutlined />
        </div>
        <Title level={2} style={{ margin: 0, fontFamily: "'Noto Serif SC', serif", color: '#16365C', letterSpacing: '0.04em' }}>
          大学校园多智能体平台
        </Title>
        <Text type="secondary" style={{ fontSize: 14 }}>创新实验室 · 你的 AI 校园助手</Text>
        <div style={{ marginTop: 14 }}>
          <Tag icon={user.role === 'teacher' ? <CrownOutlined /> : <BookOutlined />} color={user.role === 'teacher' ? 'cyan' : 'blue'}>
            {user.role === 'teacher' ? '老师' : '学生'} · {user.name}（{user.user_id}）
          </Tag>
          <Tag color="geekblue">会话 {totalSessions}</Tag>
          <Button size="small" type="text" icon={<LogoutOutlined />} onClick={() => { logout(); router.push('/login') }}>
            退出登录
          </Button>
        </div>
      </div>

      {/* 智能体卡片阵列 */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
          gap: 20,
          maxWidth: 1200,
          margin: '0 auto',
        }}
      >
        {visible.map((agent) => (
          <Card
            key={agent.key}
            hoverable
            className="glass-card"
            style={{ borderRadius: 16, borderColor: 'rgba(207,227,245,0.9)' }}
            styles={{ body: { padding: 22 } }}
            onClick={() => router.push(agent.path)}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
              <div
                style={{
                  width: 48,
                  height: 48,
                  borderRadius: 14,
                  background: agent.accent,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#fff',
                  fontSize: 22,
                  flexShrink: 0,
                  boxShadow: '0 4px 14px rgba(46,111,191,0.25)',
                }}
              >
                {agent.icon}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Text strong style={{ fontSize: 16, color: '#16365C' }}>{agent.title}</Text>
                  <ArrowRightOutlined style={{ color: '#4A90D9', fontSize: 13 }} />
                </div>
                <Paragraph type="secondary" style={{ margin: '6px 0 0', fontSize: 13, lineHeight: 1.7 }}>
                  {agent.desc}
                </Paragraph>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {visible.length === 0 && <Empty description="当前角色暂无可用的智能体" style={{ marginTop: 60 }} />}
    </div>
  )
}
