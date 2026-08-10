import { useLocation, useNavigate } from 'react-router-dom'
import { Layout as AntLayout, Menu } from 'antd'
import {
  ExperimentOutlined,
  DashboardOutlined,
  BookOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons'
import { useEffect, useState } from 'react'
import { api } from '../services/api'
import RecommendPage from '../pages/RecommendPage'
import MonitorPage from '../pages/MonitorPage'

const { Header, Content } = AntLayout

export default function Layout() {
  const location = useLocation()
  const navigate = useNavigate()
  const [apiStatus, setApiStatus] = useState<'online' | 'offline' | 'checking'>('checking')

  useEffect(() => {
    let cancelled = false
    const check = () => {
      api.health()
        .then((h) => { if (!cancelled) setApiStatus(h.status === 'healthy' ? 'online' : 'offline') })
        .catch(() => { if (!cancelled) setApiStatus('offline') })
    }
    check()
    const interval = setInterval(check, 15000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  const statusIcon = apiStatus === 'online'
    ? <CheckCircleOutlined style={{ color: '#2d6a4f', fontSize: 14 }} />
    : apiStatus === 'offline'
    ? <ExclamationCircleOutlined style={{ color: '#a52a2a', fontSize: 14 }} />
    : <SyncOutlined spin style={{ color: '#c88c3e', fontSize: 14 }} />

  const statusText = apiStatus === 'online' ? 'API 在线' : apiStatus === 'offline' ? 'API 离线' : '检测中'

  const currentKey = location.pathname.startsWith('/monitor') ? '/monitor' : '/'

  const menuItems = [
    {
      key: '/',
      icon: <ExperimentOutlined />,
      label: '推荐演示',
    },
    {
      key: '/monitor',
      icon: <DashboardOutlined />,
      label: '系统监控',
    },
  ]

  return (
    <AntLayout style={{ minHeight: '100vh', background: '#faf8f5' }}>
      <Header
        style={{
          background: 'rgba(255,255,255,0.92)',
          backdropFilter: 'blur(12px)',
          display: 'flex',
          alignItems: 'center',
          padding: '0 24px',
          borderBottom: '1px solid #e8e0d5',
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
              borderRadius: 8,
              background: 'linear-gradient(135deg, #1e3a5f 0%, #2d5a8e 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#fff',
              fontSize: 16,
            }}
            aria-hidden="true"
          >
            <BookOutlined />
          </div>
          <span
            style={{
              fontSize: 15,
              fontWeight: 700,
              fontFamily: "'Noto Serif SC', serif",
              letterSpacing: '0.03em',
              color: '#1a1a2e',
              whiteSpace: 'nowrap',
            }}
          >
            大学校园多智能体平台
          </span>
        </div>

        <Menu
          mode="horizontal"
          selectedKeys={[currentKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ flex: 1, border: 'none', background: 'transparent', fontWeight: 500 }}
        />

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '4px 12px',
            borderRadius: 20,
            background: apiStatus === 'online' ? '#f0faf4' : apiStatus === 'offline' ? '#fef2f2' : '#fefbea',
            border: `1px solid ${apiStatus === 'online' ? '#c6f0d7' : apiStatus === 'offline' ? '#fecaca' : '#fde68a'}`,
            fontSize: 12,
            color: apiStatus === 'online' ? '#166534' : apiStatus === 'offline' ? '#991b1b' : '#92400e',
          }}
          aria-label={`API 状态: ${statusText}`}
        >
          {statusIcon}
          <span>{statusText}</span>
        </div>
      </Header>

      <Content style={{ padding: 24, maxWidth: 1400, margin: '0 auto', width: '100%' }}>
        <div style={{ display: currentKey === '/' ? 'block' : 'none' }}>
          <RecommendPage />
        </div>
        <div style={{ display: currentKey === '/monitor' ? 'block' : 'none' }}>
          <MonitorPage />
        </div>
      </Content>
    </AntLayout>
  )
}
