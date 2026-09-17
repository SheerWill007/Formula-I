'use client'
import { useEffect, useState } from 'react'
import { telemetryApi } from '@/lib/api'
import { teamColour } from '@/lib/utils'
import type { DriverTelemetryStats } from '@/types/f1'

// ── Design tokens (light theme) ───────────────────────────────────────────────
const C = {
  bg: '#EEF3F9',
  surface: '#F8FBFE',
  border: '#D9E3EF',
  borderMid: '#C5D2E3',
  textDim: '#7D8BA2',
  textMid: '#56657C',
  textSub: '#293A52',
  textBright: '#13233D',
  red: '#E8002D',
  green: '#10B981',
  purple: '#6E56CF',
  gold: '#C98A27',
  rankBest: '#10B981',
  rankMid: '#64748B',
  rankWorst: '#E8002D',
} as const

// ── Types ─────────────────────────────────────────────────────────────────────
interface Props {
  sessionKey: number
  drivers: number[]
  driverMap: Record<number, { abbreviation: string; team_colour: string | null }>
}

function rankColour(val: number | null, vals: (number | null)[], higherIsBetter = false): string {
  if (val === null) return C.textDim
  const valid = vals.filter((v): v is number => v !== null)
  if (valid.length < 2) return C.textMid
  const best = higherIsBetter ? Math.max(...valid) : Math.min(...valid)
  const worst = higherIsBetter ? Math.min(...valid) : Math.max(...valid)
  if (val === best) return C.rankBest
  if (val === worst) return C.rankWorst
  return C.rankMid
}





// ── Corner detail ─────────────────────────────────────────────────────────────
function CornerDetail({ cornerNum, stats }: { cornerNum: number; stats: DriverTelemetryStats[] }) {
  const corners = stats
    .map(s => ({ ...s, corner: s.corners?.find(c => c.corner_num === cornerNum) ?? null }))
    .filter(s => s.corner !== null)
  if (!corners.length) return null

  const allEntry = corners.map(s => s.corner!.entry_speed_kmh)
  const allApex = corners.map(s => s.corner!.min_speed_kmh)
  const allExit = corners.map(s => s.corner!.exit_speed_kmh)
  const allBrake = corners.map(s => {
    const c = s.corner!
    return c.brake_point_m ? c.distance_m - c.brake_point_m : null
  })

  const cols = [
    { label: 'Entry', all: allEntry, field: (c: typeof corners[0]['corner']) => c!.entry_speed_kmh, unit: '' },
    { label: 'Apex', all: allApex, field: (c: typeof corners[0]['corner']) => c!.min_speed_kmh, unit: '', bold: true },
    { label: 'Exit', all: allExit, field: (c: typeof corners[0]['corner']) => c!.exit_speed_kmh, unit: '' },
    { label: 'Brake Dist', all: allBrake, field: (c: typeof corners[0]['corner']) => c!.brake_point_m ? c!.distance_m - c!.brake_point_m : null, unit: 'm' },
  ]

  return (
    <div style={{ borderTop: `1px solid ${C.border}`, padding: '16px 20px', background: C.bg }}>
      <div style={{ fontSize: 10, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 600, color: C.textDim, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 12 }}>
        Corner {cornerNum} · {corners[0].corner!.distance_m.toFixed(0)}m
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '60px repeat(4, 1fr)', gap: 8, marginBottom: 8 }}>
        <div />
        {cols.map(c => (
          <div key={c.label} style={{ fontSize: 9, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 600, color: C.textDim, textAlign: 'center', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            {c.label}
          </div>
        ))}
      </div>
      {corners.map(s => {
        const colour = teamColour(s.team_colour)
        return (
          <div key={s.driver_number} style={{ display: 'grid', gridTemplateColumns: '60px repeat(4, 1fr)', gap: 8, alignItems: 'center', marginBottom: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 3, height: 14, borderRadius: 2, background: colour }} />
              <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, fontWeight: 700, color: C.textBright }}>{s.abbreviation}</span>
            </div>
            {cols.map((col, ci) => {
              const val = col.field(s.corner)
              const rc = rankColour(val, col.all as (number | null)[], true)
              return (
                <div key={ci} style={{ textAlign: 'center', fontFamily: 'JetBrains Mono, monospace', fontSize: col.bold ? 13 : 11, fontWeight: col.bold ? 700 : 400, color: rc }}>
                  {val !== null ? `${typeof val === 'number' ? val.toFixed(col.unit === 'm' ? 0 : 0) : val}${col.unit}` : '—'}
                </div>
              )
            })}
          </div>
        )
      })}
    </div>
  )
}

