'use client'

import { useEffect, useRef, useState, useCallback } from 'react'

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// ── Design tokens (match telemetry page exactly) ──────────────────────────────
const C = {
  bg: '#F8F9FC',
  surface: '#FFFFFF',
  surfaceAlt: '#F5F7FB',
  border: '#D9E3EF',
  borderMid: '#C5D2E3',
  textDim: '#7D8BA2',
  textMid: '#56657C',
  textSub: '#293A52',
  textBright: '#13233D',
  red: '#E8002D',
  green: '#10B981',
  gold: '#F59E0B',
  teal: '#0EA5E9',
} as const

const PAD = { top: 16, right: 20, bottom: 32, left: 56 }

// ── Types ─────────────────────────────────────────────────────────────────────

type SpeedTrapEntry = {
  driver_number: number
  abbreviation: string
  team_name: string
  team_colour: string
  lap_time_ms: number
  speed_i1: number | null
  speed_i2: number | null
  speed_fl: number | null
  speed_st: number | null
  gap_to_pole_ms: number | null
  speed_st_rank: number
  s1_ms: number | null
  s2_ms: number | null
  s3_ms: number | null
}

type LapEntry = {
  lap_number: number
  lap_time_ms: number | null
  deleted: boolean
  quali_segment: number | null
}

type DriverProgression = {
  driver_number: number
  abbreviation: string
  team_colour: string
  team_name: string
  laps: LapEntry[]
}

type Insight = {
  tier: 'CRITICAL' | 'NOTABLE' | 'INFO'
  title: string
  detail: string
}

