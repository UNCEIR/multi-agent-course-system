'use client'

import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

export interface RadarDimension {
  name: string
  metric: string
  value: number
  weight?: number
}

interface Props {
  dimensions: RadarDimension[]
  theme?: string
  height?: number
}

export default function RadarChart({ dimensions, theme = '综合学业表现', height = 320 }: Props) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current)
    chart.setOption({
      title: { text: theme, left: 'center', textStyle: { fontSize: 14, color: '#16365C' } },
      tooltip: {},
      radar: {
        indicator: dimensions.map((d) => ({ name: d.name, max: 100 })),
        radius: '65%',
        splitArea: { areaStyle: { color: ['#EAF3FC', '#EAF2FB'] } },
      },
      series: [
        {
          type: 'radar',
          data: [{ value: dimensions.map((d) => d.value), name: theme }],
          areaStyle: { opacity: 0.25 },
          lineStyle: { color: '#2E6FBF', width: 2 },
          itemStyle: { color: '#14B8A6' },
        },
      ],
    })
    const onResize = () => chart.resize()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      chart.dispose()
    }
  }, [dimensions, theme])

  return <div ref={ref} style={{ width: '100%', height }} aria-label={`雷达图：${theme}`} />
}
