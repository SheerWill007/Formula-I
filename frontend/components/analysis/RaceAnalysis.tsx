'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { teamColour, formatLapTime } from '@/lib/utils'

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// ── Types ─────────────────────────────────────────────────────────────────────

type LapRow = {
  lap_number: number
  lap_time_ms: number | null
  compound: string | null
  position: number | null
  stint: number | null
  deleted: boolean
}

type DriverLapData = {
  driver_number: number
  abbreviation: string
  team_name: string
  team_colour: string
  laps: LapRow[]
}

type PosDriver = {
  abbreviation: string
  team_colour: string
  team_name: string
  positions: Record<string, number>
}

type GapDriver = {
  driver_number: number
  abbreviation: string
  team_colour: string
  team_name: string
  gaps: Record<string, number>
}

type StintPace = {
  driver_number: number
  abbreviation: string
  team_name: string
  team_colour: string
  stint: number
  compound: string
  start_lap: number
  end_lap: number
  clean_laps: number
  avg_ms: string
  best_ms: number
  deg_ms_per_lap: string
}

type UndercutRow = {
  driver_number: number
  abbreviation: string
  team_name: string
  team_colour: string
  pit_lap: number
  compound_in: string | null
  compound_out: string | null
  tyre_life_laps: number | null
  pos_before: number | null
  pos_after: number | null
  pos_gain: number | null
  verdict: 'undercut' | 'overcut' | 'neutral'
}

type FastestLapRow = {
  driver_number: number
  full_name: string
  abbreviation: string
  team_name: string
  team_colour: string
  lap_number: number
  lap_time_ms: number
  compound: string | null
  tyre_life_laps: number | null
  position_on_lap: number | null
  gap_ms: number
}

type DriverInfo = {
  driver_number: number
  abbreviation: string
  team_name: string | null
  team_colour: string | null
}

// ── Constants ─────────────────────────────────────────────────────────────────

const CHART_BG   = '#FFFFFF'
const AXIS_COLOR = '#DCE6F5'
const TEXT_DIM   = '#7A8CA5'
const TEXT_MID   = '#56657C'
const CROSSHAIR  = 'rgba(20,35,60,0.16)'

const COMPOUND_COLOUR: Record<string, string> = {
  SOFT: '#E8002D', MEDIUM: '#FFD700', HARD: '#FFFFFF',
  INTER: '#39B54A', WET: '#0067FF',
}

const VERDICT_STYLE = {
  undercut: { bg: '#2CF4C522', border: '#2CF4C544', text: '#2CF4C5', label: 'UNDERCUT ↑' },
  overcut:  { bg: '#E8002D22', border: '#E8002D44', text: '#E8002D', label: 'LOST OUT ↓' },
  neutral:  { bg: '#52525B22', border: '#52525B44', text: '#71717A', label: 'NEUTRAL →'  },
}

// All charts share identical left/right padding so x-axes align pixel-perfect
const PAD = { top: 24, right: 110, bottom: 44, left: 72 }

const SURFACE = 'linear-gradient(180deg, rgba(248,250,255,0.98) 0%, rgba(242,246,252,0.98) 100%)'
const BORDER = 'rgba(204,218,236,0.95)'
const TEXT_DARK = '#14233C'

function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      background: SURFACE,
      border: `1px solid ${BORDER}`,
      borderRadius: '22px',
      boxShadow: '0 16px 42px rgba(24,39,75,0.08)',
      ...style,
    }}>
      {children}
    </div>
  )
}

function SectionTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px', padding: '16px 18px 8px' }}>
      <span style={{ fontSize: '14px', fontFamily: 'Inter, sans-serif', color: TEXT_DARK, fontWeight: 800 }}>{title}</span>
      {subtitle && <span style={{ fontSize: '10px', fontFamily: 'JetBrains Mono, monospace', color: TEXT_DIM }}>{subtitle}</span>}
    </div>
  )
}

// ── Canvas helpers ────────────────────────────────────────────────────────────

function clearCanvas(canvas: HTMLCanvasElement, W: number, H: number) {
  canvas.width = W; canvas.height = H
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = CHART_BG; ctx.fillRect(0, 0, W, H)
  return ctx
}

