import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <ConfigProvider
    locale={zhCN}
    theme={{
      token: {
        colorPrimary: '#1e3a5f',
        colorSuccess: '#2d6a4f',
        colorWarning: '#b8860b',
        colorError: '#a52a2a',
        colorInfo: '#1e3a5f',
        colorBgBase: '#faf8f5',
        colorBgContainer: '#ffffff',
        colorBgElevated: '#ffffff',
        colorTextBase: '#1a1a2e',
        colorTextSecondary: '#5c5c6e',
        colorTextTertiary: '#8a8980',
        colorBorder: '#e8e0d5',
        colorBorderSecondary: '#f0ece5',
        borderRadius: 6,
        borderRadiusLG: 10,
        fontFamily: "'Noto Sans SC', system-ui, -apple-system, sans-serif",
        fontSize: 14,
        fontSizeHeading1: 28,
        fontSizeHeading2: 22,
        fontSizeHeading3: 18,
        fontSizeHeading4: 16,
        fontSizeHeading5: 14,
        lineHeight: 1.6,
        controlHeight: 38,
        paddingContentHorizontal: 20,
        paddingContentVertical: 16,
        boxShadow: '0 1px 3px rgba(26, 26, 46, 0.06), 0 1px 2px rgba(26, 26, 46, 0.04)',
        boxShadowSecondary: '0 4px 12px rgba(26, 26, 46, 0.06), 0 2px 4px rgba(26, 26, 46, 0.03)',
      },
      components: {
        Card: {
          paddingLG: 20,
          boxShadow: '0 1px 3px rgba(26, 26, 46, 0.04), 0 1px 2px rgba(26, 26, 46, 0.02)',
        },
        Button: {
          primaryShadow: '0 2px 6px rgba(30, 58, 95, 0.2)',
          fontWeight: 500,
        },
        Tag: {
          fontSizeSM: 11,
        },
        Table: {
          headerBg: '#faf8f5',
          headerColor: '#1a1a2e',
          rowHoverBg: '#f5f1ea',
          borderColor: '#e8e0d5',
        },
        Menu: {
          horizontalItemHoverColor: '#1e3a5f',
          horizontalItemSelectedColor: '#1e3a5f',
          itemHoverBg: 'transparent',
          itemSelectedBg: 'transparent',
        },
        Collapse: {
          headerBg: '#faf8f5',
          contentBg: '#ffffff',
        },
        Tabs: {
          inkBarColor: '#c88c3e',
          itemActiveColor: '#1e3a5f',
          itemHoverColor: '#c88c3e',
          itemSelectedColor: '#1e3a5f',
        },
      },
    }}
  >
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </ConfigProvider>
)
