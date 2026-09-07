import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'

import MarkdownContent from '../../src/components/MarkdownContent'

/**
 * MarkdownContent 是 chat 消息渲染器，核心职责是「任何图片生成回复里的
 * ![alt](url) 都能渲染成 <img>」。这里用通用范式覆盖：
 * - 任意主题（不绑定某一次提问/某张图）；
 * - 多种 URL 形态：内部持久化直链 /api/v1/images/download、外部 24h 签名 CDN、
 *   旧 report-download legacy 链接；
 * - 真实完整回复：标题句 + 「1./2./3.」编号图片列表 + 描述段；
 * - 安全与纯文本：不渲染 raw HTML、无图时正文完整、加粗/链接/换行正常。
 */

function imgOf(container: HTMLElement, index = 0): HTMLImageElement | null {
  return (container.querySelectorAll('img')[index] ?? null) as HTMLImageElement | null
}

const internalUrl = (key: string) => `/api/v1/images/download?file_key=images/${key}`

describe('MarkdownContent (通用图片渲染)', () => {
  // 渲染层与业务域/主题无关：组件不按主题分支，主题只是 alt 文本。
  // 因此这里验证的是「src 原样透传 + alt 任意字符串原样透传」，而非枚举主题。
  describe('渲染与主题/业务域无关（不变量：src/alt 原样透传）', () => {
    it('非校园域主题（完全通用的图片内容）同样渲染', () => {
      const alt = 'a corgi sitting on a sunset valley hillside, 4K photography'
      const url = internalUrl('any-uuid.png')
      const { container } = render(<MarkdownContent content={`![${alt}](${url})`} />)
      const img = imgOf(container)
      expect(img).not.toBeNull()
      expect(img?.getAttribute('src')).toBe(url)
      expect(img?.getAttribute('alt')).toBe(alt)
    })

    it.each([
      '生成图1',
      '手机实拍图',
      'red-rose-closeup',
      '😀 emoji 主题图',
      'A/B & C (special)',
      '图片-1_2.x',
    ])('alt「%s」原样透传，不丢失不转义', (alt) => {
      const url = internalUrl('alt-passthrough.png')
      const { container } = render(<MarkdownContent content={`![${alt}](${url})`} />)
      const img = imgOf(container)
      expect(img).not.toBeNull()
      expect(img?.getAttribute('src')).toBe(url)
      expect(img?.getAttribute('alt')).toBe(alt)
    })
  })

  describe('多种图片 URL 形态', () => {
    it('内部持久化直链（/api/v1/images/download）', () => {
      const url = '/api/v1/images/download?file_key=images/c27e93804e49.png'
      const { container } = render(<MarkdownContent content={`![生成图](${url})`} />)
      expect(imgOf(container)?.getAttribute('src')).toBe(url)
    })

    it('外部 24h 签名 CDN（byteimg，带 query 参数）', () => {
      const url =
        'https://p9-aiop-sign.byteimg.com/tos-cn-i-vuqhorh59i/20260903185201409D80A5DE9E19C1F84D-0~tplv-vuqhorh59i-image-v1.image?rk3s=7f9e702d&x-expires=1788519123&x-signature=WNpWJYu2etYlAFf3Kk8lriG6tVM%3D'
      const { container } = render(<MarkdownContent content={`![cdnc](${url})`} />)
      expect(imgOf(container)?.getAttribute('src')).toBe(url)
    })

    it('旧 report-download legacy 链接', () => {
      const url = '/api/v1/report/download?file_key=images/legacy.png&token=__IMG__'
      const { container } = render(<MarkdownContent content={`![旧图](${url})`} />)
      expect(imgOf(container)?.getAttribute('src')).toBe(url)
    })

    it('缺 alt 时渲染为空字符串，不报错', () => {
      const { container } = render(
        <MarkdownContent content={`![](/api/v1/images/download?file_key=images/no-alt.png)`} />,
      )
      expect(imgOf(container)?.getAttribute('alt')).toBe('')
    })
  })

  describe('真实图片生成完整回复', () => {
    it('标题 + 1./2./3. 编号图片列表 + 描述段 → 3 张 <img> 且前后正文保留', () => {
      const content = [
        '图片已生成完成！✨ 共生成 3 张：',
        '',
        '1. ![生成图1](/api/v1/images/download?file_key=images/a.png)',
        '2. ![生成图2](/api/v1/images/download?file_key=images/b.png)',
        '3. ![生成图3](/api/v1/images/download?file_key=images/c.png)',
        '',
        '画面细节说明……如果想调整风格，告诉我即可。',
      ].join('\n')
      const { container } = render(<MarkdownContent content={content} />)
      const imgs = container.querySelectorAll('img')
      expect(imgs).toHaveLength(3)
      expect(imgOf(container, 0)?.getAttribute('src')).toBe('/api/v1/images/download?file_key=images/a.png')
      expect(imgOf(container, 2)?.getAttribute('src')).toBe('/api/v1/images/download?file_key=images/c.png')
      expect(container.textContent).toContain('图片已生成完成')
      expect(container.textContent).toContain('画面细节说明')
    })

    it('图文混排（文字-图-文字）保持顺序', () => {
      const content = [
        '第一张是主图：',
        '',
        `![主图](${internalUrl('main.png')})`,
        '',
        '第二张是细节：',
        '',
        `![细节](${internalUrl('detail.png')})`,
      ].join('\n')
      const { container } = render(<MarkdownContent content={content} />)
      const text = container.textContent ?? ''
      const firstImgIdx = text.indexOf('主图')
      const secondImgIdx = text.indexOf('细节')
      expect(container.querySelectorAll('img')).toHaveLength(2)
      expect(firstImgIdx).toBeGreaterThan(-1)
      expect(secondImgIdx).toBeGreaterThan(firstImgIdx)
    })
  })

  describe('纯文本与安全', () => {
    it('无图片的纯文本段落完整保留（含空行分段）', () => {
      const { container } = render(<MarkdownContent content={'第一段\n\n第二段'} />)
      expect(container.textContent).toContain('第一段')
      expect(container.textContent).toContain('第二段')
      expect(container.querySelectorAll('img')).toHaveLength(0)
    })

    it('不渲染 raw HTML（XSS 安全）', () => {
      const { container } = render(<MarkdownContent content={'<script>alert(1)</script><b>hi</b>'} />)
      expect(container.querySelector('script')).toBeNull()
      expect(container.querySelector('b')).toBeNull()
    })

    it('加粗 / 链接（新窗口）/ 行内代码', () => {
      const { container } = render(
        <MarkdownContent content={'**加粗** [链接](https://example.com) `code`'} />,
      )
      expect(container.querySelector('strong')?.textContent).toBe('加粗')
      const link = container.querySelector('a')
      expect(link?.getAttribute('href')).toBe('https://example.com')
      expect(link?.getAttribute('target')).toBe('_blank')
      expect(container.querySelector('code')?.textContent).toBe('code')
    })
  })
})
