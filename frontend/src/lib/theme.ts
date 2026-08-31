// Phase 3.5 视觉主题（创新实验室 · 学院蓝）：antd ConfigProvider token
export const antdThemeConfig = {
  token: {
    colorPrimary: '#2E6FBF',
    colorInfo: '#4A90D9',
    colorSuccess: '#1FA88D',
    colorWarning: '#E8A23D',
    colorError: '#D64545',
    colorBgLayout: '#EAF3FC',
    colorTextBase: '#16365C',
    colorBorder: '#CFE3F5',
    borderRadius: 10,
    fontSize: 14,
  },
  components: {
    Layout: {
      headerBg: 'rgba(255,255,255,0.85)',
      bodyBg: 'transparent',
    },
    Card: {
      colorBgContainer: 'rgba(255,255,255,0.88)',
    },
    Menu: {
      itemSelectedBg: '#EAF2FB',
      itemSelectedColor: '#2E6FBF',
    },
  },
}
