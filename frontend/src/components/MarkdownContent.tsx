'use client'

import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'

/**
 * Chat 消息 Markdown 渲染（assistant 回复）。
 *
 * 2026-09-03：chat 页此前纯文本渲染，图片生成回复里的 ![alt](/api/v1/images/download?...)
 * 全部按字面显示。这里用 react-markdown 渲染，并把图片输出为可直接显示的 <img>
 * （后端 /api/v1/images/download 返回 image/* + inline，无 token/过期）。
 * raw HTML 默认不渲染（XSS 安全）。
 * 纯展示层、与业务域/主题无关：任何 Markdown 图片（内部直链/外部 CDN/legacy）
 * 都会渲染为 <img>，src/alt 原样透传，不做主题判断。
 */
const components: Components = {
  img: (props) => (
    // 同源内部图片直链，无需 next/image 优化
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={props.src}
      alt={props.alt ?? ''}
      style={{
        maxWidth: '100%',
        maxHeight: 360,
        borderRadius: 10,
        display: 'block',
        margin: '10px 0',
        boxShadow: '0 2px 8px rgba(51, 71, 92, 0.12)',
      }}
    />
  ),
  a: (props) => (
    <a href={props.href} target="_blank" rel="noopener noreferrer">
      {props.children}
    </a>
  ),
}

export default function MarkdownContent({ content }: { content: string }) {
  return (
    <div style={{ wordBreak: 'break-word' }}>
      <ReactMarkdown components={components}>{content}</ReactMarkdown>
    </div>
  )
}
