'use client'

import EChart from '@/components/analyst/EChart'
import r from '@/content/blog/data/driver-skill.json'

const TEXT = '#8a8a8a'
const GRID = 'rgba(138,138,138,0.25)'
const RED = '#e8002d'
const ASTON = '#00665e'
const AMBER = '#e0a100'
const MUTED = 'rgba(138,138,138,0.45)'

const axis = { axisLine: { lineStyle: { color: GRID } }, axisLabel: { color: TEXT }, splitLine: { lineStyle: { color: GRID, type: 'dashed' } } }
const base = { textStyle: { color: TEXT, fontFamily: 'inherit' } }

const T = r.meta.pct_to_tenths // 1% of a 90 s lap = 9 tenths of a second
const one = (v: number) => (Math.round(v * 10) / 10).toFixed(1)

type Point = { year: number; pct: number; sd: number }
const traj = r.trajectories as Record<string, Point[]>

/** Skill over time: tenths of a second per lap faster than the average driver of that season. Band = ±1 sd. */
function SkillTrajectory() {
  const years = Array.from({ length: 21 }, (_, i) => 2006 + i)
  const line = (id: string) => years.map(y => {
    const p = traj[id]?.find(t => t.year === y)
    return p ? -p.pct * T : null
  })
  const alo = traj.alonso
  const lo = years.map(y => { const p = alo.find(t => t.year === y); return p ? -p.pct * T - p.sd * T : null })
  const band = years.map(y => { const p = alo.find(t => t.year === y); return p ? 2 * p.sd * T : null })
  const peers: [string, string, string][] = [['max_verstappen', 'Verstappen', '#4f7ed6'], ['hamilton', 'Hamilton', '#7a7a7a'], ['vettel', 'Vettel', '#b07acb']]
  return (
    <EChart
      height={400}
      option={{
        ...base,
        grid: { left: 56, right: 16, top: 24, bottom: 64 },
        legend: { bottom: 0, textStyle: { color: TEXT }, data: ['Alonso', ...peers.map(p => p[1])] },
        tooltip: { trigger: 'axis', valueFormatter: (v: number | null) => (v == null ? '-' : `${one(v)} tenths`) },
        xAxis: { type: 'category', data: years, ...axis, splitLine: { show: false } },
        yAxis: { type: 'value', name: 'Tenths faster than average driver', nameTextStyle: { color: TEXT }, ...axis },
        series: [
          { name: 'band-lo', type: 'line', data: lo, stack: 'band', lineStyle: { opacity: 0 }, symbol: 'none', silent: true, tooltip: { show: false } },
          { name: 'band', type: 'line', data: band, stack: 'band', lineStyle: { opacity: 0 }, areaStyle: { color: 'rgba(232,0,45,0.16)' }, symbol: 'none', silent: true, tooltip: { show: false } },
          ...peers.map(([id, name, color]) => ({ name, type: 'line', data: line(id), symbol: 'none', lineStyle: { width: 1.5, color, opacity: 0.8 }, itemStyle: { color }, connectNulls: false })),
          { name: 'Alonso', type: 'line', data: line('alonso'), symbol: 'circle', symbolSize: 6, lineStyle: { width: 3, color: RED }, itemStyle: { color: RED }, connectNulls: false, z: 5 },
        ],
      }}
    />
  )
}

/** Career-average skill with its standard error. */
function SkillRanking() {
  const rows = [...r.ranking.slice(0, 12)].reverse()
  return (
    <EChart
      height={420}
      option={{
        ...base,
        grid: { left: 132, right: 96, top: 8, bottom: 28 },
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'none' },
          formatter: (ps: { dataIndex: number }[]) => {
            const d = rows[ps[0].dataIndex]
            return `${d.driver}<br/>${one(-d.career_pct * T)} ± ${one(d.se_pct * T)} tenths faster<br/>Peak: ${one(-d.peak_pct * T)} (${d.peak_year})<br/>${d.seasons} seasons`
          },
        },
        xAxis: { type: 'value', name: 'Tenths faster than the average driver, career mean', nameLocation: 'middle', nameGap: 26, nameTextStyle: { color: TEXT }, ...axis },
        yAxis: { type: 'category', data: rows.map(d => d.driver), ...axis, splitLine: { show: false } },
        series: [{
          type: 'bar',
          barWidth: '62%',
          data: rows.map(d => ({ value: -d.career_pct * T, itemStyle: { color: d.driver_id === 'alonso' ? RED : MUTED } })),
          label: { show: true, position: 'right', color: TEXT, formatter: ({ dataIndex }: { dataIndex: number }) => `${one(-rows[dataIndex].career_pct * T)} ± ${one(rows[dataIndex].se_pct * T)}` },
        }],
      }}
    />
  )
}

