'use client'
import { useEffect, useState } from 'react'
import { telemetryApi } from '@/lib/api'
import { teamColour } from '@/lib/utils'
import type { TelemetrySample } from '@/types/f1'
import LoadingSpinner from '@/components/ui/LoadingSpinner'

interface DriverTrace {
  driver_number: number
  abbreviation:  string
  team_colour:   string | null
  samples:       TelemetrySample[]
}

interface Props {
  sessionKey: number
  drivers:    { driver_number: number; abbreviation: string; team_colour: string | null }[]
}

export default function SpeedTrace({ sessionKey, drivers }: Props) {
  const [traces,  setTraces]  = useState<DriverTrace[]>([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState<string | null>(null)

  useEffect(() => {
    if (drivers.length === 0) return
    setLoading(true)

    const nums = drivers.map(d => d.driver_number)
    telemetryApi.compare(sessionKey, nums)
      .then(data => {
        const result: DriverTrace[] = []
        for (const d of drivers) {
          const entry = data[String(d.driver_number)]
          if (entry) {
            result.push({ ...d, samples: entry.samples })
          }
        }
        setTraces(result)
      })
      .catch(() => setError('No telemetry loaded for this session yet'))
      .finally(() => setLoading(false))
  }, [sessionKey, drivers])

  if (loading) return <LoadingSpinner text="Loading telemetry..." />
  if (error)   return (
    <div className="text-center py-8 text-zinc-600 text-sm">{error}</div>
  )
  if (traces.length === 0) return null

  // Build SVG path from speed samples
  const W = 600
  const H = 120
  const PAD = 8

  const maxSpeed = Math.max(...traces.flatMap(t => t.samples.map(s => s.speed_kmh ?? 0)))
  const minSpeed = Math.min(...traces.flatMap(t => t.samples.map(s => s.speed_kmh ?? maxSpeed)))

  function buildPath(samples: TelemetrySample[]): string {
    if (samples.length === 0) return ''
    return samples.map((s, i) => {
      const x = PAD + (i / (samples.length - 1)) * (W - PAD * 2)
      const y = H - PAD - ((( s.speed_kmh ?? minSpeed) - minSpeed) / (maxSpeed - minSpeed || 1)) * (H - PAD * 2)
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
    }).join(' ')
  }

  // Speed labels on y axis
  const yLabels = [minSpeed, (minSpeed + maxSpeed) / 2, maxSpeed].map(Math.round)

  return (
    <div className="bg-surface border border-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="font-semibold text-white text-sm">Speed Trace</h3>
          <p className="text-zinc-600 text-xs">Fastest lap comparison</p>
        </div>
        {/* Legend */}
        <div className="flex items-center gap-3">
          {traces.map(t => (
            <div key={t.driver_number} className="flex items-center gap-1.5">
              <div className="w-6 h-0.5 rounded" style={{ background: teamColour(t.team_colour) }} />
              <span className="font-mono text-xs text-zinc-400">{t.abbreviation}</span>
            </div>
          ))}
        </div>
      </div>

      {/* SVG Chart */}
      <div className="relative overflow-x-auto">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full"
          style={{ minWidth: '280px', height: '120px' }}
        >
          {/* Grid lines */}
          {[0.25, 0.5, 0.75].map(pct => (
            <line
              key={pct}
              x1={PAD} y1={H - PAD - pct * (H - PAD * 2)}
              x2={W - PAD} y2={H - PAD - pct * (H - PAD * 2)}
              stroke="#2A2A2A" strokeWidth="1"
            />
          ))}

          {/* Speed traces */}
          {traces.map(t => (
            <path
              key={t.driver_number}
              d={buildPath(t.samples)}
              fill="none"
              stroke={teamColour(t.team_colour)}
              strokeWidth="1.5"
              strokeLinejoin="round"
              strokeLinecap="round"
              opacity={0.9}
            />
          ))}


        </svg>

        {/* Y axis labels */}
        <div className="absolute left-0 top-0 h-full flex flex-col justify-between py-2 pointer-events-none">
          {[...yLabels].reverse().map(v => (
            <span key={v} className="font-mono text-[9px] text-zinc-700">{v}</span>
          ))}
        </div>

        {/* X axis label */}
        <div className="text-center text-[9px] font-mono text-zinc-700 mt-1">
          Distance through lap →
        </div>
      </div>

      {/* Throttle trace */}
      <div className="mt-3 border-t border-border pt-3">
        <div className="text-[9px] font-mono text-zinc-600 uppercase tracking-widest mb-1.5">
          Throttle %
        </div>
        <svg viewBox={`0 0 ${W} 40`} className="w-full" style={{ height: '40px' }}>
          {traces.map(t => {
            const path = t.samples.map((s, i) => {
              const x = PAD + (i / (t.samples.length - 1)) * (W - PAD * 2)
              const y = 40 - PAD - ((s.throttle_pct ?? 0) / 100) * (40 - PAD * 2)
              return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
            }).join(' ')
            return (
              <path key={t.driver_number} d={path} fill="none"
                stroke={teamColour(t.team_colour)} strokeWidth="1" opacity={0.7} />
            )
          })}
        </svg>
      </div>
    </div>
  )
}
