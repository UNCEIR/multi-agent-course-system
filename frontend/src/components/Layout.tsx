import { Outlet, NavLink, useLocation } from 'react-router-dom'
import { Layout as AntLayout, Menu, Badge } from 'antd'
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

const { Header, Content } = AntLayout

export default function Layout() {
  const location = useLocation()
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

  const menuItems = [
    {
      key: '/',
      icon: <ExperimentOutlined />,
      label: <NavLink to="/">推荐演示</NavLink>,
    },
    {
      key: '/monitor',
      icon: <DashboardOutlined />,
      label: <NavLink to="/monitor">系统监控</NavLink>,
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
            公选课多Agent推荐系统
          </span>
        </div>

        <Menu
          mode="horizontal"
          selectedKeys={[location.pathname]}
          items={menuItems}
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
        <Outlet />
      </Content>
    </AntLayout>
  )
}