// ── Corner table ──────────────────────────────────────────────────────────────
function CornerTable({ stats }: { stats: DriverTelemetryStats[] }) {
  const [selected, setSelected] = useState<number | null>(null)
  const maxCorners = Math.max(...stats.map(s => s.corners?.length ?? 0))
  if (maxCorners === 0) return null
  const cornerNums = Array.from({ length: maxCorners }, (_, i) => i + 1)

  return (
    <div style={{ background: `linear-gradient(180deg, ${C.surface} 0%, #F4F8FC 100%)`, border: `1px solid ${C.border}`, borderRadius: 18, overflow: 'hidden', boxShadow: '0 12px 28px rgba(37,54,82,0.07), inset 0 1px 0 rgba(255,255,255,0.78)' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 20px', borderBottom: `1px solid ${C.border}` }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 700, color: C.textBright, fontFamily: 'Inter, sans-serif' }}>Corner Analysis</div>
          <div style={{ fontSize: 11, color: C.textMid, marginTop: 2, fontFamily: 'Inter, sans-serif' }}>Apex speed · click a corner for detail</div>
        </div>
        <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
          {[{ c: C.rankBest, l: 'Fastest' }, { c: C.rankMid, l: 'Middle' }, { c: C.rankWorst, l: 'Slowest' }].map(({ c, l }) => (
            <div key={l} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <div style={{ width: 7, height: 7, borderRadius: '50%', background: c }} />
              <span style={{ fontSize: 10, color: C.textMid, fontFamily: 'Inter, sans-serif' }}>{l}</span>
            </div>
          ))}
        </div>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${C.border}` }}>
              <th style={{ textAlign: 'left', padding: '8px 20px', fontFamily: 'Space Grotesk, sans-serif', fontSize: 10, color: C.textDim, fontWeight: 600, letterSpacing: '0.1em', width: 64 }}>DRIVER</th>
              {cornerNums.map(n => (
                <th key={n} onClick={() => setSelected(selected === n ? null : n)} style={{
                  textAlign: 'center', padding: '8px 6px',
                  fontFamily: 'Space Grotesk, sans-serif', fontSize: 10, fontWeight: 600,
                  cursor: 'pointer', letterSpacing: '0.08em',
                  color: selected === n ? C.textBright : C.textDim,
                  background: selected === n ? C.bg : 'transparent',
                  transition: 'all 0.12s', userSelect: 'none',
                }}>C{n}</th>
              ))}
              <th style={{ textAlign: 'right', padding: '8px 20px', fontFamily: 'Space Grotesk, sans-serif', fontSize: 10, color: C.textDim, fontWeight: 600 }}>TRAP</th>
              <th style={{ textAlign: 'right', padding: '8px 20px', fontFamily: 'Space Grotesk, sans-serif', fontSize: 10, color: C.textDim, fontWeight: 600 }}>TOP</th>
            </tr>
          </thead>
          <tbody>
            {stats.map((s, si) => {
              const colour = teamColour(s.team_colour)
              return (
                <tr key={s.driver_number} style={{ borderBottom: si < stats.length - 1 ? `1px solid ${C.border}` : 'none' }}>
                  <td style={{ padding: '10px 20px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                      <div style={{ width: 3, height: 16, borderRadius: 2, background: colour, flexShrink: 0 }} />
                      <span style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: C.textBright, fontSize: 12 }}>{s.abbreviation}</span>
                    </div>
                  </td>
                  {cornerNums.map(n => {
                    const corner = s.corners?.find(c => c.corner_num === n)
                    const allSpeeds = stats.map(st => st.corners?.find(c => c.corner_num === n)?.min_speed_kmh ?? null)
                    const col = corner ? rankColour(corner.min_speed_kmh, allSpeeds, true) : C.textDim
                    return (
                      <td key={n} style={{ textAlign: 'center', padding: '10px 6px', background: selected === n ? C.bg : 'transparent' }}>
                        {corner
                          ? <span style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, fontSize: 12, color: col }}>{corner.min_speed_kmh}</span>
                          : <span style={{ color: C.border }}>—</span>
                        }
                      </td>
                    )
                  })}
                  <td style={{ textAlign: 'right', padding: '10px 20px', fontFamily: 'JetBrains Mono, monospace', color: C.textMid, fontSize: 11 }}>{s.speed_trap_1_kmh ?? '—'}</td>
                  <td style={{ textAlign: 'right', padding: '10px 20px', fontFamily: 'JetBrains Mono, monospace', color: C.textBright, fontWeight: 700, fontSize: 12 }}>{s.max_speed_kmh ?? '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {selected !== null && <CornerDetail cornerNum={selected} stats={stats} />}
    </div>
  )
}

// ── Main export ───────────────────────────────────────────────────────────────
export default function CornerAnalysis({ sessionKey, drivers }: Omit<Props, 'driverMap'>) {
  const [stats, setStats] = useState<DriverTelemetryStats[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!drivers.length) return
    setLoading(true)
    telemetryApi.stats(sessionKey, drivers)
      .then(setStats)
      .catch(() => setStats([]))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionKey, drivers.join(',')])

  if (loading) return (
    <div style={{ textAlign: 'center', padding: 48, color: C.textDim, fontFamily: 'Inter, sans-serif', fontSize: 13 }}>
      Computing corner analysis...
    </div>
  )
  if (!stats.length) return null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 8 }}>
      {/* Divider */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ height: 1, flex: 1, background: C.border }} />
        <span style={{ fontSize: 10, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 600, color: C.textDim, letterSpacing: '0.12em', textTransform: 'uppercase' }}>Corner Analysis</span>
        <div style={{ height: 1, flex: 1, background: C.border }} />
      </div>

      <CornerTable stats={stats} />
    </div>
  )
}
