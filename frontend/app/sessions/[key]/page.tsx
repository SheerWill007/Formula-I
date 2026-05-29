'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import { formatLapTime, formatGap, teamColour, sessionTypeLabel } from '@/lib/utils'
import { getSessionRoute, isPracticeSessionType } from '@/lib/session-routing'
import Link from 'next/link'
import { ArrowLeft, Database, Activity } from 'lucide-react'

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// ── Types ─────────────────────────────────────────────────────────────────────

type Session = {
  session_key: number
  year: number
  gp_name: string
  session_type: string
  session_name: string
  date_start: string
}

// ── Session type config ───────────────────────────────────────────────────────

const SESSION_TYPE_ORDER = ['FP1', 'FP2', 'FP3', 'SQ', 'Q', 'S', 'R']

const SESSION_META: Record<string, { label: string; color: string; desc: string }> = {
  FP1: { label: 'Practice 1', color: '#3671C6', desc: 'Installation & long runs' },
  FP2: { label: 'Practice 2', color: '#3671C6', desc: 'Race simulation day' },
  FP3: { label: 'Practice 3', color: '#3671C6', desc: 'Qualifying prep' },
  SQ: { label: 'Sprint Quali', color: '#FF8000', desc: 'Sprint qualifying' },
  Q: { label: 'Qualifying', color: '#FFD700', desc: 'Grid positions' },
  S: { label: 'Sprint', color: '#FF8000', desc: 'Sprint race' },
  R: { label: 'Race', color: '#E8002D', desc: 'Grand Prix' },
}

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


// ── Page ──────────────────────────────────────────────────────────────────────

