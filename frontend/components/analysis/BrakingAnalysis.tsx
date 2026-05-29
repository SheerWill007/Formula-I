'use client'

import { useEffect, useRef, useState } from 'react'
import { teamColour } from '@/lib/utils'
import type { InsightsData } from './CornerInsights'

export type { InsightsData }

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

function getErrorMessage(error: unknown, fallback = 'Failed to load braking analysis'): string {
  if (error instanceof Error) return error.message || fallback
  if (typeof error === 'string' && error.trim()) return error
  if (error && typeof error === 'object' && 'type' in error) {
    const type = String((error as { type?: unknown }).type ?? '').trim()
    return type ? `Failed while handling ${type}` : fallback
  }
  return fallback
}

type CornerStats = {
  corner_number: number
  brake_point_dist_m: number
  braking_dist_m: number
  decel_rate: number
  apex_speed_kmh: number
  exit_speed_kmh: number | null
  apex_x: number
  apex_y: number
  apex_dist_m: number
}

type DriverStats = {
  abbreviation: string
  team_name: string
  team_colour: string
  corners: CornerStats[]
  summary: {
    avg_braking_dist_m: number
    avg_decel_rate: number
    avg_apex_speed_kmh: number
    avg_exit_speed_kmh: number
    total_corners_detected: number
  }
}

type MatchedCorner = {
  corner_number: number
  apex_x: number
  apex_y: number
  apex_dist_m: number
  drivers: Record<string, CornerStats>
  delta: {
    brake_point_m: number
    braking_dist_m: number
    decel_rate: number
    apex_speed_kmh: number
    exit_speed_kmh: number
  } | null
}

type CompareStats = {
  session_key: number
  driver_keys: string[]
  drivers: Record<string, DriverStats>
  matched_corners: MatchedCorner[]
  insights?: InsightsData
}

type CornerCallout = {
  x: number
  y: number
  side: 'left' | 'right'
  corner: MatchedCorner
  entries: { abbr: string; colour: string; value: number }[]
  exits: { abbr: string; colour: string; value: number }[]
}