type QualiSpeedData = {
  speed_trap: SpeedTrapEntry[]
  lap_progression: Record<string, DriverProgression>
  insights: Insight[]
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function tc(hex: string | null, name?: string | null): string {
  if (hex && hex.trim()) return '#' + hex.replace('#', '')
  // fallback by team name
  const map: Record<string, string> = {
    Mercedes: '#27F4D2', Ferrari: '#E8002D', 'Red Bull': '#3671C6',
    McLaren: '#FF8000', Alpine: '#FF87BC', Aston: '#229971',
    Williams: '#64C4FF', Haas: '#B6BABD', Sauber: '#52E252',
    Racing: '#6692FF',
  }
  for (const [k, v] of Object.entries(map)) {
    if (name?.includes(k)) return v
  }
  return '#7D8BA2'
}

function fmtLap(ms: number | null): string {
  if (ms === null) return '—'
  const s = ms / 1000
  const m = Math.floor(s / 60)
  const rem = (s % 60).toFixed(3).padStart(6, '0')
  return m > 0 ? `${m}:${rem}` : rem
}

function fmtGap(ms: number | null): string {
  if (ms === null) return '—'
  return `+${(ms / 1000).toFixed(3)}`
}

// ── Section header — collapsible ──────────────────────────────────────────────
function SectionHeader({
  title, subtitle, open, onToggle,
}: {
  title: string
  subtitle: string
  open: boolean
  onToggle: () => void
}) {
  return (
    <button
      onClick={onToggle}
      style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        width: '100%', cursor: 'pointer', background: 'none', border: 'none',
        padding: '0 0 12px 0', textAlign: 'left',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        {/* Accent line */}
        <div style={{ width: 3, height: 28, borderRadius: 2, background: C.red, flexShrink: 0 }} />
        <div>
          <div style={{
            fontSize: 13, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 800,
            letterSpacing: '0.08em', textTransform: 'uppercase', color: C.textBright,
          }}>
            {title}
          </div>
          <div style={{ fontSize: 10, fontFamily: 'Inter, sans-serif', color: C.textDim, marginTop: 2 }}>
            {subtitle}
          </div>
        </div>
      </div>

      {/* Chevron */}
      <div style={{
        width: 28, height: 28, borderRadius: 8,
        background: C.surfaceAlt, border: `1px solid ${C.border}`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0, transition: 'transform 0.2s ease',
        transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
      }}>
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
          <path d="M2 4L6 8L10 4" stroke={C.textMid} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
    </button>
  )
}

// ── Speed trap leaderboard ────────────────────────────────────────────────────
function SpeedTrapLeaderboard({ data }: { data: SpeedTrapEntry[] }) {
  const maxST = Math.max(...data.map(d => d.speed_st ?? 0))
  const minST = Math.min(...data.map(d => d.speed_st ?? 999))
  const range = maxST - minST || 1

  // Sort by speed_st descending for the speed trap ranking
  const bySpeed = [...data].sort((a, b) => (b.speed_st ?? 0) - (a.speed_st ?? 0))
  const fastestST = bySpeed[0]?.speed_st ?? 0

  return (
    <div style={{ overflowX: 'auto' }}>
      {/* Column headers */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '32px 44px 1fr 88px 64px 64px 64px 64px',
        gap: 6, paddingBottom: 10,
        borderBottom: `1px solid ${C.border}`, marginBottom: 4,
        minWidth: 560,
      }}>
        {['#', 'DRV', 'SPEED TRAP', 'TIME', 'I1', 'I2', 'FL', 'ST'].map(h => (
          <span key={h} style={{
            fontSize: 8, color: C.textDim,
            fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700,
            letterSpacing: '0.12em', textTransform: 'uppercase',
            textAlign: ['TIME', 'I1', 'I2', 'FL', 'ST'].includes(h) ? 'right' : 'left',
          }}>{h}</span>
        ))}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 560 }}>
        {bySpeed.map((entry, idx) => {
          const colour    = tc(entry.team_colour, entry.team_name)
          const isFastest = idx === 0
          const stPct     = entry.speed_st ? ((entry.speed_st - minST) / range) * 100 : 0
          const stDelta   = entry.speed_st && fastestST ? fastestST - entry.speed_st : 0

          return (
            <div key={entry.driver_number} style={{
              display: 'grid',
              gridTemplateColumns: '32px 44px 1fr 88px 64px 64px 64px 64px',
              gap: 6, alignItems: 'center',
              padding: '8px 10px', borderRadius: 10,
              background: isFastest ? `${colour}08` : 'transparent',
              border: isFastest ? `1px solid ${colour}22` : '1px solid transparent',
            }}>
              {/* Rank */}
              <span style={{
                fontSize: 10, fontFamily: 'JetBrains Mono, monospace',
                color: isFastest ? colour : C.textDim,
                fontWeight: isFastest ? 700 : 400,
              }}>
                {idx + 1}
              </span>

              {/* Driver */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <div style={{ width: 3, height: 12, borderRadius: 2, background: colour, flexShrink: 0 }} />
                <span style={{
                  fontSize: 10, fontFamily: 'JetBrains Mono, monospace',
                  color: C.textBright, fontWeight: 700,
                }}>
                  {entry.abbreviation}
                </span>
              </div>

              {/* Speed bar */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{
                  flex: 1, height: 6, background: C.border,
                  borderRadius: 3, overflow: 'hidden',
                }}>
                  <div style={{
                    width: `${stPct}%`, height: '100%',
                    background: isFastest ? C.teal : colour + '99',
                    borderRadius: 3, transition: 'width 0.4s ease',
                  }} />
                </div>
                {stDelta > 0 && (
                  <span style={{
                    fontSize: 9, fontFamily: 'JetBrains Mono, monospace',
                    color: C.textDim, whiteSpace: 'nowrap',
                  }}>
                    -{stDelta.toFixed(0)}
                  </span>
                )}
              </div>

              {/* Lap time */}
              <div style={{ textAlign: 'right' }}>
                <div style={{
                  fontSize: 11, fontFamily: 'JetBrains Mono, monospace',
                  color: C.textBright, fontWeight: 600,
                }}>
                  {fmtLap(entry.lap_time_ms)}
                </div>
                {entry.gap_to_pole_ms !== null && entry.gap_to_pole_ms > 0 && (
                  <div style={{
                    fontSize: 9, fontFamily: 'JetBrains Mono, monospace',
                    color: C.textDim,
                  }}>
                    {fmtGap(entry.gap_to_pole_ms)}
                  </div>
                )}
              </div>

              {/* Speed trap columns */}
              {[entry.speed_i1, entry.speed_i2, entry.speed_fl, entry.speed_st].map((spd, si) => {
                const isSTCol = si === 3
                return (
                  <span key={si} style={{
                    fontSize: 11, fontFamily: 'JetBrains Mono, monospace',
                    color: isSTCol
                      ? (isFastest ? C.teal : C.textBright)
                      : C.textMid,
                    fontWeight: isSTCol && isFastest ? 700 : 400,
                    textAlign: 'right',
                  }}>
                    {spd !== null ? spd.toFixed(0) : '—'}
                  </span>
                )
              })}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Lap progression chart ────────────────────────────────────────────────────
function LapProgressionChart({
  progression, selected, onToggle,
}: {
  progression: Record<string, DriverProgression>
  selected: string[]
  onToggle: (dn: string) => void
}) {
  const canvasRef  = useRef<HTMLCanvasElement | null>(null)
  const wrapRef    = useRef<HTMLDivElement | null>(null)
  const [hovLap,   setHovLap]   = useState<number | null>(null)
  const [tooltip,  setTooltip]  = useState<{ lap: number; x: number; y: number; entries: { abbr: string; colour: string; ms: number | null; deleted: boolean }[] } | null>(null)

  // geometry ref to avoid stale closures in mouse handler
  const geomRef = useRef<{ maxLap: number; yMin: number; yMax: number } | null>(null)

  // Filter to valid laps for chart (not deleted, has time, within 110% of best)
  function validLaps(laps: LapEntry[]): LapEntry[] {
    const best = Math.min(...laps.filter(l => !l.deleted && l.lap_time_ms).map(l => l.lap_time_ms!))
    return laps.filter(l => !l.deleted && l.lap_time_ms && l.lap_time_ms <= best * 1.1)
  }

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const W = wrapRef.current?.clientWidth ?? 600
    const H = 240
    canvas.width = W; canvas.height = H
    const ctx = canvas.getContext('2d')!

    ctx.fillStyle = C.surface; ctx.fillRect(0, 0, W, H)

    const { top, right, bottom, left } = PAD
    const cW = W - left - right
    const cH = H - top - bottom

    const drivers = Object.entries(progression).filter(([dn]) => selected.includes(dn))
    if (!drivers.length) return

    // Y range: P5–P95 of all valid lap times
    const allMs: number[] = []
    drivers.forEach(([, d]) => validLaps(d.laps).forEach(l => allMs.push(l.lap_time_ms!)))
    if (!allMs.length) return
    allMs.sort((a, b) => a - b)
    const yMin = allMs[Math.floor(allMs.length * 0.05)] - 1000
    const yMax = allMs[Math.floor(allMs.length * 0.95)] + 3000

    let maxLap = 0
    drivers.forEach(([, d]) => d.laps.forEach(l => { if (l.lap_number > maxLap) maxLap = l.lap_number }))
    if (maxLap < 2) return

    geomRef.current = { maxLap, yMin, yMax }

    const toX = (lap: number) => left + ((lap - 1) / (maxLap - 1)) * cW
    const toY = (ms: number)  => top  + cH - ((ms - yMin) / (yMax - yMin)) * cH

    // Grid
    for (let i = 0; i <= 5; i++) {
      const ms = yMin + (i / 5) * (yMax - yMin)
      const y  = toY(ms)
      ctx.beginPath(); ctx.strokeStyle = i === 0 ? C.borderMid : C.border; ctx.lineWidth = 1
      ctx.moveTo(left, y); ctx.lineTo(left + cW, y); ctx.stroke()
      ctx.fillStyle = C.textDim; ctx.font = '600 10px "JetBrains Mono", monospace'; ctx.textAlign = 'right'
      ctx.fillText(fmtLap(ms), left - 6, y + 3)
    }
    const lapStep = Math.max(1, Math.ceil(maxLap / 10))
    for (let lap = 1; lap <= maxLap; lap += lapStep) {
      ctx.fillStyle = C.textDim; ctx.font = '600 10px "JetBrains Mono", monospace'; ctx.textAlign = 'center'
      ctx.fillText(String(lap), toX(lap), H - 10)
    }
    ctx.fillStyle = C.textDim; ctx.font = '600 10px "JetBrains Mono", monospace'; ctx.textAlign = 'center'
    ctx.fillText('LAP', left + cW / 2, H - 1)

    // Crosshair
    if (hovLap !== null) {
      const hx = toX(hovLap)
      ctx.beginPath(); ctx.strokeStyle = 'rgba(19,35,61,0.08)'; ctx.lineWidth = 1
      ctx.setLineDash([4, 4]); ctx.moveTo(hx, top); ctx.lineTo(hx, top + cH); ctx.stroke(); ctx.setLineDash([])
    }

    // Lines + dots per driver
    drivers.forEach(([, d], di) => {
      const colour = tc(d.team_colour, d.team_name)
      const valid  = validLaps(d.laps).sort((a, b) => a.lap_number - b.lap_number)
      if (!valid.length) return

      ctx.beginPath(); ctx.strokeStyle = colour; ctx.lineWidth = 2; ctx.lineJoin = 'round'
      if (di % 2 !== 0) ctx.setLineDash([6, 4])
      valid.forEach((l, i) => {
        const x = toX(l.lap_number); const y = toY(l.lap_time_ms!)
        if (i === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      })
      ctx.stroke(); ctx.setLineDash([])

      // Compound dots
      valid.forEach(l => {
        const x = toX(l.lap_number); const y = toY(l.lap_time_ms!)
        ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2)
        ctx.fillStyle = colour; ctx.fill()
        ctx.strokeStyle = C.surface; ctx.lineWidth = 1; ctx.stroke()
      })

      // Hover dot
      if (hovLap !== null) {
        const row = valid.find(l => l.lap_number === hovLap)
        if (row) {
          const hx = toX(row.lap_number); const hy = toY(row.lap_time_ms!)
          ctx.beginPath(); ctx.arc(hx, hy, 6, 0, Math.PI * 2)
          ctx.strokeStyle = colour + '55'; ctx.lineWidth = 2; ctx.stroke()
          ctx.beginPath(); ctx.arc(hx, hy, 4, 0, Math.PI * 2)
          ctx.fillStyle = colour; ctx.fill()
          ctx.strokeStyle = C.surface; ctx.lineWidth = 1.5; ctx.stroke()
        }
      }
    })
  }, [progression, selected, hovLap])

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const { left, right } = PAD
    const cW  = rect.width - left - right
    const nx  = Math.max(0, Math.min(1, (e.clientX - rect.left - left) / cW))
    const geom = geomRef.current
    if (!geom) return

    const lap = Math.round(nx * (geom.maxLap - 1)) + 1
    setHovLap(lap)

    const drivers = Object.entries(progression).filter(([dn]) => selected.includes(dn))
    const entries = drivers.map(([, d]) => {
      const row = d.laps.find(l => l.lap_number === lap)
      return {
        abbr:    d.abbreviation,
        colour:  tc(d.team_colour, d.team_name),
        ms:      row?.deleted ? null : (row?.lap_time_ms ?? null),
        deleted: row?.deleted ?? false,
      }
    })

    const tipX = Math.min(e.clientX - rect.left + 12, rect.width - 160)
    const tipY = Math.max(e.clientY - rect.top - 20, 8)
    setTooltip({ lap, x: tipX, y: tipY, entries })
  }, [progression, selected])

  const handleMouseLeave = useCallback(() => {
    setHovLap(null); setTooltip(null)
  }, [])

  const allDrivers = Object.entries(progression)

  return (
    <div>
      {/* Driver selector */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
        {allDrivers.map(([dn, d]) => {
          const isSel   = selected.includes(dn)
          const colour  = tc(d.team_colour, d.team_name)
          return (
            <button key={dn} onClick={() => onToggle(dn)} style={{
              display: 'flex', alignItems: 'center', gap: 5, padding: '5px 10px',
              borderRadius: 10, cursor: 'pointer', transition: 'all 0.12s',
              border:     `1px solid ${isSel ? colour + '55' : C.border}`,
              background: isSel ? `${colour}12` : C.surfaceAlt,
              color:      isSel ? C.textBright : C.textMid,
              fontSize: 10, fontFamily: 'JetBrains Mono, monospace',
              fontWeight: isSel ? 700 : 400,
            }}>
              <div style={{ width: 5, height: 5, borderRadius: '50%', background: colour }} />
              {d.abbreviation}
            </button>
          )
        })}
      </div>

      {/* Canvas */}
      <div ref={wrapRef} style={{ position: 'relative' }}>
        <canvas
          ref={canvasRef} height={240}
          style={{ display: 'block', width: '100%', cursor: 'crosshair', borderRadius: 12, border: `1px solid ${C.border}` }}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        />

        {/* Tooltip */}
        {tooltip && (
          <div style={{
            position: 'absolute', left: tooltip.x, top: tooltip.y,
            pointerEvents: 'none', zIndex: 100,
            background: 'rgba(255,255,255,0.96)', border: `1px solid ${C.border}`,
            borderRadius: 10, padding: '8px 12px', minWidth: 140,
            boxShadow: '0 8px 20px rgba(19,35,61,0.10)',
          }}>
            <div style={{ fontSize: 9, fontFamily: 'JetBrains Mono, monospace', color: C.textDim, fontWeight: 700, marginBottom: 6 }}>
              LAP {tooltip.lap}
            </div>
            {tooltip.entries.map(e => (
              <div key={e.abbr} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <div style={{ width: 3, height: 28, borderRadius: 2, background: e.colour, flexShrink: 0 }} />
                <div>
                  <div style={{ fontSize: 9, color: e.colour, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700 }}>{e.abbr}</div>
                  <div style={{ fontSize: 14, fontFamily: 'JetBrains Mono, monospace', color: C.textBright, fontWeight: 700, lineHeight: 1.2 }}>
                    {e.deleted ? <span style={{ color: C.red, fontSize: 10 }}>DELETED</span> : e.ms !== null ? fmtLap(e.ms) : '—'}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Insight cards ─────────────────────────────────────────────────────────────
function InsightCards({ insights }: { insights: Insight[] }) {
  const TIER_STYLE = {
    CRITICAL: { accent: C.red,  bg: 'rgba(232,0,45,0.04)',   border: 'rgba(232,0,45,0.14)' },
    NOTABLE:  { accent: C.gold, bg: 'rgba(245,158,11,0.04)', border: 'rgba(245,158,11,0.14)' },
    INFO:     { accent: C.textDim, bg: C.surfaceAlt, border: C.border },
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {insights.map((ins, i) => {
        const style = TIER_STYLE[ins.tier] ?? TIER_STYLE.INFO
        return (
          <div key={i} style={{
            background: style.bg, border: `1px solid ${style.border}`,
            borderRadius: 12, padding: '12px 14px', position: 'relative', overflow: 'hidden',
          }}>
            <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 3, background: style.accent, borderRadius: '3px 0 0 3px' }} />
            <div style={{ paddingLeft: 8 }}>
              <span style={{
                fontSize: 8, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700,
                letterSpacing: '0.14em', textTransform: 'uppercase',
                color: style.accent, padding: '2px 6px', borderRadius: 4,
                background: `${style.accent}12`, border: `1px solid ${style.accent}20`,
                marginRight: 8,
              }}>
                {ins.tier}
              </span>
              <div style={{ fontSize: 13, fontFamily: 'Inter, sans-serif', fontWeight: 700, color: C.textBright, marginTop: 8, marginBottom: 4 }}>
                {ins.title}
              </div>
              <div style={{ fontSize: 11.5, fontFamily: 'Inter, sans-serif', color: C.textMid, lineHeight: 1.6 }}>
                {ins.detail}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function QualiSpeedPanel({ sessionKey }: { sessionKey: number }) {
  const [data,    setData]    = useState<QualiSpeedData | null>(null)
  const [loading, setLoading] = useState(false)

  // Section open/close state — all open by default
  const [openSpeed,    setOpenSpeed]    = useState(true)
  const [openLapProg,  setOpenLapProg]  = useState(true)
  const [openInsights, setOpenInsights] = useState(true)

  // Lap progression driver selection — default first two
  const [selectedDns, setSelectedDns] = useState<string[]>([])

  useEffect(() => {
    setLoading(true)
    fetch(`${BASE}/api/v1/sessions/${sessionKey}/analysis/quali-speed`)
      .then(r => r.json())
      .then((d: QualiSpeedData) => {
        setData(d)
        // Default: first two drivers in speed trap order
        const keys = Object.keys(d.lap_progression)
        setSelectedDns(keys.slice(0, 2))
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [sessionKey])

  const toggleDn = useCallback((dn: string) => {
    setSelectedDns(prev =>
      prev.includes(dn)
        ? prev.length > 1 ? prev.filter(d => d !== dn) : prev  // keep at least 1
        : prev.length < 4 ? [...prev, dn] : prev
    )
  }, [])

  if (loading) return (
    <div style={{ padding: 24, border: `1px solid ${C.border}`, borderRadius: 18, background: C.surface, color: C.textDim, fontFamily: 'Inter, sans-serif', fontSize: 13 }}>
      Loading speed analysis...
    </div>
  )

  if (!data || !data.speed_trap.length) return null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* ── SPEED TRAP SECTION ─────────────────────────────────────────────── */}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 20, overflow: 'hidden', boxShadow: '0 8px 32px rgba(19,35,61,0.03)' }}>
        <div style={{ padding: '16px 18px', borderBottom: openSpeed ? `1px solid ${C.border}` : 'none' }}>
          <SectionHeader
            title="Speed Trap Analysis"
            subtitle="Top speed at FIA timing points · best lap only"
            open={openSpeed}
            onToggle={() => setOpenSpeed(o => !o)}
          />
        </div>
        {openSpeed && (
          <div style={{ padding: '14px 16px' }}>
            <SpeedTrapLeaderboard data={data.speed_trap} />
          </div>
        )}
      </div>

      {/* ── LAP PROGRESSION SECTION ───────────────────────────────────────── */}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 20, overflow: 'hidden', boxShadow: '0 8px 32px rgba(19,35,61,0.03)' }}>
        <div style={{ padding: '16px 18px', borderBottom: openLapProg ? `1px solid ${C.border}` : 'none' }}>
          <SectionHeader
            title="Lap Progression"
            subtitle="Lap time improvement across the session · deleted laps excluded"
            open={openLapProg}
            onToggle={() => setOpenLapProg(o => !o)}
          />
        </div>
        {openLapProg && (
          <div style={{ padding: '14px 16px' }}>
            <LapProgressionChart
              progression={data.lap_progression}
              selected={selectedDns}
              onToggle={toggleDn}
            />
          </div>
        )}
      </div>

      {/* ── INSIGHTS SECTION ─────────────────────────────────────────────── */}
      {data.insights.length > 0 && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 20, overflow: 'hidden', boxShadow: '0 8px 32px rgba(19,35,61,0.03)' }}>
          <div style={{ padding: '16px 18px', borderBottom: openInsights ? `1px solid ${C.border}` : 'none' }}>
            <SectionHeader
              title="Speed Insights"
              subtitle="Rules-based analysis from speed trap data"
              open={openInsights}
              onToggle={() => setOpenInsights(o => !o)}
            />
          </div>
          {openInsights && (
            <div style={{ padding: '14px 16px' }}>
              <InsightCards insights={data.insights} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
