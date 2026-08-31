import { Typography } from 'antd'

const { Text } = Typography

interface StatCardProps {
  icon: React.ReactNode
  title: string
  value: string
  color: string
}

export default function StatCard({ icon, title, value, color }: StatCardProps) {
  return (
    <div
      style={{
        background: '#fff',
        borderRadius: 10,
        padding: '16px 18px',
        border: '1px solid #CFE3F5',
        cursor: 'default',
        transition: 'box-shadow 200ms cubic-bezier(0.16, 1, 0.3, 1)',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.boxShadow =
          '0 4px 16px rgba(26,26,46,0.06), 0 2px 4px rgba(26,26,46,0.03)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.boxShadow = 'none'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <span style={{ color, fontSize: 13 }} aria-hidden="true">
          {icon}
        </span>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {title}
        </Text>
      </div>
      <Text
        strong
        style={{
          fontSize: 20,
          color,
          fontFamily: "'Noto Serif SC', serif",
        }}
        role="status"
        aria-label={`${title}：${value}`}
      >
        {value}
      </Text>
    </div>
  )
}