/** Held-out error of every model under both temporal protocols (lower is better). */
function ModelComparison() {
  const inSeason = r.in_season
  const ahead = r.season_ahead
  const order = inSeason.map(m => m.model)
  const get = (rows: { model: string; rmse: number }[], m: string) => rows.find(x => x.model === m)?.rmse ?? null
  const rev = [...order].reverse()
  return (
    <EChart
      height={440}
      option={{
        ...base,
        grid: { left: 190, right: 56, top: 8, bottom: 72 },
        legend: { bottom: 0, textStyle: { color: TEXT }, itemGap: 28, itemWidth: 18, itemHeight: 10, data: ['Mid-season forecast', 'Next-season forecast'] },
        tooltip: { trigger: 'axis', axisPointer: { type: 'none' }, valueFormatter: (v: number | null) => (v == null ? 'n/a' : `${v.toFixed(3)}% of lap`) },
        xAxis: { type: 'value', min: 0.6, name: 'Held-out RMSE, % of lap (lower is better)', nameLocation: 'middle', nameGap: 26, nameTextStyle: { color: TEXT }, ...axis },
        yAxis: { type: 'category', data: rev, ...axis, splitLine: { show: false } },
        series: [
          { name: 'Mid-season forecast', type: 'bar', barGap: '20%', barCategoryGap: '38%', itemStyle: { color: RED }, data: rev.map(m => get(inSeason, m)), label: { show: true, position: 'right', color: TEXT, formatter: ({ value }: { value: number | null }) => (value == null ? '' : value.toFixed(3)) } },
          { name: 'Next-season forecast', type: 'bar', barGap: '20%', barCategoryGap: '38%', itemStyle: { color: MUTED }, data: rev.map(m => get(ahead, m)), label: { show: true, position: 'right', color: TEXT, formatter: ({ value }: { value: number | null }) => (value == null ? '' : value.toFixed(3)) } },
        ],
      }}
    />
  )
}

/** Data drift per season (PSI vs the previous three seasons) and how spread out the field is. */
function Drift() {
  const d = r.drift
  return (
    <EChart
      height={380}
      option={{
        ...base,
        grid: { left: 52, right: 52, top: 28, bottom: 64 },
        legend: { bottom: 0, textStyle: { color: TEXT }, data: ['PSI (regulation year)', 'PSI', 'Field spread (sd of gap)'] },
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: d.map(x => x.year), ...axis, splitLine: { show: false } },
        yAxis: [
          { type: 'value', name: 'PSI', nameTextStyle: { color: TEXT }, ...axis },
          { type: 'value', name: 'Spread, % of lap', nameTextStyle: { color: TEXT }, ...axis, splitLine: { show: false } },
        ],
        series: [
          {
            name: 'PSI', type: 'bar', barWidth: '55%', itemStyle: { color: MUTED },
            data: d.map(x => (x.reg_change ? null : x.psi)),
            markLine: { silent: true, symbol: 'none', lineStyle: { color: AMBER, type: 'dashed' }, label: { color: TEXT, formatter: 'PSI 0.25: large shift' }, data: [{ yAxis: 0.25 }] },
          },
          { name: 'PSI (regulation year)', type: 'bar', barWidth: '55%', itemStyle: { color: AMBER }, data: d.map(x => (x.reg_change ? x.psi : null)) },
          { name: 'Field spread (sd of gap)', type: 'line', yAxisIndex: 1, symbol: 'circle', symbolSize: 5, lineStyle: { color: RED, width: 2 }, itemStyle: { color: RED }, data: d.map(x => x.field_sd) },
        ],
      }}
    />
  )
}

/** Brazil Q1: how far each driver landed from what the model expected, in seconds. Model never saw the session. */
function BrazilExpected() {
  const q1 = 90.939 // fastest Q1 lap, s
  const rows = [...r.brazil_2026_holdout].reverse()
  const col = (d: string) => (d === 'alonso' ? RED : d === 'stroll' ? ASTON : MUTED)
  return (
    <EChart
      height={520}
      option={{
        ...base,
        grid: { left: 112, right: 40, top: 8, bottom: 44 },
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'none' },
          formatter: (ps: { dataIndex: number }[]) => {
            const d = rows[ps[0].dataIndex]
            return `${d.driver}<br/>Expected gap ${d.pred_gap.toFixed(2)}%, actual ${d.actual_gap.toFixed(2)}%<br/>z = ${d.z.toFixed(2)}`
          },
        },
        xAxis: { type: 'value', name: 'Seconds vs expectation (negative = faster than the model expected)', nameLocation: 'middle', nameGap: 28, nameTextStyle: { color: TEXT }, ...axis },
        yAxis: { type: 'category', data: rows.map(d => d.driver), ...axis, splitLine: { show: false }, axisLabel: { color: TEXT, fontSize: 11 } },
        series: [{
          type: 'bar', barWidth: '64%',
          data: rows.map(d => ({ value: (d.resid / 100) * q1, itemStyle: { color: col(d.driver) } })),
          label: { show: true, position: 'right', color: TEXT, fontSize: 11, formatter: ({ value }: { value: number }) => `${value > 0 ? '+' : ''}${value.toFixed(2)}s` },
        }],
      }}
    />
  )
}

export const MODEL_CHARTS: Record<string, { node: () => React.ReactElement; caption: string }> = {
  'skill-trajectory': { node: SkillTrajectory, caption: 'Estimated driver skill by season, in tenths of a second per lap faster than the average driver that year (90 s lap). Red band: Alonso ±1 standard deviation.' },
  'skill-ranking': { node: SkillRanking, caption: 'Career-average skill with its standard error, drivers with 8+ seasons since 2006. Hover for peak season.' },
  'model-comparison': { node: ModelComparison, caption: 'Held-out error (RMSE) on 2018–2026. Mid-season: train through half a season, predict the rest. Next-season: train through last year, predict the whole year.' },
  drift: { node: Drift, caption: 'Population Stability Index of the Q1 gap distribution against the previous three seasons, and how spread out the field is. Orange bars are regulation-change years.' },
  'brazil-expected': { node: BrazilExpected, caption: 'Brazil 2026 Q1: actual lap against what the model expected, fitted without that session. Alonso red, Stroll green.' },
}
