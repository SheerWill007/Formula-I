'use client'

import { useState } from 'react'
import {
  Bar, CartesianGrid, ComposedChart, Legend, Line, PolarAngleAxis, PolarGrid, PolarRadiusAxis,
  Radar, RadarChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import type { DriverProfile } from '@/types/f1'
import type { SampleFlags } from '@/lib/driver-sample'
import { buildHeatRows, cellIntensity, cellLabel, radarData, type HeatMetric } from '@/lib/driver-insights'

const METRICS: { key: HeatMetric; label: string }[] = [
  { key: 'finish', label: 'Finish' },
  { key: 'gained', label: 'Places gained' },
  { key: 'points', label: 'Points' },
]

function Heatmap({ grid }: { grid: DriverProfile['results_grid'] }) {
  const [metric, setMetric] = useState<HeatMetric>('finish')
  const [active, setActive] = useState<string>('')
  const { rows, rounds } = buildHeatRows(grid)
  if (!rows.length) return <p className="dp-empty">No race results yet.</p>
  return (
    <div>
      <div className="dp-seg" role="group" aria-label="Heatmap metric">
        {METRICS.map(m => (
          <button key={m.key} type="button" aria-pressed={metric === m.key}
            className={metric === m.key ? 'on' : ''} onClick={() => setMetric(m.key)}>{m.label}</button>
        ))}
      </div>
      <p className="dp-detail" aria-live="polite">{active || 'Hover, tap or focus a square for race details.'}</p>
      <div className="dp-heat" style={{ ['--cols' as string]: rounds }}>
        {rows.map(row => (
          <div className="dp-heat-row" key={row.year}>
            <span className="dp-heat-year">{row.year}</span>
            <div className="dp-heat-cells">
              {row.cells.map((c, i) => {
                if (!c) return <i key={i} className="dp-cell empty" aria-hidden />
                const v = cellIntensity(metric, c)
                const label = cellLabel(metric, c)
                return (
                  <button key={i} type="button" aria-label={label}
                    className={`dp-cell${v == null ? ' dnf' : ''}`}
                    style={v != null ? { ['--i' as string]: v } : undefined}
                    onMouseEnter={() => setActive(label)} onFocus={() => setActive(label)} onClick={() => setActive(label)} />
                )
              })}
            </div>
          </div>
        ))}
      </div>
      <p className="dp-legend"><span>Weaker</span><i className="dp-scale" /><span>Stronger</span><span className="dp-dnf-key"><i className="dp-cell dnf" /> DNF</span></p>
    </div>
  )
}

function StrengthChips({ data }: { data: { axis: string; current: number }[] }) {
  const sorted = [...data].sort((a, b) => b.current - a.current)
  const low = sorted[sorted.length - 1]
  return (
    <div className="dp-chips">
      {sorted.slice(0, 2).map(t => <span key={t.axis} className="dp-chip">Strong: {t.axis} ({t.current})</span>)}
      <span className="dp-chip weak">Room to grow: {low.axis} ({low.current})</span>
    </div>
  )
}

function StyleRadar({ history }: { history: DriverProfile['style_history'] }) {
  const seasons = history.map(h => h.season)
  const latest = seasons[seasons.length - 1]
  const [season, setSeason] = useState<number | undefined>(latest)
  const [compare, setCompare] = useState<number | null>(seasons.length > 1 ? seasons[seasons.length - 2] : null)
  if (!seasons.length || season == null) return <p className="dp-empty">Style features are not available for this driver yet.</p>
  const data = radarData(history, season, compare)
  const summary = data.map(d => `${d.axis} ${d.current}`).join(', ')
  return (
    <div>
      <div className="dp-selects">
        <label>Season
          <select value={season} onChange={e => setSeason(Number(e.target.value))}>
            {seasons.map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </label>
        <label>Compare with
          <select value={compare ?? ''} onChange={e => setCompare(e.target.value ? Number(e.target.value) : null)}>
            <option value="">None</option>
            {seasons.filter(y => y !== season).map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </label>
      </div>
      <div role="img" aria-label={`Driving style radar for ${season}, percentile by axis: ${summary}`} style={{ width: '100%', height: 340 }}>
        <ResponsiveContainer>
          <RadarChart data={data} outerRadius="72%">
            <PolarGrid stroke="var(--border-2)" />
            <PolarAngleAxis dataKey="axis" tick={{ fontSize: 13, fill: "var(--text-2)" }} />
            <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
            {compare != null && (
              <Radar name={String(compare)} dataKey="compare" stroke="#8a8f98" fill="#8a8f98" fillOpacity={0.12} strokeDasharray="4 3" />
            )}
            <Radar name={String(season)} dataKey="current" stroke="var(--dp-team-strong)" fill="var(--dp-team)" fillOpacity={0.3} />
            <Tooltip formatter={v => `${v}th percentile`} />
            <Legend />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <StrengthChips data={data} />
      <p className="dp-note">Each axis is a percentile against every driver that season. Outward is better, so reliability rewards fewer DNFs.</p>
    </div>
  )
}

function Trajectory({ seasons }: { seasons: DriverProfile['seasons'] }) {
  if (!seasons.length) return <p className="dp-empty">No season history yet.</p>
  return (
    <div>
      <div style={{ width: '100%', height: 320 }}>
        <ResponsiveContainer>
          <ComposedChart data={seasons} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis dataKey="year" tick={{ fontSize: 13, fill: "var(--text-3)" }} />
            <YAxis yAxisId="pts" tick={{ fontSize: 13, fill: "var(--text-3)" }} width={40} />
            <YAxis yAxisId="pos" orientation="right" reversed domain={[1, 20]} tick={{ fontSize: 13, fill: "var(--text-3)" }} width={36} />
            <Tooltip
              formatter={(v, name) => [name === 'Avg finish' ? Number(v).toFixed(1) : v, name]}
              labelFormatter={(y, p) => `${y}${p?.[0]?.payload?.team ? ` · ${p[0].payload.team}` : ''}`} />
            <Legend />
            <Bar yAxisId="pts" dataKey="points" name="Points" fill="var(--dp-team)" fillOpacity={0.45} radius={[4, 4, 0, 0]} maxBarSize={56} />
            <Line yAxisId="pos" dataKey="avg_finish" name="Avg finish" stroke="var(--text)" strokeWidth={2} dot={{ r: 3 }} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="dp-note">Bars show points per season; the line shows average finishing position (higher on the chart is better).</p>
    </div>
  )
}

const Tag = ({ on }: { on: boolean }) => (on ? <span className="dp-sample inline">Sample data</span> : null)

export default function DriverInsights({ profile, sampled }: { profile: DriverProfile; sampled: SampleFlags }) {
  return (
    <div className="dp-insights">
      <section id="heatmap" className="dp-sec" aria-labelledby="dp-heat-h">
        <h2 id="dp-heat-h">Season heatmap <Tag on={sampled.races} /></h2>
        <p className="dp-sub">Every race, one square each.</p>
        <Heatmap grid={profile.results_grid} />
      </section>
      <section id="style" className="dp-sec" aria-labelledby="dp-radar-h">
        <h2 id="dp-radar-h">Driving style <Tag on={sampled.style} /></h2>
        <p className="dp-sub">How the driver compares with the grid.</p>
        <StyleRadar history={profile.style_history} />
      </section>
      <section id="trajectory" className="dp-sec" aria-labelledby="dp-traj-h">
        <h2 id="dp-traj-h">Career trajectory <Tag on={sampled.seasons} /></h2>
        <p className="dp-sub">Points and average finish by season.</p>
        <Trajectory seasons={profile.seasons} />
      </section>
    </div>
  )
}
