'use client'

import { usePathname, useRouter } from 'next/navigation'
import { App, ConfigProvider, Layout as AntLayout, Menu } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import {
  ExperimentOutlined,
  DashboardOutlined,
  HomeOutlined,
  MessageOutlined,
  FileTextOutlined,
  SmileOutlined,
  DatabaseOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  SyncOutlined,
  BulbOutlined,
} from '@ant-design/icons'
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { antdThemeConfig } from '../../lib/theme'

const { Header, Content } = AntLayout

const MENU_ITEMS = [
  { key: '/', icon: <HomeOutlined />, label: '智能体入口' },
  { key: '/chat', icon: <MessageOutlined />, label: '智能对话' },
  { key: '/recommend', icon: <ExperimentOutlined />, label: '推荐选课' },
  { key: '/report', icon: <FileTextOutlined />, label: '成绩报告' },
  { key: '/evaluation', icon: <SmileOutlined />, label: '评价寄语' },
  { key: '/documents', icon: <DatabaseOutlined />, label: '知识库' },
  { key: '/experiments', icon: <BulbOutlined />, label: '实验中心' },
  { key: '/monitor', icon: <DashboardOutlined />, label: '系统监控' },
]

export default function MainLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const [apiStatus, setApiStatus] = useState<'online' | 'offline' | 'checking'>('checking')

  useEffect(() => {
    let cancelled = false
    const check = () => {
      api
        .health()
        .then((h) => {
          if (!cancelled) setApiStatus(h.status === 'healthy' ? 'online' : 'offline')
        })
        .catch(() => {
          if (!cancelled) setApiStatus('offline')
        })
    }
    check()
    const interval = setInterval(check, 15000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  const statusIcon =
    apiStatus === 'online' ? (
      <CheckCircleOutlined style={{ color: '#1FA88D', fontSize: 14 }} />
    ) : apiStatus === 'offline' ? (
      <ExclamationCircleOutlined style={{ color: '#D64545', fontSize: 14 }} />
    ) : (
      <SyncOutlined spin style={{ color: '#14B8A6', fontSize: 14 }} />
    )

  const statusText = apiStatus === 'online' ? 'API 在线' : apiStatus === 'offline' ? 'API 离线' : '检测中'
  const currentKey = MENU_ITEMS.find((m) => pathname === m.key)?.key ?? '/'

  return (
    <ConfigProvider locale={zhCN} theme={antdThemeConfig}>
      {/* App context 提供 message/notification/modal 实例，避免静态 message.* 警告 */}
      <App>
        <AntLayout style={{ minHeight: '100vh', background: 'transparent' }}>
          <Header
            style={{
              background: 'rgba(255,255,255,0.85)',
              backdropFilter: 'blur(12px)',
              display: 'flex',
              alignItems: 'center',
              padding: '0 24px',
              borderBottom: '1px solid #CFE3F5',
              position: 'sticky',
              top: 0,
              zIndex: 100,
              height: 56,
            }}
            aria-label="主导航"
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginRight: 36 }}>
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: 9,
                  background: 'linear-gradient(135deg, #2E6FBF 0%, #14B8A6 100%)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#fff',
                  fontSize: 16,
                  boxShadow: '0 2px 10px rgba(46,111,191,0.35)',
                }}
                aria-hidden="true"
              >
                <MessageOutlined />
              </div>
              <span
                style={{
                  fontSize: 15,
                  fontWeight: 700,
                  fontFamily: "'Noto Serif SC', serif",
                  letterSpacing: '0.03em',
                  color: '#16365C',
                  whiteSpace: 'nowrap',
                }}
              >
                大学校园多智能体平台
              </span>
            </div>

            <Menu
              mode="horizontal"
              selectedKeys={[currentKey]}
              items={MENU_ITEMS}
              onClick={({ key }) => router.push(key)}
              style={{
                flex: 1,
                minWidth: 0,
                border: 'none',
                background: 'transparent',
                fontWeight: 500,
              }}
            />

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '4px 12px',
                borderRadius: 20,
                background: apiStatus === 'online' ? '#E6F7F3' : apiStatus === 'offline' ? '#FDECEC' : '#FEF7E0',
                border: `1px solid ${apiStatus === 'online' ? '#C6EDE4' : apiStatus === 'offline' ? '#F5C6C6' : '#F5DFA8'}`,
                fontSize: 12,
                color: apiStatus === 'online' ? '#147D64' : apiStatus === 'offline' ? '#C0392B' : '#B9772E',
                flexShrink: 0,
                whiteSpace: 'nowrap',
              }}
              aria-label={`API 状态: ${statusText}`}
            >
              {statusIcon}
              <span style={{ lineHeight: 1.5 }}>{statusText}</span>
            </div>
          </Header>

          <Content style={{ padding: 24, maxWidth: 1400, margin: '0 auto', width: '100%', position: 'relative', zIndex: 1 }}>
            {children}
          </Content>
        </AntLayout>
      </App>
    </ConfigProvider>
  )
}
