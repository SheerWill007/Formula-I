'use client'

import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { teamColour, formatLapTime } from '@/lib/utils'
import SectorCard from './SectorCard'
import PerformanceMatrix from './PerformanceMatrix'

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// ── Types ─────────────────────────────────────────────────────────────────────

type ScatterLap = {
  driver_number: number
  abbreviation: string
  team_name: string
  team_colour: string
  lap_number: number
  lap_time_ms: number
  compound: string | null
  tyre_life_laps: number | null
  is_outlier: boolean
  is_personal_best: boolean
}

type CompoundDeltaDriver = {
  driver_number: number
  abbreviation: string
  team_name: string
  team_colour: string
  overall_best_ms: number
  compounds: Record<string, { best_ms: number; gap_to_best_ms: number }>
}

type DegStint = {
  driver_number: number
  abbreviation: string
  team_name: string
  team_colour: string
  stint_num: number
  laps: { lap_in_stint: number; lap_time_ms: number; delta_ms: number; tyre_life_laps: number | null }[]
}

type DegVisibleStint = DegStint & {
  isPrimary: boolean
  strokeStyle: 'solid' | 'dashed'
}

type DegPoint = {
  x: number
  y: number
  stint: DegVisibleStint
  lap: DegStint['laps'][number]
}

type CompoundTeam = {
  team_name: string
  team_colour: string
  compounds: Record<string, { laps: number; best_ms: number | null }>
  drivers: {
    driver_number: number
    abbreviation: string
    compounds: Record<string, { laps: number; best_ms: number | null; avg_ms: number | null }>
  }[]
}

type SectorDriver = {
  driver_number: number
  abbreviation: string
  team_name: string
  team_colour: string
  phases: Record<string, { best_s1: number | null; best_s2: number | null; best_s3: number | null; laps: number }>
}

type DriverInfo = {
  driver_number: number
  abbreviation: string
  team_name: string | null
  team_colour: string | null
}

// ── Constants (Premium Dashboard Palette) ───────────────────────────────────

const CHART_BG = '#FFFFFF'
const TEXT_DIM = '#7D8BA2'
const TEXT_DARK = '#13233D'

const COMPOUND_COLOUR: Record<string, string> = {
  SOFT: '#E8002D', MEDIUM: '#FFD700', HARD: '#FFFFFF',
  INTER: '#39B54A', WET: '#0067FF',
}

const PAD = { top: 40, right: 30, bottom: 50, left: 80 }

// ── Helpers ───────────────────────────────────────────────────────────────────

function clearCanvas(canvas: HTMLCanvasElement, W: number, H: number) {
  const dpr = window.devicePixelRatio || 1
  canvas.width = W * dpr; canvas.height = H * dpr
  canvas.style.width = `${W}px`; canvas.style.height = `${H}px`
  const ctx = canvas.getContext('2d')!
  ctx.scale(dpr, dpr)
  ctx.fillStyle = CHART_BG; ctx.fillRect(0, 0, W, H)
  return ctx
}

