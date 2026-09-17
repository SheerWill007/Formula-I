'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { raceIntelligenceApi, api } from '@/lib/api'
import { teamColour, COMPOUND_COLOURS, COMPOUND_LABEL, formatLapTime, sessionTypeLabel } from '@/lib/utils'
import type { RaceIntelligenceResponse, DriverState, StintSummary, BattleGap, DriverScore, RaceInsight } from '@/types/f1'
import LoadingSpinner from '@/components/ui/LoadingSpinner'
import Link from 'next/link'
import { ArrowLeft, Zap, Award, Users, Flag, TrendingUp, GripVertical } from 'lucide-react'

const C = {
  bg: '#F5F7FB',
  surface: '#FFFFFF',
  surfaceAlt: '#F9FAFB',
  border: '#E2E8F0',
  textDim: '#64748B',
  textMid: '#475569',
  textSub: '#1E293B',
  textBright: '#0F172A',
  red: '#E8002D',
  green: '#10B981',
  gold: '#F59E0B',
  purple: '#8B5CF6',
  brake: '#EF4444',
} as const

const TIER_COLORS: Record<string, string> = {
  CRITICAL: C.red,
  NOTABLE: C.gold,
  INFO: C.textDim,
}

export default function RaceIntelligencePage() {
  const { key } = useParams<{ key: string }>()
  const sessionKey = parseInt(key)

  const [data, setData] = useState<RaceIntelligenceResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'overview' | 'battles' | 'insights'>('overview')

  useEffect(() => {
    Promise.all([
      api.sessions.get(sessionKey),
      raceIntelligenceApi.get(sessionKey),
    ]).then(([, ri]) => {
      setData(ri)
    }).catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [sessionKey])

  if (loading) return <LoadingSpinner text="Loading race intelligence..." />

  if (!data || !data.driver_states.length) {
    return (
      <div style={{ padding: '48px', textAlign: 'center', color: C.textDim, fontFamily: 'monospace', fontSize: '13px' }}>
        No race intelligence data available for this session.
        <br />
        <span style={{ color: C.textDim, opacity: 0.6 }}>This page requires a race session with lap data.</span>
      </div>
    )
  }

  const { session, driver_states, driver_scores, stint_summaries, battle_gaps, insights } = data
  const raceLabel = sessionTypeLabel(session.session_type)

  const totalPitStops = driver_states.reduce((sum, d) => sum + d.pit_stops, 0)
  const totalDrivers = driver_states.length
  const totalInsights = insights.length

  const MetricBadge = ({ icon: Icon, label, value, color }: { icon: React.ElementType; label: string; value: string | number; color: string }) => (
    <div style={{
      background: C.surface, border: `1px solid ${C.border}`, borderRadius: 16, padding: '16px 20px',
      display: 'flex', alignItems: 'center', gap: 14, boxShadow: '0 2px 8px rgba(37,54,82,0.04)',
    }}>
      <div style={{
        width: 40, height: 40, borderRadius: 12, background: `${color}12`,
        border: `1px solid ${color}22`, display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Icon size={18} style={{ color }} />
      </div>
      <div>
        <div style={{ fontSize: 9, fontWeight: 800, color: C.textDim, fontFamily: 'Space Grotesk', letterSpacing: '0.12em', textTransform: 'uppercase' }}>{label}</div>
        <div style={{ fontSize: 22, fontWeight: 900, color: C.textBright, fontFamily: 'Inter', letterSpacing: '-0.02em' }}>{value}</div>
      </div>
    </div>
  )

  const InsightCard = ({ insight }: { insight: RaceInsight }) => {
    const tierColor = TIER_COLORS[insight.tier] ?? C.textDim
    return (
      <div style={{
        background: C.surface, border: `1px solid ${C.border}`, borderRadius: 16, padding: 18,
        boxShadow: '0 2px 8px rgba(37,54,82,0.04)', borderLeft: `3px solid ${tierColor}`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <span style={{
            padding: '3px 8px', borderRadius: 6, background: `${tierColor}15`,
            color: tierColor, fontSize: 9, fontWeight: 800, fontFamily: 'Space Grotesk',
            letterSpacing: '0.08em', textTransform: 'uppercase',
          }}>
            {insight.tier}
          </span>
          <span style={{ fontSize: 9, color: C.textDim, fontFamily: 'Space Grotesk', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            {insight.category}
          </span>
        </div>
        <div style={{ fontSize: 14, fontWeight: 800, color: C.textBright, marginBottom: 6 }}>{insight.title}</div>
        <div style={{ fontSize: 12, color: C.textMid, lineHeight: 1.6 }}>{insight.detail}</div>
      </div>
    )
  }

  const DriverScoreCard = ({ score, driver }: { score: DriverScore; driver?: DriverState }) => {
    const colour = teamColour(driver?.team_color, driver?.team_name)
    const scorePct = Math.min(100, Math.max(0, score.score)) / 100
    return (
      <div style={{
        background: C.surface, border: `1px solid ${C.border}`, borderRadius: 16, padding: 18,
        display: 'flex', alignItems: 'center', gap: 16, boxShadow: '0 2px 8px rgba(37,54,82,0.04)',
      }}>
        <div style={{ position: 'relative', width: 48, height: 48, flexShrink: 0 }}>
          <svg width="48" height="48" viewBox="0 0 48 48">
            <circle cx="24" cy="24" r="20" fill="none" stroke={C.border} strokeWidth="3" />
            <circle cx="24" cy="24" r="20" fill="none" stroke={colour} strokeWidth="3"
              strokeDasharray={`${scorePct * 125.6} 125.6`}
              transform="rotate(-90 24 24)" strokeLinecap="round" />
          </svg>
          <div style={{
            position: 'absolute', inset: 0, display: 'flex', alignItems: 'center',
            justifyContent: 'center', fontSize: 11, fontWeight: 900, fontFamily: 'JetBrains Mono', color: colour,
          }}>
            {score.score.toFixed(0)}
          </div>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{ width: 3, height: 14, borderRadius: 2, background: colour }} />
            <span style={{ fontSize: 14, fontWeight: 800, color: C.textBright }}>{score.abbreviation}</span>
            <span style={{ fontSize: 10, color: C.textDim }}>{driver?.team_name}</span>
          </div>
          <div style={{ display: 'flex', gap: 12, fontSize: 10, color: C.textDim, fontFamily: 'JetBrains Mono' }}>
            <span>Pace {score.inputs.avg_clean_ms ? formatLapTime(score.inputs.avg_clean_ms) : '—'}</span>
            <span>+{score.inputs.positions_gained ?? 0} pos</span>
            <span>{score.inputs.pit_stops} stops</span>
          </div>
        </div>
      </div>
    )
  }

  const BattleRow = ({ battle }: { battle: BattleGap }) => (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px',
      borderBottom: `1px solid ${C.border}50`, fontSize: 13,
    }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: C.textDim, fontFamily: 'JetBrains Mono', minWidth: 48 }}>
        L{battle.lap_number}
      </div>
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontWeight: 700, color: C.textBright }}>{battle.ahead}</span>
        <span style={{ color: C.textDim, fontSize: 11 }}>vs</span>
        <span style={{ fontWeight: 700, color: C.textBright }}>{battle.behind}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <TrendingUp size={12} style={{ color: C.red }} />
        <span style={{ fontFamily: 'JetBrains Mono', fontWeight: 700, color: C.textSub }}>
          {battle.gap_s.toFixed(1)}s
        </span>
      </div>
      {battle.behind_compound && (
        <div style={{
          padding: '2px 6px', borderRadius: 4, fontSize: 9, fontWeight: 700,
          background: COMPOUND_COLOURS[battle.behind_compound] ?? C.textDim,
          color: battle.behind_compound === 'HARD' || battle.behind_compound === 'MEDIUM' ? '#000' : '#fff',
        }}>
          {COMPOUND_LABEL[battle.behind_compound] ?? battle.behind_compound}
        </div>
      )}
    </div>
  )

  const StintBar = ({ stint }: { stint: StintSummary }) => {
    const totalLaps = stint_summaries.reduce((m, s) => Math.max(m, s.end_lap), 0)
    const left = ((stint.start_lap - 1) / totalLaps) * 100
    const width = (stint.lap_count / totalLaps) * 100
    const bg = COMPOUND_COLOURS[stint.compound] ?? '#666'
    const label = COMPOUND_LABEL[stint.compound] ?? '?'
    const isDark = stint.compound === 'MEDIUM' || stint.compound === 'HARD'
    return (
      <div style={{
        position: 'absolute', left: `${left}%`, width: `${width}%`, height: '100%',
        background: bg, color: isDark ? '#000' : '#fff',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 9, fontWeight: 700, fontFamily: 'JetBrains Mono',
        borderRight: '1px solid rgba(0,0,0,0.15)',
      }}>
        {width > 6 ? `${label} (${stint.lap_count})` : ''}
      </div>
    )
  }

  const sortedDrivers = [...driver_scores].sort((a, b) => b.score - a.score)

  const TabButton = ({ id, label }: { id: string; label: string }) => (
    <button onClick={() => setActiveTab(id as typeof activeTab)} style={{
      padding: '8px 16px', borderRadius: 10, border: 'none', cursor: 'pointer',
      background: activeTab === id ? C.red : 'transparent',
      color: activeTab === id ? '#fff' : C.textDim,
      fontSize: 12, fontWeight: 700, fontFamily: 'Space Grotesk',
      letterSpacing: '0.05em', textTransform: 'uppercase',
      transition: 'all 0.15s ease',
    }}>
      {label}
    </button>
  )

  return (
    <div style={{ background: 'linear-gradient(180deg, #F8F9FC 0%, #F1F4F9 100%)', minHeight: '100vh', paddingBottom: 60 }}>

      {/* Header */}
      <div style={{ background: '#fff', borderBottom: `1px solid ${C.border}`, marginBottom: 24 }}>
        <div style={{ maxWidth: 1400, margin: '0 auto', padding: '16px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
          <Link href={`/sessions/${sessionKey}`}
            style={{ display: 'flex', alignItems: 'center', gap: 8, color: C.textDim, fontSize: 13, textDecoration: 'none', fontWeight: 600 }}>
            <ArrowLeft size={16} /> Back to Session
          </Link>
        </div>
      </div>

      <div style={{ maxWidth: 1400, margin: '0 auto', padding: '0 16px' }}>

        {/* Title */}
        <div style={{ marginBottom: 28 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
            <span style={{ fontSize: 12, fontWeight: 900, color: C.textDim, fontFamily: 'Space Grotesk', letterSpacing: '0.2em' }}>
              {session.year} SEASON
            </span>
            <div style={{ height: 1, flex: 1, background: C.border }} />
          </div>
          <h1 style={{
            fontSize: 'clamp(1.6rem, 4vw, 2.5rem)', fontWeight: 950, color: C.textBright,
            fontFamily: 'Inter', letterSpacing: '-0.03em', lineHeight: 1, marginBottom: 6,
          }}>
            Race Intelligence
          </h1>
          <p style={{ fontSize: 13, color: C.textDim }}>
            {session.gp_name.replace(' Grand Prix', '')} · {raceLabel}
          </p>
        </div>

        {/* Metric Badges */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginBottom: 24 }}>
          <MetricBadge icon={Users} label="Drivers" value={totalDrivers} color={C.purple} />
          <MetricBadge icon={Flag} label="Pit Stops" value={totalPitStops} color={C.red} />
          <MetricBadge icon={Award} label="Insights" value={totalInsights} color={C.gold} />
          <MetricBadge icon={GripVertical} label="Battles" value={battle_gaps.length} color={C.green} />
        </div>

        {/* Tab Navigation */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
          <TabButton id="overview" label="Overview" />
          <TabButton id="battles" label="Battles" />
          <TabButton id="insights" label="Insights" />
        </div>

        {/* ── Overview Tab ── */}
        {activeTab === 'overview' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>

            {/* Driver Scores */}
            <div className="panel" style={{ overflow: 'hidden' }}>
              <div style={{ padding: '16px 20px', borderBottom: `1px solid ${C.border}`, background: C.surfaceAlt, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 11, fontWeight: 800, color: C.textBright, fontFamily: 'Space Grotesk', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                  Driver Performance Scores
                </span>
                <span style={{ fontSize: 9, color: C.textDim, fontFamily: 'Space Grotesk', letterSpacing: '0.08em' }}>
                  0–100 RATING
                </span>
              </div>
              <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
                {sortedDrivers.slice(0, 6).map(score => {
                  const driver = driver_states.find(d => d.driver_number === score.driver_number)
                  return <DriverScoreCard key={score.driver_number} score={score} driver={driver} />
                })}
              </div>
            </div>

            {/* Stint Overview */}
            <div className="panel" style={{ overflow: 'hidden' }}>
              <div style={{ padding: '16px 20px', borderBottom: `1px solid ${C.border}`, background: C.surfaceAlt, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 11, fontWeight: 800, color: C.textBright, fontFamily: 'Space Grotesk', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                  Stint Overview
                </span>
              </div>
              <div style={{ padding: 16 }}>
                {sortedDrivers.slice(0, 6).map(score => {
                  const driverStints = stint_summaries.filter(s => s.driver_number === score.driver_number)
                  const colour = teamColour(
                    driver_states.find(d => d.driver_number === score.driver_number)?.team_color,
                    driver_states.find(d => d.driver_number === score.driver_number)?.team_name
                  )
                  return (
                    <div key={score.driver_number} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                      <div style={{ minWidth: 40, textAlign: 'right' }}>
                        <div style={{ fontSize: 12, fontWeight: 700, color: colour, fontFamily: 'JetBrains Mono' }}>{score.abbreviation}</div>
                      </div>
                      <div style={{ flex: 1, height: 24, background: C.surfaceAlt, borderRadius: 6, position: 'relative', overflow: 'hidden' }}>
                        {driverStints.map((stint, i) => <StintBar key={i} stint={stint} />)}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Key Insights */}
            {insights.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <Zap size={14} style={{ color: C.gold }} />
                  <span style={{ fontSize: 11, fontWeight: 800, color: C.textBright, fontFamily: 'Space Grotesk', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                    Key Findings
                  </span>
                </div>
                {insights.slice(0, 4).map(insight => (
                  <InsightCard key={insight.id} insight={insight} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Battles Tab ── */}
        {activeTab === 'battles' && (
          <div className="panel" style={{ overflow: 'hidden' }}>
            <div style={{ padding: '16px 20px', borderBottom: `1px solid ${C.border}`, background: C.surfaceAlt, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 11, fontWeight: 800, color: C.textBright, fontFamily: 'Space Grotesk', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                On-Track Battles
              </span>
              <span style={{ fontSize: 9, color: C.textDim, fontFamily: 'Space Grotesk', letterSpacing: '0.08em' }}>
                GAP ≤ 2.0S
              </span>
            </div>
            <div>
              {battle_gaps.length === 0 ? (
                <div style={{ padding: 32, textAlign: 'center', color: C.textDim, fontSize: 12 }}>
                  No close battles recorded in this session.
                </div>
              ) : (
                battle_gaps.slice(0, 50).map((battle, i) => (
                  <BattleRow key={i} battle={battle} />
                ))
              )}
            </div>
          </div>
        )}

        {/* ── Insights Tab ── */}
        {activeTab === 'insights' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {insights.length === 0 ? (
              <div style={{ padding: 32, textAlign: 'center', color: C.textDim, fontSize: 12 }}>
                No insights generated for this session.
              </div>
            ) : (
              insights.map(insight => <InsightCard key={insight.id} insight={insight} />)
            )}
          </div>
        )}

      </div>
    </div>
  )
}