function makeToX(maxLap: number, W: number) {
  const cW = W - PAD.left - PAD.right
  return (lap: number) => PAD.left + ((lap - 1) / Math.max(maxLap - 1, 1)) * cW
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
function nxFromEvent(e: React.MouseEvent<HTMLCanvasElement>, W: number) {
  const rect = e.currentTarget.getBoundingClientRect()
  const cW   = rect.width - PAD.left - PAD.right
  return Math.max(0, Math.min(1, (e.clientX - rect.left - PAD.left) / cW))
}

function lapFromNx(nx: number, maxLap: number) {
  return Math.round(nx * (maxLap - 1)) + 1
}

// ── Tooltip card — uses fixed positioning so it's always above canvas ─────────
// Canvas elements create their own stacking context and sit above
// position:absolute children of the same container. Using position:fixed
// with coordinates converted to viewport space solves this permanently.

function TooltipCard({
  anchorRef,
  canvasOffsetX,
  canvasOffsetY,
  children,
}: {
  anchorRef: React.RefObject<HTMLDivElement | null>
  canvasOffsetX: number
  canvasOffsetY: number
  children: React.ReactNode
}) {
  const [vx, setVx] = useState(0)
  const [vy, setVy] = useState(0)

  useEffect(() => {
    const container = anchorRef.current
    if (!container) return
    const rect = container.getBoundingClientRect()
    setVx(rect.left + canvasOffsetX)
    setVy(rect.top  + canvasOffsetY)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canvasOffsetX, canvasOffsetY])

  return (
    <div style={{
      position:       'fixed',
      left:           vx,
      top:            vy,
      pointerEvents:  'none',
      zIndex:         9999,
      background:     '#111111EE',
      border:         '1px solid #2A2A2A',
      borderRadius:   '10px',
      padding:        '10px 14px',
      backdropFilter: 'blur(8px)',
      minWidth:       '148px',
    }}>
      {children}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function RaceAnalysis({
  sessionKey,
  sessionName,
  drivers: allDrivers,
}: {
  sessionKey: number
  sessionName: string
  drivers: DriverInfo[]
}) {
  const [selected,    setSelected]    = useState<number[]>([])
  const [lapData,     setLapData]     = useState<Record<string, DriverLapData>>({})
  const [posData,     setPosData]     = useState<{ total_laps: number; drivers: Record<string, PosDriver> }>({ total_laps: 0, drivers: {} })
  const [gapData,     setGapData]     = useState<{ total_laps: number; drivers: Record<string, GapDriver> }>({ total_laps: 0, drivers: {} })
  const [stintPace,   setStintPace]   = useState<StintPace[]>([])
  const [undercut,    setUndercut]    = useState<UndercutRow[]>([])
  const [fastestLaps, setFastestLaps] = useState<FastestLapRow[]>([])
  const [loading,     setLoading]     = useState(false)
  const [isMobile,    setIsMobile]    = useState(false)

  // Single hovered lap drives ALL charts simultaneously
  const [hovLap, setHovLap] = useState<number | null>(null)

  // Per-chart tooltip data + canvas-relative pixel position
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [lapTip,  setLapTip]  = useState<{ lap: number; entries: any[] } | null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [posTip,  setPosTip]  = useState<{ lap: number; entries: any[] } | null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [gapTip,  setGapTip]  = useState<{ lap: number; entries: any[] } | null>(null)
  const [lapTipXY, setLapTipXY] = useState({ x: 0, y: 0 })
  const [posTipXY, setPosTipXY] = useState({ x: 0, y: 0 })
  const [gapTipXY, setGapTipXY] = useState({ x: 0, y: 0 })

  const lapRef        = useRef<HTMLCanvasElement | null>(null)
  const posRef        = useRef<HTMLCanvasElement | null>(null)
  const gapRef        = useRef<HTMLCanvasElement | null>(null)
  const lapCardRef    = useRef<HTMLDivElement | null>(null)
  const posCardRef    = useRef<HTMLDivElement | null>(null)
  const gapCardRef    = useRef<HTMLDivElement | null>(null)
  const containerRef  = useRef<HTMLDivElement | null>(null)

  // Stable geometry for mouse handlers — avoids stale closures
  const geomRef = useRef<{
    maxLap: number
    lapYMin: number; lapYMax: number
    gapYMax: number
    numDrivers: number
    lapDrivers: DriverLapData[]
    posDrivers: Record<string, PosDriver>
    gapDrivers: Record<string, GapDriver>
  } | null>(null)

  // ── Init selection ────────────────────────────────────────────────────────

  useEffect(() => {
    if (allDrivers.length >= 2)
      setSelected([allDrivers[0].driver_number, allDrivers[1].driver_number])

    const handleResize = () => setIsMobile(window.innerWidth < 1024)
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allDrivers.map(d => d.driver_number).join(',')])

  // ── Fetch all race data ───────────────────────────────────────────────────

  useEffect(() => {
    if (!selected.length) return
     
    setLoading(true)
    const qs = selected.join(',')
    Promise.all([
      fetch(`${BASE}/api/v1/sessions/${sessionKey}/analysis/lap-evolution?drivers=${qs}`).then(r => r.json()),
      fetch(`${BASE}/api/v1/sessions/${sessionKey}/analysis/position-changes`).then(r => r.json()),
      fetch(`${BASE}/api/v1/sessions/${sessionKey}/analysis/gap-to-leader`).then(r => r.json()),
      fetch(`${BASE}/api/v1/sessions/${sessionKey}/analysis/stint-pace`).then(r => r.json()),
      fetch(`${BASE}/api/v1/sessions/${sessionKey}/analysis/undercut`).then(r => r.json()),
      fetch(`${BASE}/api/v1/sessions/${sessionKey}/analysis/fastest-lap`).then(r => r.json()),
    ])
      .then(([evo, pos, gap, stints, uc, fl]) => {
        setLapData(evo.drivers ?? {})
        setPosData(pos)
        setGapData(gap)
        setStintPace(Array.isArray(stints) ? stints : [])
        setUndercut(Array.isArray(uc) ? uc : [])
        setFastestLaps(Array.isArray(fl) ? fl : [])
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionKey, selected.join(',')])

  const toggleDriver = (dn: number) =>
    setSelected(prev =>
      prev.includes(dn) ? prev.filter(d => d !== dn) : prev.length < 4 ? [...prev, dn] : prev
    )

  // ── Single maxLap for ALL charts ──────────────────────────────────────────

  const maxLap = Math.max(
    posData.total_laps,
    gapData.total_laps,
    ...Object.values(lapData).flatMap(d => d.laps.map(l => l.lap_number)),
    2
  )

  // ── Live leaderboard at hovLap (or final lap) ─────────────────────────────

  const leaderboardLap = hovLap ?? maxLap
  const leaderboard = Object.entries(posData.drivers)
    .map(([dn, data]) => ({
      driver_number: parseInt(dn),
      abbreviation:  data.abbreviation,
      team_colour:   data.team_colour,
      team_name:     data.team_name,
      position:      data.positions[String(leaderboardLap)] ?? null,
      gap:           gapData.drivers[dn]?.gaps[String(leaderboardLap)] ?? null,
    }))
    .filter(d => d.position !== null)
    .sort((a, b) => (a.position ?? 99) - (b.position ?? 99))

  // ── Draw: lap time evolution ──────────────────────────────────────────────

  useEffect(() => {
    const canvas = lapRef.current
    if (!canvas || !Object.keys(lapData).length) return
    const W = containerRef.current?.clientWidth ?? 900
    const H = 280
    const ctx = clearCanvas(canvas, W, H)
    const cW = W - PAD.left - PAD.right
    const cH = H - PAD.top  - PAD.bottom

    const allMs: number[] = []
    Object.values(lapData).forEach(d =>
      d.laps.forEach(l => { if (l.lap_time_ms && !l.deleted && l.lap_time_ms < 300000) allMs.push(l.lap_time_ms) })
    )
    if (!allMs.length) return
    allMs.sort((a, b) => a - b)
    const yMin = allMs[Math.floor(allMs.length * 0.05)] - 1500
    const yMax = allMs[Math.floor(allMs.length * 0.95)] + 4000

    const g = geomRef.current
    if (g) { g.lapYMin = yMin; g.lapYMax = yMax; g.lapDrivers = Object.values(lapData); g.maxLap = maxLap }
    else geomRef.current = { maxLap, lapYMin: yMin, lapYMax: yMax, gapYMax: 60, numDrivers: 0, lapDrivers: Object.values(lapData), posDrivers: {}, gapDrivers: {} }

    const toX = makeToX(maxLap, W)
    const toY = (ms: number) => PAD.top + cH - ((ms - yMin) / (yMax - yMin)) * cH

    for (let i = 0; i <= 5; i++) {
      const ms = yMin + (i / 5) * (yMax - yMin); const y = toY(ms)
      ctx.beginPath(); ctx.strokeStyle = AXIS_COLOR; ctx.lineWidth = 1
      ctx.moveTo(PAD.left, y); ctx.lineTo(PAD.left + cW, y); ctx.stroke()
      ctx.fillStyle = TEXT_DIM; ctx.font = '10px JetBrains Mono, monospace'; ctx.textAlign = 'right'
      ctx.fillText(formatLapTime(ms), PAD.left - 6, y + 3)
    }
    const lapStep = Math.max(1, Math.ceil(maxLap / 10))
    for (let lap = 1; lap <= maxLap; lap += lapStep) {
      ctx.fillStyle = TEXT_DIM; ctx.font = '10px JetBrains Mono, monospace'; ctx.textAlign = 'center'
      ctx.fillText(String(lap), toX(lap), H - 12)
    }
    ctx.fillStyle = TEXT_MID; ctx.font = '10px JetBrains Mono, monospace'; ctx.textAlign = 'center'
    ctx.fillText('LAP', PAD.left + cW / 2, H - 2)

    if (hovLap !== null) {
      ctx.beginPath(); ctx.strokeStyle = CROSSHAIR; ctx.lineWidth = 1
      ctx.moveTo(toX(hovLap), PAD.top); ctx.lineTo(toX(hovLap), PAD.top + cH); ctx.stroke()
    }

    Object.values(lapData).forEach(driver => {
      const colour = '#' + driver.team_colour
      const valid = driver.laps.filter(l => l.lap_time_ms && !l.deleted && l.lap_time_ms >= yMin && l.lap_time_ms <= yMax).sort((a, b) => a.lap_number - b.lap_number)
      if (!valid.length) return
      ctx.beginPath(); ctx.strokeStyle = colour; ctx.lineWidth = 2; ctx.lineJoin = 'round'
      // eslint-disable-next-line @typescript-eslint/no-unused-expressions
      valid.forEach((l, i) => { i === 0 ? ctx.moveTo(toX(l.lap_number), toY(l.lap_time_ms!)) : ctx.lineTo(toX(l.lap_number), toY(l.lap_time_ms!)) })
      ctx.stroke()
      valid.forEach(l => {
        const dot = COMPOUND_COLOUR[l.compound ?? ''] ?? '#555'
        ctx.beginPath(); ctx.arc(toX(l.lap_number), toY(l.lap_time_ms!), 3, 0, Math.PI * 2); ctx.fillStyle = dot; ctx.fill()
        ctx.beginPath(); ctx.arc(toX(l.lap_number), toY(l.lap_time_ms!), 3, 0, Math.PI * 2); ctx.strokeStyle = colour + '99'; ctx.lineWidth = 1; ctx.stroke()
      })
      if (hovLap !== null) {
        const row = valid.find(l => l.lap_number === hovLap)
        if (row) {
          ctx.beginPath(); ctx.arc(toX(row.lap_number), toY(row.lap_time_ms!), 7, 0, Math.PI * 2); ctx.strokeStyle = colour + '55'; ctx.lineWidth = 2; ctx.stroke()
          ctx.beginPath(); ctx.arc(toX(row.lap_number), toY(row.lap_time_ms!), 5, 0, Math.PI * 2); ctx.fillStyle = colour; ctx.fill()
          ctx.beginPath(); ctx.arc(toX(row.lap_number), toY(row.lap_time_ms!), 5, 0, Math.PI * 2); ctx.strokeStyle = '#0A0A0A'; ctx.lineWidth = 1.5; ctx.stroke()
        }
      }
    })
  }, [lapData, hovLap, maxLap])

  // ── Draw: gap to leader ───────────────────────────────────────────────────

  useEffect(() => {
    const canvas = gapRef.current
    if (!canvas || !Object.keys(gapData.drivers).length) return
    const W = containerRef.current?.clientWidth ?? 900
    const H = 200
    const ctx = clearCanvas(canvas, W, H)
    const cW = W - PAD.left - PAD.right
    const cH = H - PAD.top  - PAD.bottom

    const allGaps: number[] = []
    Object.values(gapData.drivers).forEach(d => Object.values(d.gaps).forEach(g => { if (g > 0 && g < 120) allGaps.push(g) }))
    const yMax = Math.min(Math.max(...allGaps, 5) * 1.08, 60)

    if (geomRef.current) { geomRef.current.gapYMax = yMax; geomRef.current.gapDrivers = gapData.drivers; geomRef.current.maxLap = maxLap }

    const toX = makeToX(maxLap, W)
    const toY = (gap: number) => PAD.top + (Math.min(gap, yMax) / yMax) * cH

    const gridStep = yMax <= 10 ? 2 : yMax <= 20 ? 5 : yMax <= 40 ? 10 : 20
    for (let g = 0; g <= yMax; g += gridStep) {
      const y = toY(g)
      ctx.beginPath(); ctx.strokeStyle = g === 0 ? '#2A2A2A' : AXIS_COLOR; ctx.lineWidth = 1
      ctx.moveTo(PAD.left, y); ctx.lineTo(PAD.left + cW, y); ctx.stroke()
      ctx.fillStyle = TEXT_DIM; ctx.font = '10px JetBrains Mono, monospace'; ctx.textAlign = 'right'
      ctx.fillText(g === 0 ? 'LEAD' : `${g}s`, PAD.left - 6, y + 3)
    }
    const lapStep = Math.max(1, Math.ceil(maxLap / 10))
    for (let lap = 1; lap <= maxLap; lap += lapStep) {
      ctx.fillStyle = TEXT_DIM; ctx.font = '10px JetBrains Mono, monospace'; ctx.textAlign = 'center'
      ctx.fillText(String(lap), toX(lap), H - 12)
    }
    ctx.fillStyle = TEXT_MID; ctx.font = '10px JetBrains Mono, monospace'; ctx.textAlign = 'center'
    ctx.fillText('LAP', PAD.left + cW / 2, H - 2)

    if (hovLap !== null) {
      ctx.beginPath(); ctx.strokeStyle = CROSSHAIR; ctx.lineWidth = 1
      ctx.moveTo(toX(hovLap), PAD.top); ctx.lineTo(toX(hovLap), PAD.top + cH); ctx.stroke()
    }

    const sorted = [...Object.entries(gapData.drivers)].sort(([a], [b]) =>
      (selected.includes(parseInt(a)) ? 1 : 0) - (selected.includes(parseInt(b)) ? 1 : 0)
    )
    sorted.forEach(([dn, data]) => {
      const isSel  = selected.includes(parseInt(dn))
      const colour = '#' + data.team_colour
      const pts    = Object.entries(data.gaps).map(([lap, gap]) => ({ lap: parseInt(lap), gap })).filter(p => p.gap >= 0 && p.gap < 120).sort((a, b) => a.lap - b.lap)
      if (!pts.length) return
      ctx.beginPath(); ctx.strokeStyle = isSel ? colour : colour + '28'; ctx.lineWidth = isSel ? 2 : 0.8; ctx.lineJoin = 'round'
      // eslint-disable-next-line @typescript-eslint/no-unused-expressions
      pts.forEach(({ lap, gap }, i) => { i === 0 ? ctx.moveTo(toX(lap), toY(gap)) : ctx.lineTo(toX(lap), toY(gap)) })
      ctx.stroke()
      if (isSel && pts.length) {
        const last = pts[pts.length - 1]
        ctx.fillStyle = colour; ctx.font = 'bold 10px JetBrains Mono, monospace'; ctx.textAlign = 'left'
        ctx.fillText(data.abbreviation, toX(last.lap) + 8, toY(last.gap) + 4)
      }
      if (isSel && hovLap !== null) {
        const gap = data.gaps[String(hovLap)]
        if (gap !== undefined && gap >= 0 && gap < 120) {
          ctx.beginPath(); ctx.arc(toX(hovLap), toY(gap), 6, 0, Math.PI * 2); ctx.strokeStyle = colour + '55'; ctx.lineWidth = 2; ctx.stroke()
          ctx.beginPath(); ctx.arc(toX(hovLap), toY(gap), 4, 0, Math.PI * 2); ctx.fillStyle = colour; ctx.fill()
          ctx.beginPath(); ctx.arc(toX(hovLap), toY(gap), 4, 0, Math.PI * 2); ctx.strokeStyle = '#0A0A0A'; ctx.lineWidth = 1.5; ctx.stroke()
        }
      }
    })
  }, [gapData, hovLap, selected, maxLap])

  // ── Draw: position changes ────────────────────────────────────────────────

  useEffect(() => {
    const canvas = posRef.current
    if (!canvas || !posData.total_laps) return
    const W = containerRef.current?.clientWidth ?? 900
    const H = 240
    const ctx = clearCanvas(canvas, W, H)
    const cW = W - PAD.left - PAD.right
    const cH = H - PAD.top  - PAD.bottom

    const allDriverEntries = Object.entries(posData.drivers)
    const numDrivers = allDriverEntries.length
    if (numDrivers < 2 || maxLap < 2) return

    if (geomRef.current) { geomRef.current.numDrivers = numDrivers; geomRef.current.posDrivers = posData.drivers; geomRef.current.maxLap = maxLap }

    const toX = makeToX(maxLap, W)
    const toY = (pos: number) => PAD.top + ((pos - 1) / (numDrivers - 1)) * cH

    for (let p = 1; p <= numDrivers; p += 4) {
      const y = toY(p)
      ctx.beginPath(); ctx.strokeStyle = AXIS_COLOR; ctx.lineWidth = 1
      ctx.moveTo(PAD.left, y); ctx.lineTo(PAD.left + cW, y); ctx.stroke()
      ctx.fillStyle = TEXT_DIM; ctx.font = '10px JetBrains Mono, monospace'; ctx.textAlign = 'right'
      ctx.fillText(`P${p}`, PAD.left - 6, y + 4)
    }
    const lapStep = Math.max(1, Math.ceil(maxLap / 10))
    for (let lap = 1; lap <= maxLap; lap += lapStep) {
      ctx.fillStyle = TEXT_DIM; ctx.font = '10px JetBrains Mono, monospace'; ctx.textAlign = 'center'
      ctx.fillText(String(lap), toX(lap), H - 12)
    }
    ctx.fillStyle = TEXT_MID; ctx.font = '10px JetBrains Mono, monospace'; ctx.textAlign = 'center'
    ctx.fillText('LAP', PAD.left + cW / 2, H - 2)

    if (hovLap !== null) {
      ctx.beginPath(); ctx.strokeStyle = CROSSHAIR; ctx.lineWidth = 1
      ctx.moveTo(toX(hovLap), PAD.top); ctx.lineTo(toX(hovLap), PAD.top + cH); ctx.stroke()
    }

    const sorted = [...allDriverEntries].sort(([a], [b]) =>
      (selected.includes(parseInt(a)) ? 1 : 0) - (selected.includes(parseInt(b)) ? 1 : 0)
    )
    sorted.forEach(([dn, data]) => {
      const isSel  = selected.includes(parseInt(dn))
      const colour = '#' + data.team_colour
      const pts    = Object.entries(data.positions).map(([lap, pos]) => ({ lap: parseInt(lap), pos })).sort((a, b) => a.lap - b.lap)
      if (!pts.length) return
      ctx.beginPath(); ctx.strokeStyle = isSel ? colour : colour + '28'; ctx.lineWidth = isSel ? 2.5 : 0.8; ctx.lineJoin = 'round'
      // eslint-disable-next-line @typescript-eslint/no-unused-expressions
      pts.forEach(({ lap, pos }, i) => { i === 0 ? ctx.moveTo(toX(lap), toY(pos)) : ctx.lineTo(toX(lap), toY(pos)) })
      ctx.stroke()
      if (isSel && pts.length) {
        const last = pts[pts.length - 1]
        ctx.fillStyle = colour; ctx.font = 'bold 10px JetBrains Mono, monospace'; ctx.textAlign = 'left'
        ctx.fillText(data.abbreviation, toX(last.lap) + 8, toY(last.pos) + 4)
      }
      if (isSel && hovLap !== null) {
        const pos = data.positions[String(hovLap)]
        if (pos !== undefined) {
          ctx.beginPath(); ctx.arc(toX(hovLap), toY(pos), 6, 0, Math.PI * 2); ctx.strokeStyle = colour + '55'; ctx.lineWidth = 2; ctx.stroke()
          ctx.beginPath(); ctx.arc(toX(hovLap), toY(pos), 4, 0, Math.PI * 2); ctx.fillStyle = colour; ctx.fill()
          ctx.beginPath(); ctx.arc(toX(hovLap), toY(pos), 4, 0, Math.PI * 2); ctx.strokeStyle = '#0A0A0A'; ctx.lineWidth = 1.5; ctx.stroke()
        }
      }
    })
  }, [posData, hovLap, selected, maxLap])

  // ── Shared mouse handler ──────────────────────────────────────────────────

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const W    = containerRef.current?.clientWidth ?? 900
    const nx   = nxFromEvent(e, W)
    const geom = geomRef.current
    if (!geom) return
    const lap = lapFromNx(nx, geom.maxLap)
    setHovLap(lap)

    // Lap tooltip entries
    const lapEntries = geom.lapDrivers.filter(d => selected.includes(d.driver_number)).map(d => {
      const sorted = [...d.laps].sort((a, b) => a.lap_number - b.lap_number)
      const cur  = sorted.find(l => l.lap_number === lap)
      const prev = sorted.find(l => l.lap_number === lap - 1)
      const isPit = !cur || cur.deleted || cur.lap_time_ms === null
      const tyrChanged = cur?.compound !== prev?.compound && prev?.compound != null
      return { abbr: d.abbreviation, colour: '#' + d.team_colour, lap_time_ms: isPit ? null : (cur?.lap_time_ms ?? null), compound: cur?.compound ?? prev?.compound ?? null, position: cur?.position ?? null, is_pit: isPit || tyrChanged, tyre_changed: tyrChanged && !isPit }
    })
    setLapTip({ lap, entries: lapEntries })

    // Position tooltip
    const posEntries = Object.entries(geom.posDrivers).filter(([dn]) => selected.includes(parseInt(dn))).map(([, data]) => ({ abbr: data.abbreviation, colour: '#' + data.team_colour, position: data.positions[String(lap)] ?? null })).sort((a, b) => (a.position ?? 99) - (b.position ?? 99))
    setPosTip({ lap, entries: posEntries })

    // Gap tooltip
    const gapEntries = Object.entries(geom.gapDrivers).filter(([dn]) => selected.includes(parseInt(dn))).map(([, data]) => ({ abbr: data.abbreviation, colour: '#' + data.team_colour, gap_s: data.gaps[String(lap)] ?? null })).sort((a, b) => (a.gap_s ?? 999) - (b.gap_s ?? 999))
    setGapTip({ lap, entries: gapEntries })

    // Store canvas-relative positions for each tooltip
    // We convert to viewport coords in TooltipCard via the container's getBoundingClientRect
    const rect = e.currentTarget.getBoundingClientRect()
    const rawX = e.clientX - rect.left + 16
    const rawY = Math.max(e.clientY - rect.top - 20, 8)
    const clampX = Math.min(rawX, W - 175)

    if (e.currentTarget === lapRef.current) setLapTipXY({ x: clampX, y: rawY })
    if (e.currentTarget === posRef.current) setPosTipXY({ x: clampX, y: rawY })
    if (e.currentTarget === gapRef.current) setGapTipXY({ x: clampX, y: rawY })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lapData, posData, gapData, selected])

  const handleMouseLeave = useCallback(() => {
    setHovLap(null); setLapTip(null); setPosTip(null); setGapTip(null)
  }, [])

  // ── Derived ───────────────────────────────────────────────────────────────

  const selectedStints   = stintPace.filter(s => selected.includes(s.driver_number)).sort((a, b) => a.driver_number - b.driver_number || a.stint - b.stint)
  const selectedUndercut = undercut.filter(u => selected.includes(u.driver_number))
  const overallFastest   = fastestLaps[0] ?? null
  const top5Fastest      = fastestLaps.slice(0, 5)

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div ref={containerRef} style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>

      {/* Driver selector */}
      <Card style={{ padding: '18px 20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '16px', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: '11px', color: TEXT_DIM, fontFamily: 'monospace', letterSpacing: '0.14em', marginBottom: '8px' }}>RACE ANALYSIS</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
              <span style={{ fontSize: '34px', lineHeight: 1, fontWeight: 900, color: TEXT_DARK, letterSpacing: '-0.04em' }}>Lap Evolution</span>
              <span style={{ fontSize: '12px', color: '#CC3648', fontWeight: 700, letterSpacing: '0.08em' }}>SESSION COMPLETE</span>
            </div>
            <div style={{ marginTop: '8px', display: 'flex', gap: '10px', flexWrap: 'wrap', fontSize: '12px', color: TEXT_MID, fontWeight: 600 }}>
              <span>{sessionName}</span>
              <span style={{ color: '#CBD5E1' }}>•</span>
              <span>{maxLap} laps</span>
              <span style={{ color: '#CBD5E1' }}>•</span>
              <span>Select up to 4 drivers</span>
            </div>
          </div>
          <div style={{ minWidth: isMobile ? '100%' : '280px', flex: isMobile ? '1 1 100%' : '1 1 320px', marginTop: isMobile ? '12px' : 0 }}>
            <div style={{ fontSize: '10px', color: TEXT_DIM, fontFamily: 'monospace', letterSpacing: '0.12em', marginBottom: '10px', textAlign: isMobile ? 'left' : 'right' }}>DRIVERS (MAX 4)</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', justifyContent: isMobile ? 'flex-start' : 'flex-end' }}>
          {allDrivers.map(d => {
            const isSel  = selected.includes(d.driver_number)
            const colour = teamColour(d.team_colour, d.team_name)
            return (
              <button key={d.driver_number} onClick={() => toggleDriver(d.driver_number)} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '7px 12px', borderRadius: '999px', cursor: 'pointer', transition: 'all 0.12s', border: isSel ? `1.5px solid ${colour}` : `1px solid ${BORDER}`, background: isSel ? `${colour}12` : 'rgba(255,255,255,0.72)', color: isSel ? TEXT_DARK : TEXT_MID, fontSize: '12px', fontWeight: isSel ? 800 : 600, fontFamily: 'Inter, sans-serif', boxShadow: isSel ? `0 8px 24px ${colour}12` : 'none' }}>
                <span style={{ width: '7px', height: '7px', borderRadius: '50%', background: colour, display: 'inline-block' }} />
                {d.abbreviation}
                {isSel && <span style={{ color: colour, fontSize: '10px', fontWeight: 900 }}>×</span>}
              </button>
            )
          })}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '14px', marginTop: '14px', paddingTop: '14px', borderTop: `1px solid ${BORDER}`, flexWrap: 'wrap' }}>
          {Object.entries(COMPOUND_COLOUR).map(([c, col]) => (
            <div key={c} style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
              <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: col }} />
              <span style={{ fontSize: '10px', fontFamily: 'monospace', color: TEXT_DIM }}>{c}</span>
            </div>
          ))}
        </div>
      </Card>

      {loading && <div style={{ textAlign: 'center', padding: '48px', color: TEXT_DIM, fontFamily: 'monospace' }}>Loading race data...</div>}

      {!loading && (
        <>
          <div className="race-analysis-grid" style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'minmax(0, 1.65fr) minmax(280px, 0.9fr)', gap: '18px', alignItems: 'start' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
              <div ref={lapCardRef}>
                <Card style={{ overflow: 'hidden', padding: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', padding: '18px 20px 8px', flexWrap: 'wrap' }}>
                    <SectionTitle title="Lap Time Evolution" subtitle="Selected drivers · pit laps excluded · compound markers on traces" />
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                      <div style={{ padding: '7px 12px', borderRadius: '999px', background: 'rgba(255,255,255,0.86)', border: `1px solid ${BORDER}`, fontSize: '11px', fontWeight: 800, color: TEXT_DARK }}>LAPS 1–{Math.min(15, maxLap)}</div>
                      <div style={{ padding: '7px 12px', borderRadius: '999px', background: '#EEF3FB', border: `1px solid ${BORDER}`, fontSize: '11px', fontWeight: 700, color: TEXT_DIM }}>FULL SESSION</div>
                    </div>
                  </div>
                  <div style={{ width: '100%', overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
                    <canvas ref={lapRef} height={isMobile ? 240 : 300} style={{ display: 'block', width: isMobile ? '130%' : '100%', cursor: 'crosshair', minWidth: isMobile ? 600 : 'auto' }} onMouseMove={handleMouseMove} onMouseLeave={handleMouseLeave} />
                  </div>
                </Card>
              </div>
              {lapTip && (
                <TooltipCard anchorRef={lapCardRef} canvasOffsetX={lapTipXY.x} canvasOffsetY={lapTipXY.y + 46}>
                  <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.5)', fontFamily: 'monospace', fontWeight: 700, letterSpacing: '0.08em', marginBottom: '8px' }}>LAP {lapTip.lap}</div>
                  {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                  {lapTip.entries.map((entry: any) => {
                    const compCol = COMPOUND_COLOUR[entry.compound ?? ''] ?? '#555'
                    return (
                      <div key={entry.abbr} style={{ display: 'flex', gap: '8px', alignItems: 'flex-start', marginBottom: '8px' }}>
                        <div style={{ width: '3px', minHeight: '44px', borderRadius: '2px', background: entry.colour, flexShrink: 0, marginTop: '2px' }} />
                        <div>
                          <div style={{ fontSize: '10px', color: entry.colour, fontFamily: 'monospace', fontWeight: 700 }}>
                            {entry.abbr}{entry.position !== null && <span style={{ color: 'rgba(255,255,255,0.45)', fontWeight: 400, marginLeft: '6px' }}>P{entry.position}</span>}
                          </div>
                          {entry.lap_time_ms === null
                            ? <div style={{ display: 'inline-block', marginTop: '2px', fontSize: '10px', fontFamily: 'monospace', fontWeight: 700, padding: '2px 8px', borderRadius: '4px', background: '#E8002D22', color: '#E8002D', border: '1px solid #E8002D44' }}>PIT</div>
                            : <div style={{ fontSize: '15px', fontFamily: 'monospace', color: '#FFFFFF', fontWeight: 700, lineHeight: 1.2 }}>{formatLapTime(entry.lap_time_ms)}</div>
                          }
                          {entry.compound && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginTop: '2px' }}>
                              <span style={{ fontSize: '9px', fontFamily: 'monospace', color: compCol }}>● {entry.compound}</span>
                              {entry.tyre_changed && <span style={{ fontSize: '10px', fontFamily: 'monospace', fontWeight: 900, padding: '1px 4px', borderRadius: '4px', background: compCol + '33', color: '#E8002D' }}>PIT</span>}
                            </div>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </TooltipCard>
              )}

              <div ref={gapCardRef}>
                <Card style={{ overflow: 'hidden', padding: 0 }}>
                  <div style={{ padding: '18px 20px 8px' }}>
                    <SectionTitle title={`Gap to Leader${leaderboard[0] ? ` (${leaderboard[0].abbreviation})` : ''}`} subtitle="Seconds behind race leader · pit laps excluded · capped at 60s" />
                  </div>
                  <div style={{ width: '100%', overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
                    <canvas ref={gapRef} height={isMobile ? 180 : 220} style={{ display: 'block', width: isMobile ? '130%' : '100%', cursor: 'crosshair', minWidth: isMobile ? 600 : 'auto' }} onMouseMove={handleMouseMove} onMouseLeave={handleMouseLeave} />
                  </div>
                </Card>
              </div>
              {gapTip && (
                <TooltipCard anchorRef={gapCardRef} canvasOffsetX={gapTipXY.x} canvasOffsetY={gapTipXY.y + 46}>
                  <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.5)', fontFamily: 'monospace', fontWeight: 700, letterSpacing: '0.08em', marginBottom: '8px' }}>LAP {gapTip.lap}</div>
                  {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                  {gapTip.entries.map((e: any) => (
                    <div key={e.abbr} style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                      <div style={{ width: '3px', height: '28px', borderRadius: '2px', background: e.colour, flexShrink: 0 }} />
                      <div>
                        <div style={{ fontSize: '10px', color: e.colour, fontFamily: 'monospace', fontWeight: 700 }}>{e.abbr}</div>
                        <div style={{ fontSize: '14px', fontFamily: 'monospace', color: '#FFFFFF', fontWeight: 700, lineHeight: 1.1 }}>
                          {e.gap_s === null ? '—' : e.gap_s === 0 ? 'LEADER' : `+${e.gap_s.toFixed(3)}s`}
                        </div>
                      </div>
                    </div>
                  ))}
                </TooltipCard>
              )}

              <div ref={posCardRef}>
                <Card style={{ overflow: 'hidden', padding: 0 }}>
                  <div style={{ padding: '18px 20px 8px' }}>
                    <SectionTitle title="Position Changes" subtitle="Full field · selected drivers highlighted" />
                  </div>
                  <div style={{ width: '100%', overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
                    <canvas ref={posRef} height={isMobile ? 200 : 250} style={{ display: 'block', width: isMobile ? '130%' : '100%', cursor: 'crosshair', minWidth: isMobile ? 600 : 'auto' }} onMouseMove={handleMouseMove} onMouseLeave={handleMouseLeave} />
                  </div>
                </Card>
              </div>
              {posTip && (
                <TooltipCard anchorRef={posCardRef} canvasOffsetX={posTipXY.x} canvasOffsetY={posTipXY.y + 46}>
                  <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.5)', fontFamily: 'monospace', fontWeight: 700, letterSpacing: '0.08em', marginBottom: '8px' }}>LAP {posTip.lap}</div>
                  {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                  {posTip.entries.map((e: any) => (
                    <div key={e.abbr} style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                      <div style={{ width: '3px', height: '24px', borderRadius: '2px', background: e.colour, flexShrink: 0 }} />
                      <div>
                        <div style={{ fontSize: '10px', color: e.colour, fontFamily: 'monospace', fontWeight: 700 }}>{e.abbr}</div>
                        <div style={{ fontSize: '15px', fontFamily: 'monospace', color: '#FFFFFF', fontWeight: 700, lineHeight: 1.1 }}>{e.position !== null ? `P${e.position}` : '—'}</div>
                      </div>
                    </div>
                  ))}
                </TooltipCard>
              )}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
              {overallFastest && (
                <Card style={{ padding: '18px 20px' }}>
                  <SectionTitle title="Fastest Lap" subtitle="Session benchmark" />
                  <div style={{ marginTop: '14px', padding: '18px', borderRadius: '20px', background: 'linear-gradient(180deg, #16243D 0%, #101A2D 100%)', color: '#fff', boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
                      <div>
                        <div style={{ fontSize: '12px', fontFamily: 'monospace', letterSpacing: '0.08em', color: '#' + overallFastest.team_colour }}>{overallFastest.abbreviation}</div>
                        <div style={{ fontSize: isMobile ? '28px' : '40px', lineHeight: 1.02, fontWeight: 900, letterSpacing: '-0.05em', marginTop: '8px' }}>{formatLapTime(overallFastest.lap_time_ms)}</div>
                      </div>
                      <div style={{ padding: '6px 10px', borderRadius: '999px', background: 'rgba(255,255,255,0.1)', fontSize: '11px', fontWeight: 700, color: '#B7C4DD' }}>LAP {overallFastest.lap_number}</div>
                    </div>
                    <div style={{ display: 'flex', gap: '14px', marginTop: '14px', flexWrap: 'wrap', fontSize: '11px', color: '#B7C4DD' }}>
                      <span>{overallFastest.team_name}</span>
                      {overallFastest.compound && <span style={{ color: COMPOUND_COLOUR[overallFastest.compound] ?? '#B7C4DD' }}>● {overallFastest.compound}</span>}
                      {overallFastest.position_on_lap !== null && <span>P{overallFastest.position_on_lap} at the time</span>}
                    </div>
                  </div>
                </Card>
              )}

              {top5Fastest.length > 0 && (
                <Card style={{ padding: '18px 20px' }}>
                  <SectionTitle title="Top 5 Laps" subtitle="Fastest non-pit laps in the session" />
                  <div style={{ marginTop: '14px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {top5Fastest.map((fl, i) => {
                      const colour = '#' + fl.team_colour
                      return (
                        <div key={fl.driver_number + '-' + fl.lap_number} style={{ display: 'grid', gridTemplateColumns: '26px 44px 1fr auto', gap: '10px', alignItems: 'center', padding: '12px 14px', background: i === 0 ? '#FFF4F5' : '#F8FBFF', border: `1px solid ${i === 0 ? '#F3D2D8' : BORDER}`, borderRadius: '14px' }}>
                          <span style={{ fontSize: '11px', fontFamily: 'monospace', color: TEXT_DIM }}>P{i + 1}</span>
                          <span style={{ fontSize: '12px', fontFamily: 'monospace', color: colour, fontWeight: 800 }}>{fl.abbreviation}</span>
                          <div style={{ fontSize: '11px', color: TEXT_MID }}>
                            Lap {fl.lap_number}
                            {fl.compound ? <span style={{ marginLeft: '8px', color: COMPOUND_COLOUR[fl.compound] ?? TEXT_DIM }}>● {fl.compound}</span> : null}
                          </div>
                          <div style={{ textAlign: 'right' }}>
                            <div style={{ fontSize: '18px', fontFamily: 'monospace', color: i === 0 ? '#CC3648' : TEXT_DARK, fontWeight: 800 }}>{formatLapTime(fl.lap_time_ms)}</div>
                            {i > 0 && <div style={{ fontSize: '10px', fontFamily: 'monospace', color: '#CC3648' }}>+{(fl.gap_ms / 1000).toFixed(3)}s</div>}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </Card>
              )}

              {leaderboard.length > 0 && (
                <Card style={{ padding: '18px 20px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '12px' }}>
                    <SectionTitle title="Race Order" subtitle={hovLap ? `Lap ${hovLap}` : `Final classification · lap ${maxLap}`} />
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {leaderboard.map((d) => {
                      const colour = '#' + d.team_colour
                      const isSel = selected.includes(d.driver_number)
                      const isLeader = d.position === 1
                      return (
                        <div key={d.driver_number} style={{ display: 'grid', gridTemplateColumns: '24px 8px 36px 1fr auto', gap: '10px', alignItems: 'center', padding: '9px 10px', borderRadius: '12px', background: isSel ? `${colour}10` : '#FAFCFF', border: `1px solid ${isSel ? `${colour}30` : BORDER}` }}>
                          <span style={{ fontSize: '11px', fontFamily: 'monospace', color: isLeader ? '#C69214' : TEXT_DIM, fontWeight: 700, textAlign: 'right' }}>{d.position}</span>
                          <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: colour, display: 'inline-block' }} />
                          <span style={{ fontSize: '11px', fontFamily: 'monospace', color: isSel ? colour : TEXT_MID, fontWeight: 800 }}>{d.abbreviation}</span>
                          <div style={{ height: '5px', background: '#E7EEF8', borderRadius: '999px', overflow: 'hidden' }}>
                            {d.gap !== null && d.gap > 0 && <div style={{ width: `${Math.min(100, (d.gap / 60) * 100)}%`, height: '100%', background: colour, borderRadius: '999px' }} />}
                          </div>
                          <span style={{ fontSize: '10px', fontFamily: 'monospace', color: isLeader ? '#C69214' : TEXT_DIM, fontWeight: 700 }}>{isLeader ? 'LEADER' : d.gap !== null ? `+${d.gap.toFixed(1)}s` : '—'}</span>
                        </div>
                      )
                    })}
                  </div>
                </Card>
              )}
            </div>
          </div>

          {/* ── PIT STOP ANALYSIS ──────────────────────────────────── */}
          {selectedUndercut.length > 0 && (
            <Card style={{ padding: '18px 20px' }}>
              <SectionTitle title="Pit Stop Analysis" subtitle="Position before pit versus three laps after rejoining" />
              <div style={{ marginTop: '14px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {selectedUndercut.map((u, i) => {
                  const colour = teamColour(u.team_colour, u.team_name)
                  const vs = VERDICT_STYLE[u.verdict]
                  const compInCol  = COMPOUND_COLOUR[u.compound_in  ?? ''] ?? '#666'
                  const compOutCol = COMPOUND_COLOUR[u.compound_out ?? ''] ?? '#666'
                  const posGain = u.pos_gain ?? 0
                  return (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '12px 14px', background: '#F9FBFF', borderRadius: '14px', border: `1px solid ${BORDER}` }}>
                      <div style={{ width: '3px', height: '52px', borderRadius: '2px', background: colour, flexShrink: 0 }} />
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                          <span style={{ fontSize: '11px', fontFamily: 'monospace', color: colour, fontWeight: 700 }}>{u.abbreviation}</span>
                          <span style={{ fontSize: '9px', fontFamily: 'monospace', color: TEXT_DIM }}>Pit lap {u.pit_lap}</span>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginLeft: 'auto' }}>
                            <span style={{ fontSize: '9px', fontFamily: 'monospace', color: compInCol }}>● {u.compound_in?.slice(0,1) ?? '?'}</span>
                            <span style={{ fontSize: '9px', color: TEXT_DIM }}>→</span>
                            <span style={{ fontSize: '9px', fontFamily: 'monospace', color: compOutCol }}>● {u.compound_out?.slice(0,1) ?? '?'}</span>
                            {u.tyre_life_laps !== null && <span style={{ fontSize: '9px', color: TEXT_DIM, fontFamily: 'monospace' }}>({u.tyre_life_laps}L in)</span>}
                          </div>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <span style={{ fontSize: '13px', fontFamily: 'monospace', color: TEXT_MID }}>P{u.pos_before ?? '?'}</span>
                          <span style={{ fontSize: '10px', color: TEXT_DIM }}>→</span>
                          <span style={{ fontSize: '13px', fontFamily: 'monospace', color: TEXT_DARK, fontWeight: 700 }}>P{u.pos_after ?? '?'}</span>
                          {u.pos_before !== null && u.pos_after !== null && (
                            <span style={{ fontSize: '11px', fontFamily: 'monospace', color: posGain > 0 ? '#2CF4C5' : posGain < 0 ? '#E8002D' : '#71717A', fontWeight: 700 }}>
                              {posGain > 0 ? `+${posGain}` : posGain < 0 ? `${posGain}` : '±0'}
                            </span>
                          )}
                          <div style={{ marginLeft: 'auto', padding: '2px 8px', borderRadius: '4px', background: vs.bg, border: `1px solid ${vs.border}` }}>
                            <span style={{ fontSize: '9px', fontFamily: 'monospace', color: vs.text, fontWeight: 700 }}>{vs.label}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </Card>
          )}

          {/* ── STINT PACE ─────────────────────────────────────────── */}
          {selectedStints.length > 0 && (
            <Card style={{ padding: '18px 20px' }}>
              <SectionTitle title="Stint Pace" subtitle="Clean laps only · degradation shown as milliseconds lost per lap" />
              <div style={{ marginTop: '14px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {selectedStints.map((s, i) => {
                  const colour     = teamColour(s.team_colour, s.team_name)
                  const degVal     = parseFloat(s.deg_ms_per_lap)
                  const degColour  = degVal > 100 ? '#E8002D' : degVal > 30 ? '#FFD700' : '#2CF4C5'
                  const compColour = COMPOUND_COLOUR[s.compound] ?? '#666666'
                  return (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '12px 14px', background: '#F9FBFF', borderRadius: '14px', border: `1px solid ${BORDER}` }}>
                      <div style={{ width: '3px', height: '44px', borderRadius: '2px', background: colour, flexShrink: 0 }} />
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '5px' }}>
                          <span style={{ fontSize: '11px', fontFamily: 'monospace', color: colour, fontWeight: 700 }}>{s.abbreviation}</span>
                          <span style={{ fontSize: '10px', fontFamily: 'monospace', color: TEXT_DIM }}>Stint {s.stint}</span>
                          <span style={{ fontSize: '9px', padding: '1px 6px', borderRadius: '4px', background: compColour + '22', color: compColour, fontFamily: 'monospace', fontWeight: 700 }}>{s.compound}</span>
                          <span style={{ fontSize: '9px', color: TEXT_DIM, fontFamily: 'monospace', marginLeft: 'auto' }}>L{s.start_lap}–{s.end_lap} · {s.clean_laps} laps</span>
                        </div>
                        <div style={{ display: 'flex', gap: '20px', alignItems: 'baseline' }}>
                          <span style={{ fontSize: '15px', fontFamily: 'monospace', color: TEXT_DARK, fontWeight: 700 }}>{formatLapTime(parseFloat(s.avg_ms))}</span>
                          <span style={{ fontSize: '10px', fontFamily: 'monospace', color: degColour }}>{degVal >= 0 ? '+' : ''}{degVal.toFixed(0)} ms/lap</span>
                          <span style={{ fontSize: '9px', fontFamily: 'monospace', color: TEXT_DIM }}>best {formatLapTime(s.best_ms)}</span>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
