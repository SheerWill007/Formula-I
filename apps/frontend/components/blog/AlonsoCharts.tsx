'use client'

import { useMemo } from 'react'
import EChart from '@/components/analyst/EChart'
import data from '@/content/blog/data/alonso-slowest-car.json'
import { MODEL_CHARTS } from './ModelCharts'

// Mid-grey text and hairlines read on both the light and dark blog themes.
const TEXT = '#8a8a8a'
const GRID = 'rgba(138,138,138,0.25)'
const RED = '#e8002d' // Alonso
const ASTON = '#00665e' // Aston Martin
const WET = '#2f7fd6'
const INTER = '#e0a100'

const axis = { axisLine: { lineStyle: { color: GRID } }, axisLabel: { color: TEXT }, splitLine: { lineStyle: { color: GRID, type: 'dashed' } } }
const base = { textStyle: { color: TEXT, fontFamily: 'inherit' } }

const sec = (ms: number) => ms / 1000

/** Every team's qualifying gap to pole across the 16 earlier 2026 sessions. */
function TeamPace() {
  const rows = [...data.team_pace].reverse() // echarts draws the first category at the bottom
  return (
    <EChart
      height={380}
      option={{
        ...base,
        grid: { left: 110, right: 56, top: 8, bottom: 28 },
        tooltip: { trigger: 'axis', axisPointer: { type: 'none' }, valueFormatter: (v: number) => `${v.toFixed(2)}% off pole` },
        xAxis: { type: 'value', name: '% off pole, average best lap', nameLocation: 'middle', nameGap: 26, nameTextStyle: { color: TEXT }, ...axis },
        yAxis: { type: 'category', data: rows.map(r => r.team), ...axis, splitLine: { show: false } },
        series: [{
          type: 'bar',
          data: rows.map(r => ({ value: r.pct_off_pole, itemStyle: { color: r.team === 'Aston Martin' ? ASTON : 'rgba(138,138,138,0.45)' } })),
          label: { show: true, position: 'right', color: TEXT, formatter: ({ value }: { value: number }) => value.toFixed(2) },
          barWidth: '62%',
        }],
      }}
    />
  )
}

/** All Brazil quali laps by lap number, drying through Q1 to Q3, with Alonso and Stroll drawn over them. */
function BrazilQuali() {
  const { field, alo, str, bands } = useMemo(() => {
    const laps = data.brazil_laps
    const pt = (l: (typeof laps)[number]) => [l.lap, sec(l.lap_time_ms), l.driver]
    const bySeg = (s: number) => laps.filter(l => l.segment === s).map(l => l.lap)
    const bands = [1, 2, 3].map(s => {
      const ls = bySeg(s)
      return { s, from: Math.min(...ls) - 0.5, to: Math.max(...ls) + 0.5 }
    })
    return {
      field: {
        WET: laps.filter(l => l.compound === 'WET' && l.driver !== 'ALO' && l.driver !== 'STR').map(pt),
        INTERMEDIATE: laps.filter(l => l.compound === 'INTERMEDIATE' && l.driver !== 'ALO' && l.driver !== 'STR').map(pt),
      },
      // Only flying laps are joined up; in-laps and out-laps would spike the line to 110s.
      alo: laps.filter(l => l.driver === 'ALO' && l.lap_time_ms <= 100000).map(pt),
      str: laps.filter(l => l.driver === 'STR' && l.lap_time_ms <= 100000).map(pt),
      bands,
    }
  }, [])

  return (
    <EChart
      height={420}
      option={{
        ...base,
        grid: { left: 52, right: 16, top: 36, bottom: 84 },
        legend: { bottom: 0, textStyle: { color: TEXT }, itemGap: 18, data: ['Wet tyres', 'Intermediates', 'Alonso', 'Stroll'] },
        tooltip: { trigger: 'item', formatter: (p: { seriesName: string; value: (number | string)[] }) => `${p.value[2]} (${p.seriesName})<br/>Lap ${p.value[0]}: ${(p.value[1] as number).toFixed(3)}s` },
        xAxis: { type: 'value', name: 'Lap of the session', nameLocation: 'middle', nameGap: 28, nameTextStyle: { color: TEXT }, min: 1, ...axis },
        yAxis: { type: 'value', name: 'Lap time, s', min: 86, max: 112, nameTextStyle: { color: TEXT }, ...axis },
        series: [
          {
            name: 'Wet tyres', type: 'scatter', symbolSize: 8, itemStyle: { color: WET, opacity: 0.8, borderColor: '#fff', borderWidth: 0.5 }, data: field.WET,
            markArea: {
              silent: true,
              label: { color: TEXT, position: 'top', fontSize: 12 },
              itemStyle: { color: 'rgba(138,138,138,0.07)' },
              data: bands.map(b => [{ name: `Q${b.s}`, xAxis: b.from }, { xAxis: b.to }]),
            },
          },
          { name: 'Intermediates', type: 'scatter', symbolSize: 8, itemStyle: { color: INTER, opacity: 0.85, borderColor: '#fff', borderWidth: 0.5 }, data: field.INTERMEDIATE },
          { name: 'Alonso', type: 'line', symbol: 'circle', symbolSize: 9, lineStyle: { width: 3, color: RED }, itemStyle: { color: RED }, z: 5, data: alo },
          { name: 'Stroll', type: 'line', symbol: 'circle', symbolSize: 8, lineStyle: { width: 2, color: ASTON, type: 'dashed' }, itemStyle: { color: ASTON }, z: 4, data: str },
        ],
      }}
    />
  )
}

const CHARTS: Record<string, { node: () => React.ReactElement; caption: string }> = {
  'team-pace': { node: TeamPace, caption: 'Average gap to pole, 2026 qualifying (16 sessions before Brazil). Aston Martin is last of 11.' },
  'brazil-quali': { node: BrazilQuali, caption: 'Every Brazil qualifying lap under 1:55. Alonso and Stroll are joined up on flying laps only (under 1:40). The track dries from Q1 (wet tyres) to Q3 (all intermediates).' },
  ...MODEL_CHARTS,
}

export default function BlogChart({ id }: { id: string }) {
  const chart = CHARTS[id]
  if (!chart) return null
  const Node = chart.node
  return (
    <figure style={{ margin: '24px 0' }}>
      <Node />
      <figcaption style={{ fontSize: 13, lineHeight: '18px', color: TEXT, marginTop: 8 }}>{chart.caption}</figcaption>
    </figure>
  )
}
