'use client'

/**
 * 全局 Error Boundary（路 3）。
 *
 * Next.js App Router 的 error.tsx 约定：路由组件抛错时被路由级 error.tsx 捕获。
 * 这里捕获 (main) 路由组的渲染期 / 数据获取期未捕获错误，给用户可读的兜底 UI + 重试入口。
 *
 * 边界外（layout.tsx、模板）的错误仍会冒到 root error.tsx（项目里没有，留给 Next.js 默认 500 页面）。
 */

import { useEffect } from 'react'
import Link from 'next/link'
import { Button, Result } from 'antd'

interface ErrorProps {
  error: Error & { digest?: string }
  reset: () => void
}

export default function MainError({ error, reset }: ErrorProps) {
  useEffect(() => {
    // 仅在客户端 console 报告（服务端会有自己的 logging middleware）
    console.error('[main route error]', error)
  }, [error])

  return (
    <Result
      status="error"
      title="页面出错了"
      subTitle={
        error.digest
          ? `错误编号：${error.digest}`
          : '本次请求发生未预期错误。可以重试或回到首页。'
      }
      extra={[
        <Button type="primary" key="retry" onClick={reset}>
          重试
        </Button>,
        <Link href="/" key="home">
          <Button>回到首页</Button>
        </Link>,
      ]}
    />
  )
}
