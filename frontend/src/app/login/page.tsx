'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button, Card, ConfigProvider, Input, Segmented, Typography } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { LockOutlined, MessageOutlined, UserOutlined } from '@ant-design/icons'
import { App } from 'antd'
import { api } from '../../lib/api'
import { useAuthStore } from '../../stores/auth'
import { useNotify } from '../../lib/api/useNotify'
import { antdThemeConfig } from '../../lib/theme'

const { Text, Title } = Typography

export default function LoginPage() {
  const router = useRouter()
  const { user, hydrated, login } = useAuthStore()
  const notify = useNotify()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [userId, setUserId] = useState('')
  const [name, setName] = useState('')
  const [role, setRole] = useState('student')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    useAuthStore.getState().hydrate()
  }, [])

  useEffect(() => {
    if (hydrated && user) router.replace('/')
  }, [hydrated, user, router])

  const handleSubmit = async () => {
    if (!userId.trim() || !password.trim()) {
      notify.toast.warning('请输入学号/工号和密码')
      return
    }
    if (mode === 'register' && (!name.trim() || password.length < 6)) {
      notify.toast.warning('请输入姓名，密码至少 6 位')
      return
    }
    setSubmitting(true)
    try {
      if (mode === 'register') {
        await api.register({ user_id: userId.trim(), name: name.trim(), role, password })
        notify.toast.success('注册成功，请登录')
        setMode('login')
        return
      }
      const res = await api.login({ user_id: userId.trim(), password })
      login(res.user, res.token ?? '')
      notify.toast.success(`欢迎，${res.user.name}`)
      router.replace('/')
    } catch (e: unknown) {
      notify.toast.error(e, '操作失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <ConfigProvider locale={zhCN} theme={antdThemeConfig}>
      <App>
        <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 24,
          background:
            'radial-gradient(800px 400px at 20% 0%, rgba(74,144,217,0.20), transparent 60%), linear-gradient(180deg, #f0f7fe, #e0eefa)',
        }}
      >
        <Card className="glass-card animate-fade-scale" style={{ width: 420, borderRadius: 16 }} styles={{ body: { padding: 32 } }}>
          <div style={{ textAlign: 'center', marginBottom: 28 }}>
            <div
              style={{
                width: 56,
                height: 56,
                margin: '0 auto 12px',
                borderRadius: 16,
                background: 'linear-gradient(135deg, #2E6FBF, #14B8A6)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#fff',
                fontSize: 26,
                boxShadow: '0 6px 20px rgba(46,111,191,0.35)',
              }}
            >
              <MessageOutlined />
            </div>
            <Title level={3} style={{ margin: 0, fontFamily: "'Noto Serif SC', serif", color: '#16365C' }}>
              大学校园多智能体平台
            </Title>
            <Text type="secondary" style={{ fontSize: 13 }}>
              学生 / 老师 · 智能体服务统一入口
            </Text>
          </div>

          <Segmented
            block
            value={mode}
            onChange={(v) => setMode(v as 'login' | 'register')}
            options={[
              { label: '登录', value: 'login' },
              { label: '注册', value: 'register' },
            ]}
            style={{ marginBottom: 20 }}
          />

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <Input
              prefix={<UserOutlined style={{ color: '#6B7A8D' }} />}
              placeholder="学号 / 工号（如 3123003252）"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              size="large"
            />
            {mode === 'register' && (
              <>
                <Input
                  prefix={<UserOutlined style={{ color: '#6B7A8D' }} />}
                  placeholder="姓名"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  size="large"
                />
                <Segmented
                  block
                  value={role}
                  onChange={(v) => setRole(v as string)}
                  options={[
                    { label: '学生', value: 'student' },
                    { label: '老师', value: 'teacher' },
                  ]}
                />
              </>
            )}
            <Input.Password
              prefix={<LockOutlined style={{ color: '#6B7A8D' }} />}
              placeholder={mode === 'register' ? '密码（至少 6 位）' : '密码'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onPressEnter={handleSubmit}
              size="large"
            />
            <Button type="primary" size="large" loading={submitting} onClick={handleSubmit} style={{ marginTop: 4 }}>
              {mode === 'register' ? '注册' : '登录'}
            </Button>
          </div>
        </Card>
      </div>
      </App>
    </ConfigProvider>
  )
}
