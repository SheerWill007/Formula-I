'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { Calendar, ChevronDown, ChevronRight, Layers3, Radio, Flag, Clock3 } from 'lucide-react'
import { getSessionOverviewRoute } from '@/lib/session-routing'
import { sessionTypeLabel } from '@/lib/utils'
import type { Session } from '@/types/f1'

type SessionFilter = 'ALL' | 'FP1' | 'FP2' | 'FP3' | 'Q' | 'SQ' | 'R'

type WeekendGroup = {
  key: string
  year: number
  gp_name: string
  country?: string | null
  sessions: Session[]
  startDate: string | null
  endDate: string | null
  round: number
}

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

const SESSION_COLOUR: Record<string, string> = {
  FP1: '#3671C6',
  FP2: '#3671C6',
  FP3: '#3671C6',
  SQ: '#FF8000',
  SS: '#FF8000',
  Q: '#FFD700',
  R: '#E8002D',
}

const FILTER_OPTIONS: { key: SessionFilter; label: string }[] = [
  { key: 'ALL', label: 'All Sessions' },
  { key: 'FP1', label: 'FP1' },
  { key: 'FP2', label: 'FP2' },
  { key: 'FP3', label: 'FP3' },
  { key: 'Q', label: 'Qualifying' },
  { key: 'R', label: 'Race' },
]

function groupSessions(sessions: Session[]): WeekendGroup[] {
  const map = new Map<string, Session[]>()
  for (const s of sessions) {
    const key = `${s.year}__${s.gp_name}`
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(s)
  }

  const typeOrder: Record<string, number> = { FP1: 0, FP2: 1, FP3: 2, SQ: 3, SS: 4, Q: 5, R: 6 }

  return Array.from(map.entries())
    .map(([key, rows]) => {
      const sortedRows = [...rows].sort((a, b) => {
        const timeDelta = new Date(a.date_start ?? 0).getTime() - new Date(b.date_start ?? 0).getTime()
        if (timeDelta !== 0) return timeDelta
        return (typeOrder[a.session_type] ?? 9) - (typeOrder[b.session_type] ?? 9)
      })

      const first = sortedRows[0]
      const start = sortedRows[0]?.date_start ?? null
      const end = sortedRows[sortedRows.length - 1]?.date_start ?? start

      return {
        key,
        year: first.year,
        gp_name: first.gp_name,
        country: first.country ?? null,
        sessions: sortedRows,
        startDate: start,
        endDate: end,
        round: 0,
      }
    })
    .sort((a, b) => new Date(b.startDate ?? 0).getTime() - new Date(a.startDate ?? 0).getTime())
    .map((group, idx, arr) => ({
      ...group,
      round: arr.length - idx,
    }))
}

function formatDateRange(start: string | null, end: string | null) {
  if (!start) return 'Date unavailable'
  const startDate = new Date(start)
  const endDate = end ? new Date(end) : startDate
  const sameMonth = startDate.toLocaleString('en-GB', { month: 'short' }) === endDate.toLocaleString('en-GB', { month: 'short' })
  const startLabel = startDate.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
  const endLabel = endDate.toLocaleDateString('en-GB', sameMonth ? { day: 'numeric' } : { day: 'numeric', month: 'short' })
  return `${startLabel} - ${endLabel}`
}

function sessionSummary(group: WeekendGroup) {
  const quali = group.sessions.find(s => s.session_type === 'Q' || s.session_type === 'SQ')
  const race = group.sessions.find(s => s.session_type === 'R')
  const latest = group.sessions[group.sessions.length - 1]
  return {
    leftLabel: quali ? 'Qualifying' : 'Latest Session',
    leftValue: quali ? sessionTypeLabel(quali.session_type) : sessionTypeLabel(latest.session_type),
    rightLabel: race ? 'Race Session' : 'Weekend Scope',
    rightValue: race ? 'Race Loaded' : `${group.sessions.length} sessions`,
    latest,
  }
}

