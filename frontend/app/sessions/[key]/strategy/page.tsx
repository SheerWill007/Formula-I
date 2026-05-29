'use client'
import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { strategyApi } from '@/lib/api'
import { api } from '@/lib/api'
import { teamColour, COMPOUND_COLOURS, COMPOUND_LABEL } from '@/lib/utils'
import type { Stint, RacePosition, Session } from '@/types/f1'
import LoadingSpinner from '@/components/ui/LoadingSpinner'
import Link from 'next/link'
import { ArrowLeft, Zap } from 'lucide-react'

const TOTAL_LAPS = 52   // will be derived from data

export default function StrategyPage() {
  const { key } = useParams<{ key: string }>()
  const sessionKey = parseInt(key)

  const [session,   setSession]   = useState<Session | null>(null)
  const [stints,    setStints]    = useState<Stint[]>([])
  const [order,     setOrder]     = useState<RacePosition[]>([])
  const [loading,   setLoading]   = useState(true)
  const [insight,   setInsight]   = useState<string>('')

  useEffect(() => {
    Promise.all([
      api.sessions.get(sessionKey),
      strategyApi.stints(sessionKey),
      strategyApi.raceOrder(sessionKey),
    ]).then(([sess, s, o]) => {
      setSession(sess)
      setStints(s)
      setOrder(o)
      setInsight(generateInsight(s, o))
    }).finally(() => setLoading(false))
  }, [sessionKey])

  if (loading) return <LoadingSpinner text="Loading strategy data..." />

  // Derive total laps from data
  const maxLap = stints.reduce((m, s) => Math.max(m, s.lap_end), 0) || TOTAL_LAPS

  // Group stints by driver
  const stintsByDriver: Record<number, Stint[]> = {}
  for (const stint of stints) {
    if (!stintsByDriver[stint.driver_number]) stintsByDriver[stint.driver_number] = []
    stintsByDriver[stint.driver_number].push(stint)
  }

  // Order drivers by race finish
  const orderedDrivers = order.length > 0
    ? order.map(o => o.driver_number).filter(n => stintsByDriver[n])
    : Object.keys(stintsByDriver).map(Number)

  // Lap axis ticks
  const ticks = [0, 10, 20, 30, 40, 50, maxLap].filter((v, i, a) => a.indexOf(v) === i && v <= maxLap)

  const compounds = ['SOFT', 'MEDIUM', 'HARD', 'INTER', 'WET']
    .filter(c => stints.some(s => s.compound === c))

  return (
    <div className="px-4 py-4 max-w-4xl mx-auto">

      {/* Header */}
      <Link href={`/sessions/${sessionKey}`}
        className="flex items-center gap-1.5 text-zinc-500 text-sm mb-4 hover:text-white transition-colors">
        <ArrowLeft size={14} /> Back to Session
      </Link>

      <div className="mb-5">
        <h1 className="font-display font-bold text-2xl text-white">Tyre Strategy</h1>
        <p className="text-zinc-500 text-sm">
          Race stints by compound · {session?.year} {session?.gp_name}
        </p>
      </div>

      {orderedDrivers.length === 0 ? (
        <div className="text-center py-16 text-zinc-600 text-sm">
          No race strategy data available for this session.
          <br />
          <span className="text-zinc-700">This may be a qualifying session — strategy is only available for races.</span>
        </div>
      ) : (
        <>
          {/* Strategy diagram */}
          <div className="bg-surface border border-border rounded-xl overflow-hidden mb-4">
            <div className="p-4 border-b border-border flex items-center justify-between">
              <h2 className="font-semibold text-white text-sm">Race Stints</h2>
              <span className="text-zinc-600 text-xs font-mono">{maxLap} laps</span>
            </div>

            <div className="p-4">
              {/* Stint rows */}
              <div className="space-y-1.5 mb-3">
                {orderedDrivers.map((driverNum, idx) => {
                  const driverStints = stintsByDriver[driverNum] || []
                  const pos = order.find(o => o.driver_number === driverNum)
                  // eslint-disable-next-line @typescript-eslint/no-unused-vars
                  const colour = teamColour(driverStints[0]?.team_colour)

                  return (
                    <div key={driverNum} className="flex items-center gap-2">
                      {/* Driver label */}
                      <div className="w-12 flex-shrink-0 text-right">
                        <div className="font-mono text-xs font-bold text-white">
                          {driverStints[0]?.abbreviation}
                        </div>
                        <div className="font-mono text-[9px] text-zinc-600">
                          P{pos?.position ?? idx + 1}
                        </div>
                      </div>

                      {/* Timeline */}
                      <div className="flex-1 relative h-8 bg-surface2 rounded overflow-hidden">
                        {driverStints.map((stint, i) => {
                          const left  = ((stint.lap_start - 1) / maxLap) * 100
                          const width = (stint.lap_count / maxLap) * 100
                          const bg    = COMPOUND_COLOURS[stint.compound ?? ''] ?? '#666'
                          const label = COMPOUND_LABEL[stint.compound ?? ''] ?? '?'
                          const isDark = stint.compound === 'MEDIUM' || stint.compound === 'HARD'

                          return (
                            <div
                              key={i}
                              className="absolute top-0 h-full flex items-center justify-center text-xs font-bold transition-all"
                              style={{
                                left:            `${left}%`,
                                width:           `${width}%`,
                                background:      bg,
                                color:           isDark ? '#000' : '#fff',
                                borderRight:     i < driverStints.length - 1 ? '2px solid #0A0A0A' : 'none',
                              }}
                              title={`${stint.compound} — Laps ${stint.lap_start}–${stint.lap_end} (${stint.lap_count} laps)`}
                            >
                              {width > 8 ? label : ''}
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* Lap axis */}
              <div className="flex ml-14 relative h-4">
                {ticks.map(tick => (
                  <div
                    key={tick}
                    className="absolute text-[9px] font-mono text-zinc-600 -translate-x-1/2"
                    style={{ left: `${(tick / maxLap) * 100}%` }}
                  >
                    L{tick}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Legend */}
          <div className="flex items-center gap-4 mb-4 px-1">
            {compounds.map(c => (
              <div key={c} className="flex items-center gap-1.5">
                <div
                  className="w-3 h-3 rounded-sm"
                  style={{ background: COMPOUND_COLOURS[c] }}
                />
                <span className="text-xs text-zinc-400">{c.charAt(0) + c.slice(1).toLowerCase()}</span>
              </div>
            ))}
          </div>

          {/* AI Strategy Insight */}
          {insight && (
            <div className="bg-surface border border-border rounded-xl p-4 flex gap-3">
              <div className="w-8 h-8 rounded-lg bg-teal/10 flex items-center justify-center flex-shrink-0">
                <Zap size={14} className="text-teal" />
              </div>
              <div>
                <div className="text-sm font-semibold text-white mb-1">Strategy Insight</div>
                <p className="text-zinc-400 text-sm leading-relaxed">{insight}</p>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

/** Generate a simple insight from stint data */
function generateInsight(stints: Stint[], order: RacePosition[]): string {
  if (stints.length === 0) return ''

  const byDriver: Record<number, Stint[]> = {}
  for (const s of stints) {
    if (!byDriver[s.driver_number]) byDriver[s.driver_number] = []
    byDriver[s.driver_number].push(s)
  }

  const winner = order[0]
  if (!winner) return ''

  const winnerStints = byDriver[winner.driver_number] ?? []
  const stopCount = winnerStints.length - 1

  // Find one-stoppers
  const oneStoppers = Object.entries(byDriver)
    .filter(([, s]) => s.length === 2)
    .map(([, s]) => s[0].abbreviation)

  const winnerAbbr = winner.abbreviation
  const winnerStrategy = winnerStints.map(s => COMPOUND_LABEL[s.compound ?? ''] ?? '?').join('→')

  let insight = `${winnerAbbr} won on a ${stopCount}-stop strategy (${winnerStrategy})`

  if (oneStoppers.length > 0 && !oneStoppers.includes(winnerAbbr)) {
    insight += `. ${oneStoppers.slice(0, 2).join(' and ')} attempted a bold one-stop, extending their second stint to cover track position.`
  } else {
    insight += `, managing tyre degradation through careful compound selection.`
  }

  return insight
}
