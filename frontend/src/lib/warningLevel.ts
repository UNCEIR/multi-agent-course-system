// 选课提醒 / 选课可行性警告等级映射：抽取到独立模块以便 StreamView 与
// SingleResultView / CompareView 共享同一套配色 + 文案。
// level 取值约定：`'high' | 'medium' | 'low'`（来自后端 SelectionWarning.level）

export interface WarningLevelStyle {
  color: string
  bg: string
  label: string
}

export const WARNING_LEVEL_STYLES: Record<string, WarningLevelStyle> = {
  high: { color: '#C0392B', bg: '#FDECEC', label: '高' },
  medium: { color: '#B9772E', bg: '#fef3c7', label: '中' },
  low: { color: '#6B7A8D', bg: '#EAF2FB', label: '低' },
}

export const DEFAULT_WARNING_LEVEL: WarningLevelStyle = {
  color: '#6B7A8D',
  bg: '#EAF2FB',
  label: '低',
}

/**
 * 解析选课提醒等级：未知值回退到 DEFAULT_WARNING_LEVEL（low），
 * 这样即使后端引入新等级，UI 不会因为 `undefined` 报错而崩。
 */
export function getWarningLevel(level: unknown): WarningLevelStyle {
  if (typeof level !== 'string') return DEFAULT_WARNING_LEVEL
  return WARNING_LEVEL_STYLES[level] ?? DEFAULT_WARNING_LEVEL
}
