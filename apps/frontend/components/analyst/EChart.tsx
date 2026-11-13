'use client'

import dynamic from 'next/dynamic'
import { Component, type ReactNode } from 'react'

const ReactECharts = dynamic(() => import('echarts-for-react'), { ssr: false })

class Boundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

const hide = (axis: unknown) =>
  Array.isArray(axis) ? axis.map((a) => ({ ...a, show: false })) : { ...(axis as object), show: false, name: undefined }

/** A chart stripped to its shape, for card thumbnails. */
export function miniOption(option: Record<string, unknown>): Record<string, unknown> {
  return {
    ...option,
    animation: false,
    legend: { show: false },
    tooltip: { show: false },
    title: { show: false },
    grid: { left: 6, right: 6, top: 6, bottom: 6 },
    xAxis: hide(option.xAxis),
    yAxis: hide(option.yAxis),
  }
}

export default function EChart({
  option,
  height = 280,
  mini = false,
}: {
  option: Record<string, unknown>
  height?: number
  mini?: boolean
}) {
  return (
    <Boundary fallback={<div className="an-chart-fail">This chart could not be drawn.</div>}>
      <ReactECharts
        option={mini ? miniOption(option) : { animation: false, ...option }}
        style={{ height, width: '100%' }}
        opts={{ renderer: 'svg' }}
        notMerge
      />
    </Boundary>
  )
}