export default function SessionPage() {
  const params = useParams()
  const router = useRouter()
  const keyStr = Array.isArray(params.key) ? params.key[0] : (params.key ?? '')
  const sessionKey = parseInt(keyStr)

  const [session, setSession] = useState<Session | null>(null)
  const [siblings, setSiblings] = useState<Session[]>([])
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [raceData, setRaceData] = useState<any[]>([])
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [qualiLaps, setQualiLaps] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  // Step 1: load current session
  useEffect(() => {

    setLoading(true)
    fetch(`${BASE}/api/v1/sessions/${sessionKey}`)
      .then(r => r.json())
      .then(s => setSession(s))
      .catch(() => setSession(null))
      .finally(() => setLoading(false))
  }, [sessionKey])

  // Step 2: load all sessions to find siblings (same GP + year)
  useEffect(() => {
    if (!session) return
    fetch(`${BASE}/api/v1/sessions`)
      .then(r => r.json())
      .then((all: Session[]) => {
        const sibs = all
          .filter(s => s.gp_name === session.gp_name && s.year === session.year)
          .sort((a, b) =>
            SESSION_TYPE_ORDER.indexOf(a.session_type) - SESSION_TYPE_ORDER.indexOf(b.session_type)
          )
        setSiblings(sibs)
      })
      .catch(() => { })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.session_key])

  useEffect(() => {
    if (session?.session_type && isPracticeSessionType(session.session_type)) {
      router.replace(getSessionRoute(sessionKey, session.session_type))
    }
  }, [router, session?.session_type, sessionKey])

  // Step 3: load leaderboard data
  useEffect(() => {
    if (!session?.session_type) return
    const type = session.session_type
    const isR = type === 'R' || type === 'S'
    const isFP = type.startsWith('FP')
    if (isFP) return  // FP has no leaderboard



    const url = isR
      ? `${BASE}/api/v1/sessions/${sessionKey}/race-results`
      : `${BASE}/api/v1/sessions/${sessionKey}/fastest`

    fetch(url)
      .then(r => r.json())
      .then(d => {
        if (isR) setRaceData(Array.isArray(d) ? d : [])
        else setQualiLaps(Array.isArray(d) ? d : (d.laps ?? []))
      })
      .catch(() => { })
      .finally(() => { })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.session_key, session?.session_type])

  // ── Loading / error states ────────────────────────────────────────────────

  if (loading) {
    return (
      <div style={{ padding: '48px', textAlign: 'center', color: '#3F3F46', fontFamily: 'monospace', fontSize: '13px' }}>
        Loading...
      </div>
    )
  }

  if (!session) {
    return (
      <div style={{ padding: '48px', textAlign: 'center', color: '#E8002D', fontFamily: 'monospace' }}>
        Session not found
      </div>
    )
  }

  if (session.session_type && isPracticeSessionType(session.session_type)) {
    return (
      <div style={{ padding: '48px', textAlign: 'center', color: '#3F3F46', fontFamily: 'monospace', fontSize: '13px' }}>
        Opening practice analysis...
      </div>
    )
  }

  // ── Derived values — all null-safe ────────────────────────────────────────

  const type = session.session_type ?? ''
  const isRace = type === 'R' || type === 'S'
  const isFP = type.startsWith('FP')
  const isQuali = !isRace && !isFP
  const meta = SESSION_META[type] ?? { label: session.session_name ?? type, color: '#71717A', desc: '' }

  const hasData = isRace
    ? raceData.length > 0
    : isFP
      ? true
      : qualiLaps.length > 0

  // ── Layout Components ──────────────────────────────────────────────────

  const ToolCard = ({ title, desc, icon: Icon, href, color, sub }: { title: string; desc: string; icon: React.ElementType; href: string; color: string; sub?: string }) => (
    <Link href={href} style={{ textDecoration: 'none', flex: 1 }}>
      <div style={{
        background: '#fff', border: `1px solid ${C.border}`, borderRadius: 24, padding: '24px',
        display: 'flex', flexDirection: 'column', gap: 16, transition: 'all 0.2s ease',
        boxShadow: '0 4px 12px rgba(37,54,82,0.04)', cursor: 'pointer', height: '100%',
        position: 'relative', overflow: 'hidden'
      }}
        onMouseEnter={e => {
          e.currentTarget.style.borderColor = color;
          e.currentTarget.style.boxShadow = `0 12px 32px ${color}15`;
          e.currentTarget.style.transform = 'translateY(-2px)';
        }}
        onMouseLeave={e => {
          e.currentTarget.style.borderColor = C.border;
          e.currentTarget.style.boxShadow = '0 4px 12px rgba(37,54,82,0.04)';
          e.currentTarget.style.transform = 'translateY(0)';
        }}>
        <div style={{ width: 44, height: 44, borderRadius: 12, background: `${color}12`, border: `1px solid ${color}22`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Icon size={20} style={{ color }} />
        </div>
        <div>
          <div style={{ fontSize: 11, fontWeight: 800, color, fontFamily: 'Space Grotesk', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 4 }}>{sub}</div>
          <div style={{ fontSize: 20, fontWeight: 900, color: C.textBright, fontFamily: 'Inter', letterSpacing: '-0.02em', marginBottom: 6 }}>{title}</div>
          <div style={{ fontSize: 13, color: C.textMid, lineHeight: 1.5 }}>{desc}</div>
        </div>
        <div style={{ position: 'absolute', right: 24, top: 24, fontSize: 18, color: '#D1D5DB' }}>→</div>
      </div>
    </Link>
  )

  const Panel = ({ title, children, right }: { title: string; children: React.ReactNode; right?: React.ReactNode }) => (
    <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 24, overflow: 'hidden', boxShadow: '0 4px 12px rgba(37,54,82,0.04)' }}>
      <div style={{ padding: '16px 20px', borderBottom: `1px solid ${C.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#F9FAFB' }}>
        <span style={{ fontSize: 11, fontWeight: 800, color: C.textBright, fontFamily: 'Space Grotesk', letterSpacing: '0.08em', textTransform: 'uppercase' }}>{title}</span>
        {right}
      </div>
      {children}
    </div>
  )

  return (
    <div style={{ background: 'linear-gradient(180deg, #F8F9FC 0%, #F1F4F9 100%)', minHeight: '100vh', paddingBottom: 60 }}>
      {/* Global Header */}
      <div style={{ background: '#fff', borderBottom: `1px solid ${C.border}`, marginBottom: 24 }}>
        <div style={{ maxWidth: 1400, margin: '0 auto', padding: '16px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
          <Link href="/sessions" style={{ display: 'flex', alignItems: 'center', gap: 8, color: C.textDim, fontSize: 13, textDecoration: 'none', fontWeight: 600 }}>
            <ArrowLeft size={16} /> Sessions
          </Link>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {siblings.map(sib => {
              const isA = sib.session_key === sessionKey
              const sColor = SESSION_META[sib.session_type]?.color ?? C.textDim
              return (
                <Link key={sib.session_key} href={getSessionRoute(sib.session_key, sib.session_type)} style={{ textDecoration: 'none' }}>
                  <div style={{
                    padding: '8px 16px', borderRadius: 12, border: `1px solid ${isA ? sColor : C.border}`,
                    background: isA ? `${sColor}12` : 'transparent', color: isA ? sColor : C.textMid,
                    fontSize: 12, fontWeight: 800, fontFamily: 'Space Grotesk', transition: 'all 0.1s'
                  }}>
                    {sib.session_type}
                  </div>
                </Link>
              )
            })}
          </div>
        </div>
      </div>

      <div style={{ maxWidth: 1400, margin: '0 auto', padding: '0 16px' }}>
        {/* GP Identity */}
        <div style={{ marginBottom: 32 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
            <span style={{ fontSize: 12, fontWeight: 900, color: C.textDim, fontFamily: 'Space Grotesk', letterSpacing: '0.2em' }}>{session.year} SEASON</span>
            <div style={{ height: 1, flex: 1, background: C.border }} />
          </div>
          <h1 style={{ fontSize: 'clamp(2rem, 6vw, 3rem)', fontWeight: 950, color: C.textBright, fontFamily: 'Inter', letterSpacing: '-0.04em', lineHeight: 1, marginBottom: 8 }}>
            {session.gp_name.replace(' Grand Prix', '')} <span style={{ color: C.textDim, fontWeight: 400 }}>GP</span>
          </h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: `${meta.color}15`, padding: '6px 12px', borderRadius: 8, border: `1px solid ${meta.color}22` }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: meta.color }} />
              <span style={{ fontSize: 11, fontWeight: 800, color: meta.color, fontFamily: 'Space Grotesk', letterSpacing: '0.05em' }}>{meta.label.toUpperCase()}</span>
            </div>
            <span style={{ fontSize: 13, color: C.textDim, fontWeight: 500 }}>{session.date_start ? new Date(session.date_start).toLocaleDateString('en-GB', { day: 'numeric', month: 'long' }) : ''}</span>
          </div>
        </div>

        {/* Main Hub Grid: 2-col on desktop, 1-col on mobile via CSS class */}
        <div className="session-hub-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 24, alignItems: 'start' }}>

          {/* Left Column: Actions & Insights */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            {hasData ? (
              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 480px)', gap: 20 }}>
                <ToolCard
                  title={isQuali ? "Qualifying Telemetry" : isFP ? "Practice Analysis" : "Race Telemetry"}
                  sub="PRO INSTRUMENTATION"
                  desc="High-precision needle gauging, RPM distribution, and driver modulation comparison."
                  icon={Activity}
                  href={`/sessions/${sessionKey}/telemetry`}
                  color={C.red}
                />
              </div>
            ) : (
              <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 24, padding: 40, textAlign: 'center' }}>
                <Database size={40} style={{ color: C.textDim, marginBottom: 20 }} />
                <h3 style={{ fontSize: 20, fontWeight: 800, color: C.textBright, marginBottom: 8 }}>Session Data Missing</h3>
                <p style={{ color: C.textMid, fontSize: 14, marginBottom: 24, maxWidth: 400, margin: '0 auto 24px' }}>
                  The ingestion pipeline has not been run for this session. Use the command below to load telemetry and results.
                </p>
                <code style={{ background: C.surfaceAlt, padding: '12px 20px', borderRadius: 12, border: `1px solid ${C.border}`, display: 'inline-block', fontSize: 12, color: C.textMid, fontFamily: 'JetBrains Mono' }}>
                  uv run python -m ingestion.ingest_session --session {type}
                </code>
              </div>
            )}


          </div>

          {/* Right Column: Results Sidebar */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }} className="session-sidebar">
            <Panel title={isRace ? "Race Classification" : "Fastest Laps"}
              right={<div style={{ fontSize: 9, fontWeight: 800, color: C.textDim }}>{hasData ? 'LIVE DATA' : 'NO DATA'}</div>}>
              {!hasData ? (
                <div style={{ padding: 32, textAlign: 'center', color: C.textDim, fontSize: 12 }}>Classification unavailable</div>
              ) : (
                <div style={{ maxHeight: 600, overflowY: 'auto' }}>
                  {(isRace ? raceData : qualiLaps).map((d: { driver_number: number, abbreviation: string, team_colour: string, team_name: string, gap_ms: number, lap_time_ms: number, total_laps: number }, i: number) => {
                    const colour = teamColour(d.team_colour, d.team_name)
                    const gap = i === 0 ? null : (isRace ? (d.gap_ms) : (d.lap_time_ms - qualiLaps[0].lap_time_ms))
                    return (
                      <div key={d.driver_number} style={{ display: 'grid', gridTemplateColumns: '32px 1fr auto', padding: '12px 16px', alignItems: 'center', borderBottom: `1px solid ${C.border}50` }}>
                        <span style={{ fontSize: 12, fontWeight: 900, color: i < 3 ? C.textBright : C.textDim, fontFamily: 'JetBrains Mono' }}>{i + 1}</span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <div style={{ width: 3, height: 16, borderRadius: 2, background: colour }} />
                          <div style={{ display: 'flex', flexDirection: 'column' }}>
                            <span style={{ fontSize: 13, fontWeight: 700, color: C.textBright }}>{d.abbreviation}</span>
                            <span style={{ fontSize: 10, color: C.textDim }}>{d.team_name.split(' ')[0]}</span>
                          </div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <div style={{ fontSize: 12, fontWeight: 700, color: C.textBright, fontFamily: 'JetBrains Mono' }}>
                            {isRace ? (d.total_laps + ' L') : formatLapTime(d.lap_time_ms)}
                          </div>
                          {gap !== null && <div style={{ fontSize: 9, color: C.textDim, fontFamily: 'JetBrains Mono' }}>+{isRace ? (d.gap_ms / 1000).toFixed(1) : formatGap(gap)}</div>}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </Panel>
          </div>

        </div>
      </div>
    </div>
  )
}