function Tooltip({ x, y, children }: { x: number; y: number; children: React.ReactNode }) {
  return (
    <div style={{
      position: 'fixed', left: x, top: y, pointerEvents: 'none', zIndex: 9999,
      background: '#FFFFFFEE', border: '1px solid #D9E3EF', borderRadius: '14px',
      padding: '12px 16px', backdropFilter: 'blur(8px)', minWidth: '160px',
      boxShadow: '0 10px 40px rgba(0,0,0,0.1)'
    }}>
      {children}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function PracticeAnalysis({
  sessionKey,
  session,
  drivers: allDrivers,
}: {
  sessionKey: number
  session?: import('@/types/f1').Session | null
  drivers: DriverInfo[]
}) {
  const [selected, setSelected] = useState<number[]>([])
  const [scatter, setScatter] = useState<ScatterLap[]>([])
  const [compoundDelta, setCompoundDelta] = useState<CompoundDeltaDriver[]>([])
  const [tyreDeg, setTyreDeg] = useState<Record<string, DegStint[]>>({})
  const [compounds, setCompounds] = useState<CompoundTeam[]>([])
  const [sectors, setSectors] = useState<SectorDriver[]>([])
  const [loading, setLoading] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const [activeDegCmp, setActiveDegCmp] = useState<string>('HARD')
  const [scatterTip, setScatterTip] = useState<{ x: number; y: number; lap: ScatterLap; gapMs: number } | null>(null)
  const [degTip, setDegTip] = useState<{ x: number; y: number; stint: DegVisibleStint; lap: DegStint['laps'][number] } | null>(null)

  const scatterRef = useRef<HTMLCanvasElement | null>(null)
  const degRef = useRef<HTMLCanvasElement | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const degCanvasWrapRef = useRef<HTMLDivElement | null>(null)

  const scatterGeomRef = useRef<{
    laps: (ScatterLap & { gap_ms: number })[]
    xMin: number; xMax: number; yMax: number; W: number; H: number
  } | null>(null)
  const degGeomRef = useRef<{
    points: DegPoint[]
    xMax: number
    yMin: number
    yMax: number
    W: number
    H: number
  } | null>(null)

  // ── Init ──────────────────────────────────────────────────────────────────

  useEffect(() => {
    if (allDrivers.length >= 2 && selected.length === 0)
      setSelected([allDrivers[0].driver_number, allDrivers[1].driver_number])

    const handleResize = () => setIsMobile(window.innerWidth < 1024)
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allDrivers.length])

  // ── Fetch ─────────────────────────────────────────────────────────────────

  useEffect(() => {
    setLoading(true)
    Promise.all([
      fetch(`${BASE}/api/v1/sessions/${sessionKey}/analysis/fp-scatter`).then(r => r.json()),
      fetch(`${BASE}/api/v1/sessions/${sessionKey}/analysis/fp-compound-delta`).then(r => r.json()),
      fetch(`${BASE}/api/v1/sessions/${sessionKey}/analysis/fp-tyre-deg`).then(r => r.json()),
      fetch(`${BASE}/api/v1/sessions/${sessionKey}/analysis/fp-compounds`).then(r => r.json()),
      fetch(`${BASE}/api/v1/sessions/${sessionKey}/analysis/fp-sectors`).then(r => r.json()),
    ])
      .then(([sc, cd, td, cp, sec]) => {
        setScatter(Array.isArray(sc) ? sc : [])
        setCompoundDelta(Array.isArray(cd) ? cd : [])
        setTyreDeg(td && typeof td === 'object' ? td : {})
        setCompounds(Array.isArray(cp) ? cp : [])
        setSectors(Array.isArray(sec) ? sec : [])
        const firstCmp = Object.keys(td ?? {})[0]
        if (firstCmp) setActiveDegCmp(firstCmp)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [sessionKey])

  const toggleDriver = (dn: number) =>
    setSelected(prev =>
      prev.includes(dn) ? prev.filter(d => d !== dn) : prev.length < 6 ? [...prev, dn] : prev
    )

  // ── Stats Computation ────────────

  const selectedStats = useMemo(() => {
    if (!selected.length || !scatter.length) return null
    const target = selected[0]
    const driverLaps = scatter.filter(l => l.driver_number === target && !l.is_outlier)
    if (!driverLaps.length) return null

    const bestLap = Math.min(...driverLaps.map(l => l.lap_time_ms))
    const comparison = compoundDelta.find(d => d.driver_number === target)
    const sectorInfo = sectors.find(d => d.driver_number === target)

    // Rough theoretical best (sum of best phases)
    const phases = sectorInfo?.phases || {}
    const tBest = (phases['early']?.best_s1 || 0) + (phases['middle']?.best_s2 || 0) + (phases['late']?.best_s3 || 0)

    return {
      bestLap,
      theoBest: comparison?.overall_best_ms || tBest,
      s1: phases['middle']?.best_s1 || phases['early']?.best_s1 || 0,
      s2: phases['middle']?.best_s2 || phases['early']?.best_s2 || 0,
      s3: phases['middle']?.best_s3 || phases['early']?.best_s3 || 0,
    }
  }, [selected, scatter, compoundDelta, sectors])

  const activeDegStints = useMemo<DegVisibleStint[]>(() => {
    const selectedOrder = new Map(selected.map((driverNumber, index) => [driverNumber, index]))
    const stints = (tyreDeg[activeDegCmp] ?? []).filter(stint => selected.includes(stint.driver_number))

    const sorted = [...stints].sort((a, b) => {
      const driverOrder = (selectedOrder.get(a.driver_number) ?? 99) - (selectedOrder.get(b.driver_number) ?? 99)
      if (driverOrder !== 0) return driverOrder
      const lapDelta = b.laps.length - a.laps.length
      if (lapDelta !== 0) return lapDelta
      return a.stint_num - b.stint_num
    })

    const primaryAssigned = new Set<number>()
    return sorted.map(stint => {
      const isPrimary = !primaryAssigned.has(stint.driver_number)
      if (isPrimary) primaryAssigned.add(stint.driver_number)
      return {
        ...stint,
        isPrimary,
        strokeStyle: isPrimary ? 'solid' : 'dashed',
      }
    })
  }, [activeDegCmp, selected, tyreDeg])

  // ── Draw: Gap to Best (Scatter but styled as line if comparable) ───────────

  useEffect(() => {
    const canvas = scatterRef.current
    if (!canvas || !scatter.length) return
    const W = (containerRef.current?.clientWidth ?? 1200) * 0.65
    const H = 400
    const ctx = clearCanvas(canvas, W, H)
    const cW = W - PAD.left - PAD.right
    const cH = H - PAD.top - PAD.bottom

    const cleanLaps = scatter.filter(l => !l.is_outlier && l.lap_time_ms)
    if (!cleanLaps.length) return
    const sessionBest = Math.min(...cleanLaps.map(l => l.lap_time_ms))

    const visible = scatter
      .filter(l => selected.includes(l.driver_number) && !l.is_outlier)
      .map(l => ({ ...l, gap_ms: l.lap_time_ms - sessionBest }))
      .sort((a, b) => a.lap_number - b.lap_number)

    if (!visible.length) return

    const yMax = Math.min(Math.max(...visible.map(l => l.gap_ms)) + 500, 5000)
    const xMin = Math.min(...visible.map(l => l.lap_number))
    const xMax = Math.max(...visible.map(l => l.lap_number))

    scatterGeomRef.current = { laps: visible, xMin, xMax, yMax, W, H }

    const toX = (lap: number) => PAD.left + ((lap - xMin) / Math.max(xMax - xMin, 1)) * cW
    const toY = (gap: number) => PAD.top + (Math.min(gap, yMax) / yMax) * cH

    // Grid lines (horizontal)
    const gridVals = [0, 500, 1000, 2000, 3000].filter(g => g <= yMax)
    gridVals.forEach(g => {
      const y = toY(g)
      ctx.beginPath(); ctx.strokeStyle = g === 0 ? '#13233D33' : '#F0F4FA'; ctx.lineWidth = 1
      ctx.moveTo(PAD.left, y); ctx.lineTo(PAD.left + cW, y); ctx.stroke()
      ctx.fillStyle = TEXT_DIM; ctx.font = '500 10px Inter'; ctx.textAlign = 'right'
      ctx.fillText(g === 0 ? 'P1' : `+${(g / 1000).toFixed(1)}s`, PAD.left - 10, y + 3)
    })

    // Draw connecting lines for each driver
    selected.forEach((dn, i) => {
      const driverLaps = visible.filter(l => l.driver_number === dn)
      if (driverLaps.length < 2) return

      const colour = '#' + driverLaps[0].team_colour
      ctx.beginPath(); ctx.strokeStyle = colour; ctx.lineWidth = i === 0 ? 3 : 1.5
      if (i > 0) ctx.setLineDash([5, 5])
      else ctx.setLineDash([])

      driverLaps.forEach((l, idx) => {
        const x = toX(l.lap_number); const y = toY(l.gap_ms)
        if (idx === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
      })
      ctx.stroke()
      ctx.setLineDash([])

      // Area fill for target driver
      if (i === 0) {
        ctx.lineTo(toX(driverLaps[driverLaps.length - 1].lap_number), toY(0))
        ctx.lineTo(toX(driverLaps[0].lap_number), toY(0))
        ctx.closePath()
        const grad = ctx.createLinearGradient(0, toY(0), 0, toY(yMax))
        grad.addColorStop(0, colour + '20'); grad.addColorStop(1, colour + '00')
        ctx.fillStyle = grad; ctx.fill()
      }
    })

    // Dots
    visible.forEach(l => {
      const x = toX(l.lap_number); const y = toY(l.gap_ms)
      const col = COMPOUND_COLOUR[l.compound ?? ''] ?? '#555'
      const active = selected[0] === l.driver_number

      ctx.beginPath(); ctx.arc(x, y, active ? 5 : 4, 0, Math.PI * 2)
      ctx.fillStyle = col; ctx.fill()
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5; ctx.stroke()

      if (l.is_personal_best) {
        ctx.beginPath(); ctx.arc(x, y, 8, 0, Math.PI * 2)
        ctx.strokeStyle = col + '44'; ctx.lineWidth = 2; ctx.stroke()
      }
    })

  }, [scatter, selected])

  const handleScatterMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const geom = scatterGeomRef.current
    if (!geom) return
    const rect = e.currentTarget.getBoundingClientRect()
    const mx = e.clientX - rect.left; const my = e.clientY - rect.top
    let nearest: (ScatterLap & { gap_ms: number }) | null = null; let nearDist = 15
    geom.laps.forEach(l => {
      const x = (PAD.left + ((l.lap_number - geom.xMin) / Math.max(geom.xMax - geom.xMin, 1)) * (rect.width - PAD.left - PAD.right))
      const y = (PAD.top + (Math.min(l.gap_ms, geom.yMax) / geom.yMax) * (rect.height - PAD.top - PAD.bottom))
      const dist = Math.hypot(mx - x, my - y)
      if (dist < nearDist) { nearDist = dist; nearest = l }
    })
    if (nearest) {
      const n = nearest as (ScatterLap & { gap_ms: number })
      setScatterTip({ x: e.clientX + 16, y: e.clientY - 20, lap: n, gapMs: n.gap_ms })
    }
    else setScatterTip(null)
  }, [])

  // ── Draw: Tyre Regression (Normalized Stint Overlay) ──────────────────────

  useEffect(() => {
    const canvas = degRef.current
    if (!canvas) return
    const stints = activeDegStints
    const W = Math.max((degCanvasWrapRef.current?.clientWidth ?? 0) - 4, 320)
    const H = 260
    const ctx = clearCanvas(canvas, W, H)
    degGeomRef.current = null
    if (!stints.length) return

    const maxLapInStint = Math.max(...stints.flatMap(stint => stint.laps.map(lap => lap.lap_in_stint)))
    const allDeltas = stints.flatMap(s => s.laps.map(l => l.delta_ms))
    let yMin = Math.min(...allDeltas, 0)
    let yMax = Math.max(...allDeltas, 0)
    if (yMin === yMax) {
      yMin -= 200
      yMax += 200
    }

    const deltaPad = Math.max((yMax - yMin) * 0.12, 120)
    yMin -= deltaPad
    yMax += deltaPad

    const cW = W - PAD.left - PAD.right
    const cH = H - PAD.top - PAD.bottom
    const toX = (lapInStint: number) => PAD.left + (lapInStint / Math.max(maxLapInStint, 1)) * cW
    const toY = (delta: number) => PAD.top + ((yMax - delta) / Math.max(yMax - yMin, 1)) * cH

    const ticks = 5
    for (let idx = 0; idx <= ticks; idx += 1) {
      const ratio = idx / ticks
      const value = yMax - ratio * (yMax - yMin)
      const y = PAD.top + ratio * cH
      const isZero = Math.abs(value) < 25

      ctx.beginPath()
      ctx.strokeStyle = isZero ? '#13233D44' : '#EEF3F9'
      ctx.lineWidth = isZero ? 1.5 : 1
      ctx.moveTo(PAD.left, y)
      ctx.lineTo(PAD.left + cW, y)
      ctx.stroke()

      ctx.fillStyle = TEXT_DIM
      ctx.font = '500 10px Inter'
      ctx.textAlign = 'right'
      const labelValue = isZero ? 0 : value
      const sign = labelValue > 0 ? '+' : ''
      ctx.fillText(`${sign}${(labelValue / 1000).toFixed(2)}s`, PAD.left - 10, y + 3)
    }

    for (let lapIdx = 0; lapIdx <= maxLapInStint; lapIdx += 1) {
      const x = toX(lapIdx)
      ctx.beginPath()
      ctx.strokeStyle = lapIdx === 0 ? '#D8E2F0' : '#F4F7FB'
      ctx.lineWidth = 1
      ctx.moveTo(x, PAD.top)
      ctx.lineTo(x, PAD.top + cH)
      ctx.stroke()
    }

    const degPoints: DegPoint[] = []

    stints.forEach(stint => {
      const col = teamColour(stint.team_colour, stint.team_name)
      ctx.globalAlpha = stint.isPrimary ? 1 : 0.5
      ctx.beginPath()
      ctx.strokeStyle = col
      ctx.lineWidth = stint.isPrimary ? 3 : 2
      ctx.setLineDash(stint.strokeStyle === 'dashed' ? [7, 5] : [])

      stint.laps.forEach((lap, index) => {
        const x = toX(lap.lap_in_stint)
        const y = toY(lap.delta_ms)
        degPoints.push({ x, y, stint, lap })

        if (index === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      })
      ctx.stroke()
      ctx.setLineDash([])

      stint.laps.forEach((lap, index) => {
        const x = toX(lap.lap_in_stint)
        const y = toY(lap.delta_ms)

        ctx.beginPath()
        ctx.arc(x, y, stint.isPrimary ? 4.5 : 3.5, 0, Math.PI * 2)
        ctx.fillStyle = COMPOUND_COLOUR[activeDegCmp] ?? col
        ctx.fill()
        ctx.strokeStyle = col
        ctx.lineWidth = 1.5
        ctx.stroke()

        if (index === stint.laps.length - 1) {
          ctx.fillStyle = col
          ctx.font = '700 10px Inter'
          ctx.textAlign = 'left'
          ctx.fillText(
            `${stint.abbreviation} ${stint.isPrimary ? '' : `S${stint.stint_num}`}`.trim(),
            x + 8,
            y - 6,
          )
        }
      })
    })
    ctx.globalAlpha = 1

    for (let lapIdx = 0; lapIdx <= maxLapInStint; lapIdx += 1) {
      const x = toX(lapIdx)
      ctx.fillStyle = TEXT_DIM
      ctx.font = '500 10px Inter'
      ctx.textAlign = 'center'
      ctx.fillText(String(lapIdx + 1), x, H - PAD.bottom + 18)
    }

    ctx.fillStyle = TEXT_DIM
    ctx.font = '500 10px Inter'
    ctx.textAlign = 'left'
    ctx.fillText('DELTA TO FIRST CLEAN LAP', PAD.left, PAD.top - 12)
    ctx.textAlign = 'center'
    ctx.fillText('LAP IN STINT', PAD.left + cW / 2, H - 14)

    degGeomRef.current = { points: degPoints, xMax: maxLapInStint, yMin, yMax, W, H }
  }, [activeDegCmp, activeDegStints])

  const handleDegMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const geom = degGeomRef.current
    if (!geom) return
    const rect = e.currentTarget.getBoundingClientRect()
    const scaleX = rect.width / geom.W
    const scaleY = rect.height / geom.H
    const mx = (e.clientX - rect.left) / scaleX
    const my = (e.clientY - rect.top) / scaleY

    let nearest: DegPoint | null = null
    let nearestDistance = 16

    geom.points.forEach(point => {
      const distance = Math.hypot(mx - point.x, my - point.y)
      if (distance < nearestDistance) {
        nearestDistance = distance
        nearest = point
      }
    })

    if (!nearest) {
      setDegTip(null)
      return
    }

    const point = nearest as DegPoint
    setDegTip({
      x: e.clientX + 16,
      y: e.clientY - 20,
      stint: point.stint,
      lap: point.lap,
    })
  }, [])

  // ── Render ────────────────────────────────────────────────────────────────

  if (loading) return <div style={{ textAlign: 'center', padding: '100px', color: TEXT_DIM, fontFamily: 'Inter' }}>Initializing Dashboard...</div>

  return (
    <div ref={containerRef} style={{ background: '#F8F9FC', minHeight: '100vh', padding: isMobile ? '12px' : '24px', fontFamily: 'Inter, sans-serif' }}>

      {/* ── Dashboard Header ─────────────────────────────────── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '32px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
            <span style={{
              background: '#13233D', color: '#fff', fontSize: '10px', padding: '4px 10px',
              borderRadius: '6px', fontWeight: 700, letterSpacing: '0.05em'
            }}>
              {session?.session_type || 'FP'}
            </span>
            <span style={{ color: TEXT_DIM, fontSize: '13px', fontWeight: 500 }}>
              {session?.gp_name || 'Circuit Analysis'}
            </span>
            <span style={{ color: TEXT_DIM }}>•</span>
            <span style={{ color: TEXT_DIM, fontSize: '13px' }}>
              {session?.date_start ? new Date(session.date_start).toLocaleDateString() : 'Active Session'}
            </span>
          </div>
          <h1 style={{ fontSize: isMobile ? '32px' : '48px', fontWeight: 900, color: TEXT_DARK, margin: 0, letterSpacing: '-0.04em' }}>
            GAP ANALYSIS
          </h1>
        </div>
      </div>

      {/* ── Driver Filter ────────────────────────────────────── */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '24px', background: '#FFFFFF', padding: '12px 16px', borderRadius: '16px', border: '1px solid #D9E3EF', alignItems: 'center' }}>
        <span style={{ fontSize: '11px', fontWeight: 700, color: TEXT_DIM, marginRight: '10px' }}>DRIVERS</span>
        {allDrivers.map(d => {
          const isSel = selected.includes(d.driver_number)
          const color = teamColour(d.team_colour, d.team_name)
          return (
            <button key={d.driver_number} onClick={() => toggleDriver(d.driver_number)} style={{
              padding: '6px 14px', borderRadius: '10px', cursor: 'pointer', border: 'none',
              background: isSel ? `${color}15` : 'transparent', color: isSel ? color : TEXT_DIM,
              fontSize: '13px', fontWeight: 700, transition: '0.2s', display: 'flex', alignItems: 'center', gap: '6px'
            }}>
              <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: color }} />
              {d.abbreviation}
            </button>
          )
        })}
      </div>

      {/* ── Main Dashboard Grid ──────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 340px', gap: '24px', marginBottom: '24px' }}>

        {/* Left Col: Gap Analysis Chart */}
        <div style={{ background: '#fff', border: '1px solid #D9E3EF', borderRadius: '24px', padding: '24px', position: 'relative' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px' }}>
            <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 800, color: TEXT_DARK }}>Gap to Session Best</h3>
            <div style={{ display: 'flex', gap: '16px' }}>
              {selected.map((dn, i) => (
                <div key={dn} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#' + allDrivers.find(d => d.driver_number === dn)?.team_colour }} />
                  <span style={{ fontSize: '11px', fontWeight: 700, color: TEXT_DIM }}>{allDrivers.find(d => d.driver_number === dn)?.abbreviation} {i === 0 ? '(TARGET)' : '(REF)'}</span>
                </div>
              ))}
            </div>
          </div>
          <div style={{ width: '100%', overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
            <canvas ref={scatterRef} style={{ display: 'block', width: isMobile ? '130%' : '100%', height: isMobile ? '300px' : '400px', minWidth: isMobile ? 600 : 'auto' }} onMouseMove={handleScatterMove} onMouseLeave={() => setScatterTip(null)} />
          </div>
          {scatterTip && (
            <Tooltip x={scatterTip.x} y={scatterTip.y}>
              <div style={{ fontSize: '10px', color: TEXT_DIM, fontWeight: 700, marginBottom: '4px' }}>LAP {scatterTip.lap.lap_number}</div>
              <div style={{ fontSize: '16px', fontWeight: 900, color: TEXT_DARK }}>{formatLapTime(scatterTip.lap.lap_time_ms)}</div>
              <div style={{ fontSize: '12px', fontWeight: 700, color: scatterTip.gapMs < 10 ? '#10B981' : '#E8002D' }}>
                {scatterTip.gapMs < 10 ? 'SESSION BEST' : `+${(scatterTip.gapMs / 1000).toFixed(3)}s`}
              </div>
            </Tooltip>
          )}
        </div>

        {/* Right Col: Performance Matrix */}
        <PerformanceMatrix
          bestLap={selectedStats?.bestLap || '—'}
          theoBest={selectedStats?.theoBest || '—'}
          topSpeed={324} // Placeholder: usually in stats
          s1Best={selectedStats?.s1 || '—'}
          s2Best={selectedStats?.s2 || '—'}
          s3Best={selectedStats?.s3 || '—'}
          accentColor={selected.length ? teamColour(allDrivers.find(d => d.driver_number === selected[0])?.team_colour, '') : '#E8002D'}
        />
      </div>

      {/* ── Sub Grid ── */}
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)', gap: '24px', marginBottom: '24px' }}>
        <SectorCard label="SECTOR 1" time={selectedStats?.s1 || '—'} color="#10B981" delta={-150} />
        <SectorCard label="SECTOR 2" time={selectedStats?.s2 || '—'} color="#F59E0B" delta={40} />
        <SectorCard label="SECTOR 3" time={selectedStats?.s3 || '—'} color="#6E56CF" delta={210} />
      </div>

      {/* ── Bottom Grid ──────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1.2fr', gap: '24px' }}>

        {/* Strategy Analysis */}
        <div style={{ background: '#13233D', border: '1px solid #1A2E4B', borderRadius: '24px', padding: '24px', color: '#fff', boxShadow: '0 8px 32px rgba(19,35,61,0.2)' }}>
          <h3 style={{ margin: 0, marginBottom: '20px', fontSize: '16px', fontWeight: 800, color: '#D9E3EF' }}>Compound Strategy Analysis</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {compounds.slice(0, 4).map(team => {
              const mainCmp = Object.keys(team.compounds).sort((a, b) => team.compounds[b].laps - team.compounds[a].laps)[0]
              const data = team.compounds[mainCmp]
              return (
                <div key={team.team_name} style={{ display: 'flex', alignItems: 'center', gap: '16px', background: 'rgba(255,255,255,0.03)', padding: '12px', borderRadius: '12px' }}>
                  <div style={{ width: '4px', height: '32px', borderRadius: '2px', background: '#' + team.team_colour }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                      <span style={{ fontSize: '13px', fontWeight: 700 }}>{team.team_name.split(' ')[0]} ({mainCmp})</span>
                      <span style={{ fontSize: '11px', color: '#7D8BA2' }}>{data?.laps || 0} Laps • Best {formatLapTime(data?.best_ms)}</span>
                    </div>
                    <div style={{ height: '8px', background: 'rgba(255,255,255,0.1)', borderRadius: '4px', overflow: 'hidden' }}>
                      <div style={{ width: `${Math.min((data?.laps || 0) * 4, 100)}%`, height: '100%', background: '#' + team.team_colour }} />
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Tyre Degradation Chart */}
        <div style={{ background: '#fff', border: '1px solid #D9E3EF', borderRadius: '24px', padding: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px' }}>
            <div>
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 800, color: TEXT_DARK }}>Tyre Degradation Analysis</h3>
              <div style={{ marginTop: '6px', fontSize: '11px', color: TEXT_DIM, fontWeight: 600 }}>
                Normalized to the first clean lap of each stint. Solid lines are each driver&apos;s primary long run; dashed lines show extra stints.
              </div>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              {Object.keys(tyreDeg).sort().map(c => (
                <button key={c} onClick={() => setActiveDegCmp(c)} style={{
                  padding: '4px 12px', borderRadius: '20px', border: '1px solid #D9E3EF',
                  background: activeDegCmp === c ? '#13233D' : '#fff', color: activeDegCmp === c ? '#fff' : TEXT_DIM,
                  fontSize: '11px', fontWeight: 700, cursor: 'pointer'
                }}>{c}</button>
              ))}
            </div>
          </div>
          <div ref={degCanvasWrapRef} style={{ position: 'relative', width: '100%' }}>
            {activeDegStints.length ? (
              <canvas
                ref={degRef}
                style={{ display: 'block', width: '100%', height: '260px' }}
                onMouseMove={handleDegMove}
                onMouseLeave={() => setDegTip(null)}
              />
            ) : (
              <div style={{ height: '260px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: TEXT_DIM, fontSize: '13px', fontWeight: 600 }}>
                No comparable long-run stints available for this compound and driver selection.
              </div>
            )}
          </div>
          {degTip && (
            <Tooltip x={degTip.x} y={degTip.y}>
              <div style={{ fontSize: '10px', color: TEXT_DIM, fontWeight: 700, marginBottom: '4px' }}>
                {degTip.stint.abbreviation} · STINT {degTip.stint.stint_num}
              </div>
              <div style={{ fontSize: '16px', fontWeight: 900, color: TEXT_DARK }}>
                {degTip.lap.delta_ms >= 0 ? '+' : ''}{(degTip.lap.delta_ms / 1000).toFixed(3)}s
              </div>
              <div style={{ fontSize: '12px', color: TEXT_DIM, fontWeight: 700 }}>
                Lap {degTip.lap.lap_in_stint + 1} of stint
              </div>
              <div style={{ fontSize: '12px', color: TEXT_DIM }}>
                Actual pace {formatLapTime(degTip.lap.lap_time_ms)}
              </div>
              <div style={{ fontSize: '12px', color: TEXT_DIM }}>
                Tyre life {degTip.lap.tyre_life_laps ?? '—'}
              </div>
            </Tooltip>
          )}
        </div>
      </div>

    </div>
  )
}