export default function BrakingAnalysis({
  sessionKey,
  drivers,
  trackPath,
  compact = false,
  onInsightsLoad,
}: {
  sessionKey: number
  drivers: number[]
  trackPath?: { x: number[]; y: number[] }
  compact?: boolean
  onInsightsLoad?: (insights: InsightsData | null, driverColours: Record<string, string>) => void
}) {
  const [data, setData] = useState<CompareStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const [callouts, setCallouts] = useState<CornerCallout[]>([])
  const [hoveredCornerNumber, setHoveredCornerNumber] = useState<number | null>(null)

  useEffect(() => {
    if (drivers.length < 2) {
      setData(null)
      setCallouts([])
      setHoveredCornerNumber(null)
      return
    }

    const abort = new AbortController()
    let active = true
    setLoading(true)
    setError(null)

    fetch(`${BASE}/api/v1/sessions/${sessionKey}/analysis/driver-compare-stats?drivers=${drivers.join(',')}`, {
      signal: abort.signal,
    })
      .then(res => {
        if (!res.ok) throw new Error('Failed to load braking analysis')
        return res.json()
      })
      .then((d: CompareStats) => {
        if (!active) return
        setData(d)
        if (onInsightsLoad && d.insights) {
          const colours: Record<string, string> = {}
          for (const dk of d.driver_keys) {
            const dr = d.drivers[dk]
            if (dr) colours[dr.abbreviation] = teamColour(dr.team_colour, dr.team_name)
          }
          onInsightsLoad(d.insights, colours)
        } else if (onInsightsLoad) {
          onInsightsLoad(null, {})
        }
      })
      .catch(err => {
        if (!active || err?.name === 'AbortError') return
        setError(getErrorMessage(err))
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
      abort.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionKey, drivers])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !data) return

    const W = canvas.clientWidth || 600
    const H = compact ? 240 : 320
    canvas.width = W
    canvas.height = H
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    ctx.clearRect(0, 0, W, H)
    ctx.fillStyle = '#F8F9FC'
    ctx.fillRect(0, 0, W, H)

    const points = trackPath?.x.length && trackPath.x.length === trackPath.y.length && trackPath.x.length > 1
      ? trackPath.x.map((x, i) => ({ x, y: trackPath.y[i] }))
      : data.matched_corners
        .slice()
        .sort((a, b) => a.apex_dist_m - b.apex_dist_m)
        .map(c => ({ x: c.apex_x, y: c.apex_y }))

    if (points.length < 2) {
      setCallouts([])
      setHoveredCornerNumber(null)
      return
    }

    const xs = points.map(p => p.x)
    const ys = points.map(p => p.y)
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const minY = Math.min(...ys)
    const maxY = Math.max(...ys)
    const pad = compact ? 28 : 36
    const trackWidth = maxX - minX || 1
    const trackHeight = maxY - minY || 1
    const scale = Math.min((W - pad * 2) / trackWidth, (H - pad * 2) / trackHeight) * 0.9
    const offsetX = (W - trackWidth * scale) / 2
    const offsetY = (H - trackHeight * scale) / 2
    const tx = (x: number) => (x - minX) * scale + offsetX
    const ty = (y: number) => (y - minY) * scale + offsetY
    const [driverAKey, driverBKey] = data.driver_keys

    ctx.lineWidth = 3.5
    ctx.strokeStyle = '#111827'
    ctx.lineJoin = 'round'
    ctx.lineCap = 'round'
    ctx.beginPath()
    points.forEach((p, i) => {
      if (i === 0) ctx.moveTo(tx(p.x), ty(p.y))
      else ctx.lineTo(tx(p.x), ty(p.y))
    })
    ctx.stroke()

    const nextCallouts: CornerCallout[] = []

    data.matched_corners.forEach(corner => {
      const driverA = data.drivers[driverAKey]
      const driverB = data.drivers[driverBKey]
      const base = teamColour(driverA?.team_colour ?? driverB?.team_colour)
      const alt = teamColour(driverB?.team_colour ?? driverA?.team_colour, driverB?.team_name ?? driverA?.team_name)
      const val = corner.delta?.brake_point_m ?? 0
      const colour = val <= 0 ? base : alt
      const x = tx(corner.apex_x)
      const y = ty(corner.apex_y)
      const side: 'left' | 'right' = x < W * 0.52 ? 'right' : 'left'

      ctx.beginPath()
      ctx.font = '900 18px Inter, sans-serif'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.lineWidth = 3
      ctx.strokeStyle = '#FFFFFF'
      ctx.strokeText('•', x, y)
      ctx.fillStyle = colour
      ctx.fillText('•', x, y)

      const entries = Object.entries(corner.drivers)
        .map(([dn, stats]) => ({
          abbr: data.drivers[dn]?.abbreviation ?? dn,
          colour: teamColour(data.drivers[dn]?.team_colour, data.drivers[dn]?.team_name),
          value: stats.brake_point_dist_m,
        }))
        .sort((a, b) => a.value - b.value)

      const exits = Object.entries(corner.drivers)
        .map(([dn, stats]) => ({
          abbr: data.drivers[dn]?.abbreviation ?? dn,
          colour: teamColour(data.drivers[dn]?.team_colour, data.drivers[dn]?.team_name),
          value: stats.exit_speed_kmh ?? 0,
        }))
        .sort((a, b) => b.value - a.value)

      nextCallouts.push({ x, y, side, corner, entries, exits })
    })

    setCallouts(nextCallouts)
  }, [compact, data, trackPath])

  const handleMove = (event: React.MouseEvent<HTMLDivElement>) => {
    if (!callouts.length) return
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const x = event.clientX - rect.left
    const y = event.clientY - rect.top

    let best: CornerCallout | null = null
    let bestDist = compact ? 18 : 22
    for (const callout of callouts) {
      const dx = x - callout.x
      const dy = y - callout.y
      const dist = Math.hypot(dx, dy)
      if (dist < bestDist) {
        bestDist = dist
        best = callout
      }
    }

    setHoveredCornerNumber(best?.corner.corner_number ?? null)
  }

  if (drivers.length < 2 || loading || error || !data) {
    if (loading) {
      return (
        <div style={{ padding: 20, border: '1px solid #D9E3EF', borderRadius: 18, background: '#FFFFFF', color: '#7D8BA2', fontFamily: 'Inter, sans-serif', fontSize: 13 }}>
          Loading braking analysis...
        </div>
      )
    }

    if (error) {
      return (
        <div style={{ padding: 20, border: '1px solid #FECACA', borderRadius: 18, background: '#FEF2F2', color: '#B91C1C', fontFamily: 'Inter, sans-serif', fontSize: 13 }}>
          {error}
        </div>
      )
    }

    return null
  }

  const d0 = data.drivers[data.driver_keys[0]]
  const d1 = data.drivers[data.driver_keys[1]]
  if (!d0 || !d1) return null

  const c0 = teamColour(d0.team_colour, d0.team_name)
  const c1 = teamColour(d1.team_colour, d1.team_name)
  const sameColour = c0.toLowerCase() === c1.toLowerCase()
  const altC1 = sameColour ? '#111827' : c1

  const corners = data.matched_corners
    .filter(c => c.delta)
    .sort((a, b) => a.apex_dist_m - b.apex_dist_m)

  const total = corners.length || 1
  const d0Wins = data.matched_corners.filter(c => (c.delta?.brake_point_m ?? 0) < 0).length
  const d1Wins = data.matched_corners.filter(c => (c.delta?.brake_point_m ?? 0) > 0).length

  return (
    <div style={{ background: '#FFFFFF', border: '1px solid #D9E3EF', borderRadius: compact ? 16 : 18, overflow: 'hidden', boxShadow: '0 8px 24px rgba(19,35,61,0.04)', height: '100%' }}>
      <div style={{ padding: compact ? '12px 14px' : '14px 18px', borderBottom: '1px solid #D9E3EF', display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
        <div>
          <div style={{ fontSize: compact ? 13 : 14, fontFamily: 'Inter, sans-serif', fontWeight: 800, color: '#13233D' }}>Braking Analysis</div>
          <div style={{ fontSize: compact ? 10 : 11, fontFamily: 'Inter, sans-serif', color: '#56657C', marginTop: 2, lineHeight: 1.35 }}>
            Compare where each driver brakes, slows, and exits the corner.
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <span style={{ fontSize: 9, fontFamily: 'JetBrains Mono, monospace', color: '#13233D', background: `${c0}14`, border: `1px solid ${c0}2A`, borderRadius: 999, padding: compact ? '4px 8px' : '6px 10px' }}>
            {d0.abbreviation}: {d0Wins}/{total}
          </span>
          <span style={{ fontSize: 9, fontFamily: 'JetBrains Mono, monospace', color: '#13233D', background: `${altC1}14`, border: `1px solid ${altC1}2A`, borderRadius: 999, padding: compact ? '4px 8px' : '6px 10px' }}>
            {d1.abbreviation}: {d1Wins}/{total}
          </span>
        </div>
      </div>

      <div style={{ padding: compact ? 14 : 18 }}>
        <div style={{ position: 'relative' }} onMouseMove={handleMove} onMouseLeave={() => setHoveredCornerNumber(null)}>
          <canvas ref={canvasRef} style={{ display: 'block', width: '100%', borderRadius: 14, border: '1px solid #E2E8F0', background: '#F8F9FC' }} />
          <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
            {callouts.filter(callout => hoveredCornerNumber === callout.corner.corner_number).map(({ x, y, side, corner, entries, exits }) => (
              <div
                key={corner.corner_number}
                style={{
                  position: 'absolute',
                  left: side === 'right' ? x + 14 : x - 14,
                  top: y,
                  transform: compact
                    ? (side === 'right' ? 'translate(0, -50%)' : 'translate(-100%, -50%)')
                    : (side === 'right' ? 'translate(0, -50%)' : 'translate(-100%, -50%)'),
                  minWidth: compact ? 96 : 112,
                  maxWidth: compact ? 120 : 132,
                  background: 'rgba(255,255,255,0.96)',
                  border: '1px solid #D9E3EF',
                  borderRadius: compact ? 10 : 12,
                  padding: compact ? '5px 7px' : '6px 8px',
                  boxShadow: '0 8px 20px rgba(19,35,61,0.08)',
                }}
              >
                <div style={{ fontSize: 8, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700, color: '#7D8BA2', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 4 }}>
                  C{corner.corner_number}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: compact ? 9 : 10, fontFamily: 'JetBrains Mono, monospace', color: '#13233D' }}>
                  <div style={{ color: '#56657C', marginBottom: 1 }}>Entry</div>
                  {entries.slice(0, compact ? 4 : 2).map(item => (
                    <div key={`${corner.corner_number}-entry-${item.abbr}`} style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <span style={{ color: item.colour, fontWeight: 700 }}>{item.abbr}</span>
                      <span style={{ color: item.colour, fontWeight: 700 }}>{item.value.toFixed(1)}m</span>
                    </div>
                  ))}
                  <div style={{ color: '#56657C', marginTop: 3, marginBottom: 1 }}>Exit</div>
                  {exits.slice(0, compact ? 4 : 2).map(item => (
                    <div key={`${corner.corner_number}-exit-${item.abbr}`} style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <span style={{ color: item.colour, fontWeight: 700 }}>{item.abbr}</span>
                      <span style={{ color: item.colour, fontWeight: 700 }}>{item.value.toFixed(1)}km/h</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {!compact && (
          <div style={{ marginTop: 14, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 }}>
            <Metric label="Avg brake point" value={`${d0.summary.avg_braking_dist_m.toFixed(1)} m / ${d1.summary.avg_braking_dist_m.toFixed(1)} m`} />
            <Metric label="Avg decel" value={`${d0.summary.avg_decel_rate.toFixed(2)} G / ${d1.summary.avg_decel_rate.toFixed(2)} G`} />
            <Metric label="Avg apex speed" value={`${d0.summary.avg_apex_speed_kmh.toFixed(1)} / ${d1.summary.avg_apex_speed_kmh.toFixed(1)} km/h`} />
          </div>
        )}

        <div style={{ marginTop: 14, borderTop: '1px solid #D9E3EF', paddingTop: 12, overflowX: 'auto' }}>
          <div style={{ display: 'grid', gridTemplateColumns: compact ? '48px 1fr 1fr 48px' : '56px 1fr 1fr 1fr 1fr', minWidth: compact ? 'auto' : 480, gap: 8, fontSize: 9, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 600, letterSpacing: '0.1em', color: '#7D8BA2', textTransform: 'uppercase', marginBottom: 8 }}>
            <div>Corner</div>
            <div>Driver</div>
            <div>Entry</div>
            <div>Exit</div>
            {!compact && <div>Faster</div>}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, minWidth: compact ? 'auto' : 480 }}>
            {corners.map(corner => (
              <div key={corner.corner_number} style={{ display: 'grid', gridTemplateColumns: compact ? '48px 1fr 1fr 48px' : '56px 1fr 1fr 1fr 1fr', gap: 8, alignItems: 'center', fontSize: compact ? 10 : 11, fontFamily: 'JetBrains Mono, monospace', color: '#13233D' }}>
                <div style={{ fontWeight: 700 }}>C{corner.corner_number}</div>
                <div style={{ color: '#56657C' }}>{d0.abbreviation} / {d1.abbreviation}</div>
                <div>
                  <div style={{ color: c0 }}>{(corner.drivers[data.driver_keys[0]]?.brake_point_dist_m ?? 0).toFixed(1)}m</div>
                  <div style={{ color: altC1 }}>{(corner.drivers[data.driver_keys[1]]?.brake_point_dist_m ?? 0).toFixed(1)}m</div>
                </div>
                <div>
                  <div style={{ color: c0 }}>{(corner.drivers[data.driver_keys[0]]?.exit_speed_kmh ?? 0).toFixed(1)}km/h</div>
                  <div style={{ color: altC1 }}>{(corner.drivers[data.driver_keys[1]]?.exit_speed_kmh ?? 0).toFixed(1)}km/h</div>
                </div>
                {!compact && (
                  <div style={{ fontWeight: 700 }}>
                    {corner.delta?.brake_point_m == null ? '—' : corner.delta.brake_point_m > 0 ? d1.abbreviation : d0.abbreviation}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ border: '1px solid #D9E3EF', borderRadius: 14, background: '#F8FBFE', padding: '10px 12px' }}>
      <div style={{ fontSize: 9, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700, color: '#7D8BA2', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontSize: 12, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: '#13233D' }}>
        {value}
      </div>
    </div>
  )
}
