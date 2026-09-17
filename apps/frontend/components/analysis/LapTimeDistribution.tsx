'use client'

import { useEffect, useState, useMemo } from 'react'
import Plot from 'react-plotly.js'
import { COMPOUND_COLOURS } from '@/lib/utils'

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

const C = {
  surface: '#FFFFFF',
  surfaceAlt: '#F5F7FB',
  border: '#D9E3EF',
  textDim: '#7D8BA2',
  textMid: '#56657C',
  textBright: '#13233D',
} as const

type LapEntry = {
  lap_number: number
  lap_time_ms: number
  compound: string
  position: number
  stint: number
  is_personal_best: boolean
  deleted: boolean
  s1_ms: number | null
  s2_ms: number | null
  s3_ms: number | null
}

type DriverLaps = {
  driver_number: number
  abbreviation: string
  team_colour: string
  team_name: string
  laps: LapEntry[]
}

type LapEvolutionResponse = {
  drivers: Record<string, DriverLaps>
}

function median(vals: number[]): number {
  const s = [...vals].sort((a, b) => a - b)
  const mid = Math.floor(s.length / 2)
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2
}

export default function LapTimeDistribution({
  sessionKey,
}: {
  sessionKey: number
}) {
  const [data, setData] = useState<LapEvolutionResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string[]>([])

  useEffect(() => {
    const abort = new AbortController()
    let active = true
    setLoading(true)
    setError(null)
    fetch(`${BASE}/api/v1/sessions/${sessionKey}/analysis/lap-evolution`, { signal: abort.signal })
      .then(r => { if (!r.ok) throw new Error('Failed to load')
        return r.json() as Promise<LapEvolutionResponse>
      })
      .then(d => {
        if (!active) return
        setData(d)
        const keys = Object.keys(d.drivers)
        if (selected.length === 0 && keys.length > 0) {
          setSelected(keys.slice(0, Math.min(4, keys.length)))
        }
      })
      .catch(err => { if (active && err?.name !== 'AbortError') setError(err instanceof Error ? err.message : 'Error') })
      .finally(() => { if (active) setLoading(false) })

    return () => { active = false; abort.abort() }
  }, [sessionKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const allDrivers = useMemo(() => {
    if (!data) return []
    return Object.entries(data.drivers).map(([dn, d]) => ({
      key: dn,
      number: d.driver_number,
      abbr: d.abbreviation,
      colour: d.team_colour,
    }))
  }, [data])

  const { traces, xPositions, xLabels } = useMemo(() => {
    const traces: Record<string, unknown>[] = []
    let xPositions: number[] = []
    let xLabels: string[] = []

    if (!data || selected.length === 0) return { traces, xPositions, xLabels }

    const n = selected.length
    const spacing = 1.2
    const positions = selected.map((_, i) => (i - (n - 1) / 2) * spacing)
    xPositions = positions
    xLabels = selected.map(dn => data.drivers[dn]?.abbreviation ?? dn)

    for (let di = 0; di < n; di++) {
      const dn = selected[di]
      const driver = data.drivers[dn]
      if (!driver) continue
      const laps = driver.laps.filter(l => !l.deleted && l.lap_time_ms != null)
      if (laps.length === 0) continue

      const teamColour = driver.team_colour?.startsWith('#') ? driver.team_colour : `#${driver.team_colour ?? '666'}`
      const times = laps.map(l => l.lap_time_ms / 1000)
      const hoverTexts = laps.map(l => {
        const totalSec = l.lap_time_ms / 1000
        const mins = Math.floor(totalSec / 60)
        const secs = (totalSec % 60).toFixed(3).padStart(6, '0')
        const compound = COMPOUND_COLOURS[l.compound] ? l.compound.charAt(0) + l.compound.slice(1).toLowerCase() : l.compound
        return `${driver.abbreviation} Lap ${l.lap_number} — ${mins}:${secs}<br>${compound} (Stint ${l.stint})<br>Pos ${l.position}`
      })

      traces.push({
        type: 'violin',
        y: times,
        x: Array(times.length).fill(positions[di]),
        name: driver.abbreviation,
        side: 'both',
        points: 'all',
        pointpos: 0,
        jitter: 0.3,
        spanmode: 'soft',
        bandwidth: 0.12,
        scalemode: 'width',
        scalegroup: 'all',
        line: { color: 'transparent', width: 0 },
        fillcolor: 'transparent',
        marker: {
          color: teamColour,
          size: 5.5,
          line: { width: 0.5, color: 'rgba(0,0,0,0.3)' },
          opacity: 0.85,
        },
        box: { visible: false },
        meanline: { visible: false },
        text: hoverTexts,
        hoveron: 'points',
        hoverinfo: 'text',
      } as unknown as Record<string, unknown>)
    }
    return { traces, xPositions, xLabels }
  }, [data, selected])

  const yTickConfig = useMemo(() => {
    if (!data) return { tickvals: [], ticktext: [] }
    const allTimes: number[] = []
    for (const d of Object.values(data.drivers)) {
      for (const l of d.laps) {
        if (!l.deleted && l.lap_time_ms != null) allTimes.push(l.lap_time_ms / 1000)
      }
    }
    if (allTimes.length === 0) return { tickvals: [], ticktext: [] }
    const minT = Math.min(...allTimes)
    const maxT = Math.max(...allTimes)
    const tickInterval = 5
    const startTick = Math.ceil(minT / tickInterval) * tickInterval
    const tickvals: number[] = []
    const ticktext: string[] = []
    for (let t = startTick; t <= maxT; t += tickInterval) {
      tickvals.push(t)
      const mins = Math.floor(t / 60)
      const secs = (t % 60).toFixed(3).padStart(6, '0')
      ticktext.push(`${mins}:${secs}`)
    }
    return { tickvals, ticktext }
  }, [data])

  const stats = useMemo(() => {
    if (!data) return []
    return selected.flatMap(dn => {
      const d = data.drivers[dn]
      if (!d) return []
      const laps = d.laps.filter(l => !l.deleted && l.lap_time_ms != null)
      const times = laps.map(l => l.lap_time_ms)
      if (times.length === 0) return []
      const sorted = [...times].sort((a, b) => a - b)
      return [{
        dn,
        abbr: d.abbreviation,
        colour: d.team_colour,
        count: times.length,
        best: sorted[0],
        median: median(times),
        avg: times.reduce((a, b) => a + b, 0) / times.length,
        worst: sorted[sorted.length - 1],
        iqr: sorted[Math.floor(sorted.length * 0.75)] - sorted[Math.floor(sorted.length * 0.25)],
      }]
    })
  }, [data, selected])

  if (loading) {
    return (
      <div style={{ padding: 20, border: `1px solid ${C.border}`, borderRadius: 18, background: C.surface }}>
        <div style={{ fontSize: 11, color: C.textDim, fontFamily: 'Inter, sans-serif' }}>Loading lap data...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ padding: 20, border: '1px solid #FECACA', borderRadius: 18, background: '#FEF2F2', color: '#B91C1C', fontFamily: 'Inter, sans-serif', fontSize: 11 }}>
        {error}
      </div>
    )
  }

  const xRange = xPositions.length > 0
    ? [Math.min(...xPositions) - 1.5, Math.max(...xPositions) + 1.5]
    : [-2, 2]

  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 18, overflow: 'hidden', boxShadow: '0 8px 24px rgba(19,35,61,0.04)' }}>
      <div style={{ padding: '14px 18px', borderBottom: `1px solid ${C.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div>
          <div style={{ fontSize: 14, fontFamily: 'Inter, sans-serif', fontWeight: 800, color: C.textBright }}>
            Lap Time Distribution
          </div>
          <div style={{ fontSize: 11, fontFamily: 'Inter, sans-serif', color: C.textMid, marginTop: 2, lineHeight: 1.5, maxWidth: 420 }}>
            All race laps grouped by driver. Hover for details.
          </div>
        </div>
      </div>

      <div style={{ padding: 18 }}>
        {allDrivers.length > 0 && (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
            <span style={{ fontSize: 9, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 600, letterSpacing: '0.08em', color: C.textDim, textTransform: 'uppercase', alignSelf: 'center', marginRight: 4 }}>
              Drivers
            </span>
            {allDrivers.map(d => {
              const active = selected.includes(d.key)
              const colour = d.colour?.startsWith('#') ? d.colour : `#${d.colour ?? '666'}`
              return (
                <button
                  key={d.key}
                  onClick={() => {
                    setSelected(prev =>
                      active ? prev.filter(x => x !== d.key) : prev.length < 4 ? [...prev, d.key] : prev
                    )
                  }}
                  style={{
                    padding: '5px 10px',
                    borderRadius: 8,
                    border: `1px solid ${active ? colour : C.border}`,
                    background: active ? colour + '15' : C.surfaceAlt,
                    color: active ? colour : C.textMid,
                    fontSize: 10,
                    fontFamily: 'JetBrains Mono, monospace',
                    fontWeight: 700,
                    cursor: 'pointer',
                  }}
                >
                  {d.abbr}
                </button>
              )
            })}
          </div>
        )}

        {traces.length > 0 ? (
          <Plot
            data={traces}
            layout={{
              autosize: true,
              height: 400,
              margin: { l: 56, r: 18, t: 14, b: 52, pad: 0 },
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { family: 'JetBrains Mono, monospace', size: 10, color: C.textDim },
              xaxis: {
                title: { text: '' },
                tickfont: { size: 12, color: C.textBright, family: 'JetBrains Mono, monospace' },
                tickvals: xPositions,
                ticktext: xLabels,
                linecolor: 'transparent',
                gridcolor: 'transparent',
                zeroline: false,
                range: xRange,
              },
              yaxis: {
                title: { text: '', standoff: 8, font: { size: 9, color: C.textDim, family: 'Inter, sans-serif' } },
                tickfont: { size: 9, color: C.textDim, family: 'JetBrains Mono, monospace' },
                tickvals: yTickConfig.tickvals,
                ticktext: yTickConfig.ticktext,
                linecolor: C.border,
                gridcolor: '#EEF1F6',
                zeroline: false,
                autorange: 'reversed',
              },
              hovermode: 'closest',
              dragmode: false,
              showlegend: false,
            }}
            config={{
              displayModeBar: false,
              responsive: true,
              staticPlot: false,
            }}
            style={{ width: '100%' }}
            useResizeHandler
          />
        ) : (
          <div style={{ padding: '40px 20px', textAlign: 'center', fontSize: 11, color: C.textDim, fontFamily: 'Inter, sans-serif' }}>
            {allDrivers.length === 0 ? 'No lap data available' : 'Select up to 4 drivers above'}
          </div>
        )}

        {stats.length > 0 && (
          <div style={{ marginTop: 14, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {stats.map(s => {
              const colour = s.colour?.startsWith('#') ? s.colour : `#${s.colour ?? '666'}`
              return (
                <div key={s.dn} style={{ border: `1px solid ${C.border}`, borderRadius: 10, padding: '6px 12px', background: C.surfaceAlt, minWidth: 140 }}>
                  <div style={{ fontSize: 10, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: colour, marginBottom: 4 }}>
                    {s.abbr}
                    <span style={{ fontWeight: 400, color: C.textDim, fontSize: 9, marginLeft: 4 }}>
                      ({s.count} laps)
                    </span>
                  </div>
                  <StatRow label="Best" value={`${(s.best / 1000).toFixed(3)}s`} />
                  <StatRow label="Median" value={`${(s.median / 1000).toFixed(3)}s`} />
                  <StatRow label="Avg" value={`${(s.avg / 1000).toFixed(3)}s`} />
                  <StatRow label="IQR" value={`${(s.iqr / 1000).toFixed(3)}s`} />
                </div>
              )
            })}
          </div>
        )}

        <div style={{ marginTop: 12, display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: 9, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 600, letterSpacing: '0.08em', color: C.textDim, textTransform: 'uppercase' }}>
            Compound
          </span>
          {Object.entries(COMPOUND_COLOURS).filter(([k]) => ['SOFT', 'MEDIUM', 'HARD', 'INTER', 'WET'].includes(k)).map(([compound, colour]) => (
            <div key={compound} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: colour, border: compound === 'HARD' ? '1px solid #CCC' : 'none' }} />
              <span style={{ fontSize: 10, fontFamily: 'Inter, sans-serif', color: C.textMid }}>
                {compound.charAt(0) + compound.slice(1).toLowerCase()}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 9, fontFamily: 'JetBrains Mono, monospace', color: C.textMid, lineHeight: 1.6 }}>
      <span style={{ color: C.textDim }}>{label}</span>
      <span style={{ fontWeight: 600, color: C.textBright }}>{value}</span>
    </div>
  )
}