export default function SessionsPage() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [allYears, setAllYears] = useState<number[]>([])
  const [year, setYear] = useState<number | 'all'>('all')
  const [sessionFilter, setSessionFilter] = useState<SessionFilter>('ALL')
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [isMobile, setIsMobile] = useState(false)

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 1024)
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  useEffect(() => {
    fetch(`${BASE}/api/v1/sessions`)
      .then(r => r.json())
      .then((data: Session[] | { error?: string }) => {
        const rows = Array.isArray(data) ? data : []
        setSessions(rows)
        setAllYears([...new Set(rows.map(s => s.year))].sort((a, b) => b - a))
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const filteredByYear = year === 'all' ? sessions : sessions.filter(s => s.year === year)
  const filteredByType = sessionFilter === 'ALL'
    ? filteredByYear
    : filteredByYear.filter(s => s.session_type === sessionFilter || (sessionFilter === 'Q' && s.session_type === 'SQ'))

  const grouped = useMemo(() => groupSessions(filteredByType), [filteredByType])
  const displayYear = year === 'all' ? 'Historical' : year

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '18px', maxWidth: '1080px', margin: '0 auto', padding: isMobile ? '0 8px 32px' : '0 12px 48px' }}>
      <section style={{
        padding: '22px',
        borderRadius: '28px',
        background: 'linear-gradient(180deg, rgba(248,250,255,0.98) 0%, rgba(242,246,252,0.98) 100%)',
        border: '1px solid rgba(207,219,235,0.92)',
        boxShadow: '0 18px 48px rgba(24,39,75,0.10)',
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '18px', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: '10px', color: '#7A8CA5', fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: '10px' }}>
              Kinetic Precision
            </div>
            <h1 style={{ margin: 0, color: '#14233C', fontSize: isMobile ? '2.2rem' : 'clamp(2rem, 4vw, 3.3rem)', lineHeight: 0.98, fontFamily: 'Inter, sans-serif', fontWeight: 800 }}>
              {displayYear} {year === 'all' ? 'Archive' : 'Season'}
            </h1>
            <p style={{ margin: '10px 0 0', color: '#56657C', fontSize: '15px', lineHeight: 1.6, maxWidth: '640px', fontFamily: 'Inter, sans-serif' }}>
              Complete telemetry, session timelines, and weekend analytics for every Grand Prix in the current archive scope.
            </p>
          </div>

          <div style={{ position: 'relative' }}>
            <button
              onClick={() => setOpen(o => !o)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                background: '#fff',
                border: '1px solid rgba(204,218,236,0.92)',
                color: '#14233C',
                fontSize: '12px',
                padding: '11px 14px',
                borderRadius: '999px',
                cursor: 'pointer',
                fontFamily: 'JetBrains Mono, monospace',
                boxShadow: '0 10px 24px rgba(24,39,75,0.08)',
              }}
            >
              {year === 'all' ? 'All Years' : year}
              <ChevronDown size={13} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }} />
            </button>
            {open && (
              <div style={{
                position: 'absolute',
                right: 0,
                top: 'calc(100% + 8px)',
                background: 'rgba(248,250,255,0.99)',
                border: '1px solid rgba(204,218,236,0.95)',
                borderRadius: '18px',
                overflow: 'hidden',
                zIndex: 40,
                minWidth: '150px',
                boxShadow: '0 20px 48px rgba(24,39,75,0.16)',
              }}>
                {(['all', ...allYears] as (number | 'all')[]).map(y => (
                  <button
                    key={y}
                    onClick={() => { setYear(y); setOpen(false) }}
                    style={{
                      display: 'block',
                      width: '100%',
                      textAlign: 'left',
                      padding: '11px 14px',
                      fontSize: '12px',
                      cursor: 'pointer',
                      background: year === y ? 'rgba(20,35,60,0.05)' : 'transparent',
                      color: year === y ? '#14233C' : '#56657C',
                      fontFamily: 'JetBrains Mono, monospace',
                      border: 'none',
                      borderBottom: '1px solid rgba(204,218,236,0.72)',
                    }}
                  >
                    {y === 'all' ? 'All Years' : y}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', marginTop: '18px' }}>
          <div style={{ padding: '12px 14px', borderRadius: '18px', background: '#fff', border: '1px solid rgba(204,218,236,0.9)', minWidth: '150px' }}>
            <div style={{ fontSize: '9px', color: '#7A8CA5', fontFamily: 'JetBrains Mono, monospace', textTransform: 'uppercase', letterSpacing: '0.12em', marginBottom: '6px' }}>Grand Prix</div>
            <div style={{ color: '#14233C', fontSize: '22px', fontFamily: 'Rajdhani, sans-serif', fontWeight: 700 }}>{grouped.length}</div>
          </div>
          <div style={{ padding: '12px 14px', borderRadius: '18px', background: '#fff', border: '1px solid rgba(204,218,236,0.9)', minWidth: '150px' }}>
            <div style={{ fontSize: '9px', color: '#7A8CA5', fontFamily: 'JetBrains Mono, monospace', textTransform: 'uppercase', letterSpacing: '0.12em', marginBottom: '6px' }}>Sessions</div>
            <div style={{ color: '#14233C', fontSize: '22px', fontFamily: 'Rajdhani, sans-serif', fontWeight: 700 }}>{filteredByType.length}</div>
          </div>
          <div style={{ padding: '12px 14px', borderRadius: '18px', background: '#fff', border: '1px solid rgba(204,218,236,0.9)', minWidth: '170px' }}>
            <div style={{ fontSize: '9px', color: '#7A8CA5', fontFamily: 'JetBrains Mono, monospace', textTransform: 'uppercase', letterSpacing: '0.12em', marginBottom: '6px' }}>Filter</div>
            <div style={{ color: '#14233C', fontSize: '20px', fontFamily: 'Rajdhani, sans-serif', fontWeight: 700 }}>{FILTER_OPTIONS.find(f => f.key === sessionFilter)?.label ?? 'All Sessions'}</div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap', marginTop: '20px' }}>
          <div style={{ fontSize: '10px', color: '#7A8CA5', fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.14em', textTransform: 'uppercase', marginRight: '2px' }}>
            Filter Sessions:
          </div>
          {FILTER_OPTIONS.map(option => {
            const active = option.key === sessionFilter
            return (
              <button
                key={option.key}
                onClick={() => setSessionFilter(option.key)}
                style={{
                  padding: '10px 16px',
                  borderRadius: '14px',
                  border: active ? '1px solid rgba(59,130,246,0.16)' : '1px solid rgba(204,218,236,0.9)',
                  background: active ? 'rgba(59,130,246,0.08)' : '#fff',
                  color: active ? '#14233C' : '#56657C',
                  fontFamily: 'Inter, sans-serif',
                  fontSize: '13px',
                  fontWeight: active ? 700 : 600,
                  cursor: 'pointer',
                  boxShadow: active ? '0 10px 26px rgba(59,130,246,0.08)' : 'none',
                }}
              >
                {option.label}
              </button>
            )
          })}
        </div>
      </section>

      {loading && (
        <div style={{ textAlign: 'center', padding: '64px 0', color: '#7A8CA5', fontFamily: 'JetBrains Mono, monospace', fontSize: '13px' }}>
          Loading archive...
        </div>
      )}

      {!loading && grouped.length === 0 && (
        <div style={{ textAlign: 'center', padding: '64px 0', color: '#7A8CA5', fontFamily: 'JetBrains Mono, monospace', fontSize: '13px' }}>
          No archive sessions available for this filter.
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        {grouped.map(group => {
          const summary = sessionSummary(group)
          return (
            <div
              key={group.key}
              style={{
                background: 'linear-gradient(180deg, rgba(248,250,255,0.98) 0%, rgba(243,247,252,0.98) 100%)',
                border: '1px solid rgba(204,218,236,0.92)',
                borderRadius: '24px',
                padding: isMobile ? '14px' : '18px',
                boxShadow: '0 16px 40px rgba(24,39,75,0.08)',
              }}
            >
              <div className="sessions-grid-row" style={{ display: 'grid', gridTemplateColumns: isMobile ? '64px 1fr 48px' : '84px 1.3fr 1fr 52px', gap: isMobile ? '12px' : '18px', alignItems: 'center' }}>
                <div style={{
                  borderRadius: '18px',
                  background: '#F1F5FB',
                  border: '1px solid rgba(214,224,238,0.92)',
                  padding: isMobile ? '10px 8px' : '14px 12px',
                  textAlign: 'center',
                }}>
                  <div style={{ fontSize: '9px', color: '#7A8CA5', fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.12em', textTransform: 'uppercase' }}>Rnd</div>
                  <div style={{ color: '#14233C', fontSize: isMobile ? '24px' : '32px', lineHeight: 1, fontFamily: 'Rajdhani, sans-serif', fontWeight: 700, marginTop: '4px' }}>
                    {String(group.round).padStart(2, '0')}
                  </div>
                </div>

                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap', marginBottom: '6px' }}>
                    <div style={{ fontSize: isMobile ? '16px' : '18px', color: '#14233C', fontFamily: 'Inter, sans-serif', fontWeight: 800 }}>
                      {group.gp_name}
                    </div>
                    {!isMobile && (
                      <div style={{
                        padding: '4px 8px',
                        borderRadius: '999px',
                        background: '#EEF4FF',
                        color: '#7A8CA5',
                        fontSize: '9px',
                        fontFamily: 'JetBrains Mono, monospace',
                        letterSpacing: '0.1em',
                        textTransform: 'uppercase',
                      }}>
                        Completed
                      </div>
                    )}
                  </div>
                  <div style={{ fontSize: isMobile ? '13px' : '14px', color: '#56657C', fontFamily: 'Inter, sans-serif', fontWeight: 600 }}>
                    {group.country ?? 'Grand Prix weekend'}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap', marginTop: '8px', color: '#7A8CA5', fontSize: '11px', fontFamily: 'JetBrains Mono, monospace' }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                      <Calendar size={11} />
                      {formatDateRange(group.startDate, group.endDate)}
                    </span>
                    {!isMobile && (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                        <Layers3 size={11} />
                        {group.sessions.length} sessions
                      </span>
                    )}
                  </div>
                </div>

                {!isMobile && (
                  <div className="sessions-stats-box" style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: '10px',
                  }}>
                    <div style={{
                      borderRadius: '18px',
                      background: '#F5F8FD',
                      border: '1px solid rgba(214,224,238,0.82)',
                      padding: '12px 14px',
                    }}>
                      <div style={{ fontSize: '8px', color: '#7A8CA5', fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: '8px' }}>
                        {summary.leftLabel}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
                        <div style={{ width: '4px', height: '20px', borderRadius: '999px', background: SESSION_COLOUR[summary.latest.session_type] ?? '#94A3B8' }} />
                        <div>
                          <div style={{ fontSize: '14px', color: '#14233C', fontFamily: 'Inter, sans-serif', fontWeight: 700 }}>
                            {summary.leftValue}
                          </div>
                          <div style={{ fontSize: '10px', color: '#7A8CA5', fontFamily: 'JetBrains Mono, monospace', marginTop: '2px' }}>
                            {summary.latest.date_start ? new Date(summary.latest.date_start).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : 'Loaded'}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div style={{
                      borderRadius: '18px',
                      background: '#F5F8FD',
                      border: '1px solid rgba(214,224,238,0.82)',
                      padding: '12px 14px',
                    }}>
                      <div style={{ fontSize: '8px', color: '#7A8CA5', fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: '8px' }}>
                        {summary.rightLabel}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
                        <div style={{ width: '4px', height: '20px', borderRadius: '999px', background: '#3671C6' }} />
                        <div>
                          <div style={{ fontSize: '14px', color: '#14233C', fontFamily: 'Inter, sans-serif', fontWeight: 700 }}>
                            {summary.rightValue}
                          </div>
                          <div style={{ fontSize: '10px', color: '#7A8CA5', fontFamily: 'JetBrains Mono, monospace', marginTop: '2px' }}>
                            Archive ready
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                <Link
                  href={getSessionOverviewRoute(summary.latest.session_key)}
                  style={{
                    width: isMobile ? '42px' : '52px',
                    height: isMobile ? '42px' : '52px',
                    borderRadius: '50%',
                    background: '#EDF4FF',
                    border: '1px solid rgba(204,218,236,0.95)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#14233C',
                    textDecoration: 'none',
                    boxShadow: '0 10px 24px rgba(24,39,75,0.08)',
                  }}
                >
                  <ChevronRight size={isMobile ? 16 : 18} />
                </Link>
              </div>

              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '16px', paddingTop: '14px', borderTop: '1px solid rgba(204,218,236,0.78)' }}>
                {group.sessions.map(session => {
                  const colour = SESSION_COLOUR[session.session_type] ?? '#94A3B8'
                  const Icon = session.session_type === 'R' ? Flag : session.session_type === 'Q' || session.session_type === 'SQ' ? Radio : Clock3
                  return (
                    <Link
                      key={session.session_key}
                      href={getSessionOverviewRoute(session.session_key)}
                      style={{
                        textDecoration: 'none',
                        color: '#14233C',
                        background: '#fff',
                        border: '1px solid rgba(204,218,236,0.88)',
                        borderRadius: '14px',
                        padding: isMobile ? '8px 10px' : '10px 12px',
                        minWidth: isMobile ? 'auto' : '132px',
                        flex: isMobile ? '1 1 auto' : 'none',
                        boxShadow: '0 8px 20px rgba(24,39,75,0.04)',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <div style={{
                          width: '26px',
                          height: '26px',
                          borderRadius: '8px',
                          background: `${colour}16`,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          color: colour,
                          flexShrink: 0,
                        }}>
                          <Icon size={13} />
                        </div>
                        <div>
                          <div style={{ fontSize: '12px', fontFamily: 'Inter, sans-serif', fontWeight: 700, color: '#14233C' }}>
                            {isMobile ? session.session_type : sessionTypeLabel(session.session_type)}
                          </div>
                          {!isMobile && (
                            <div style={{ fontSize: '10px', fontFamily: 'JetBrains Mono, monospace', color: '#7A8CA5', marginTop: '2px' }}>
                              {session.session_type}
                            </div>
                          )}
                        </div>
                      </div>
                    </Link>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
