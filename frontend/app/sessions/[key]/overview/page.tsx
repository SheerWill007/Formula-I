import Link from 'next/link'
import { notFound } from 'next/navigation'
import type { ReactNode } from 'react'
import { CalendarDays, Clock3, Flag, Radio, Thermometer, Wind, Droplets } from 'lucide-react'

import CountdownTimer from '@/components/schedule/CountdownTimer'
import { api } from '@/lib/api'
import {
  findWeekendBySessionKey,
  getWeekendRoundForSeason,
  pickLatestWeekendSession,
  pickPrimaryWeekendSession,
} from '@/lib/session-weekends'
import { getSessionTelemetryRoute } from '@/lib/session-routing'
import { COMPOUND_COLOURS, formatLapTime, getCircuitName, sessionTypeLabel, teamColour } from '@/lib/utils'
import type { FastestLap, Session } from '@/types/f1'

export const revalidate = 60

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

const SESSION_ORDER: Record<string, number> = {
  FP1: 0,
  FP2: 1,
  FP3: 2,
  SQ: 3,
  SS: 4,
  Q: 5,
  S: 6,
  R: 7,
}

const RACE_LIKE_TYPES = ['R', 'S'] as const
const QUALI_LIKE_TYPES = ['Q', 'SQ'] as const
const COVERAGE_TYPES = ['FP1', 'FP2', 'FP3', 'SQ', 'SS', 'Q', 'S'] as const
const ACTION_EXTRA_TYPES = ['S', 'SS', 'FP1', 'FP2', 'FP3'] as const
const PAGE_BACKGROUND = '#F5F7FB'
const PANEL_SHADOW = '0 16px 36px rgba(24,39,75,0.06)'
const PANEL_BORDER = '1px solid rgba(226,232,240,0.92)'

type RaceResult = {
  driver_number: number
  full_name: string
  abbreviation: string
  team_name: string
  team_colour: string
  total_laps: number
  finish_pos: number | null
  best_lap_ms: number | null
  gap_ms: number | null
  laps_down: number
}

type StintPreview = {
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
}

type PositionChanges = {
  total_laps: number
  drivers: Record<string, {
    abbreviation: string
    team_colour: string
    team_name: string
    positions: Record<string, number>
  }>
}

type SessionReference = {
  current: Session | null
  reference: Session | null
  effective: Session | null
  source: 'current' | 'reference' | 'none'
}

type NextRacePayload = {
  race?: {
    event_name?: string
    circuit?: string
  } | null
  next_session?: {
    name?: string
    date_utc?: string | null
  } | null
} | null

async function fetchJson<T>(path: string, revalidateSeconds = 60): Promise<T | null> {
  try {
    const response = await fetch(`${BASE}${path}`, {
      next: { revalidate: revalidateSeconds },
      headers: { 'Content-Type': 'application/json' },
    })

    if (!response.ok) return null
    return response.json() as Promise<T>
  } catch {
    return null
  }
}

function sortByWeekendOrder(sessions: Session[]): Session[] {
  return [...sessions].sort((a, b) => {
    const timeDelta = new Date(a.date_start ?? 0).getTime() - new Date(b.date_start ?? 0).getTime()
    if (timeDelta !== 0) return timeDelta
    return (SESSION_ORDER[a.session_type] ?? 99) - (SESSION_ORDER[b.session_type] ?? 99)
  })
}

function findSessionByTypes(sessions: Session[], types: readonly string[]): Session | null {
  for (const type of types) {
    const match = sessions.find((session) => session.session_type === type)
    if (match) return match
  }
  return null
}

function resolveSessionReference(
  currentSessions: Session[],
  previousYearSessions: Session[],
  types: readonly string[],
): SessionReference {
  const current = findSessionByTypes(currentSessions, types)
  const reference = findSessionByTypes(previousYearSessions, types)

  if (current) return { current, reference, effective: current, source: 'current' }
  if (reference) return { current: null, reference, effective: reference, source: 'reference' }
  return { current: null, reference: null, effective: null, source: 'none' }
}

function hasWeather(session: Session): boolean {
  return Boolean(
    session.track_temp_c !== null && session.track_temp_c !== undefined
      || session.air_temp_c !== null && session.air_temp_c !== undefined
      || session.humidity_pct !== null && session.humidity_pct !== undefined
      || session.rainfall !== null && session.rainfall !== undefined,
  )
}

function getWeatherSource(currentSessions: Session[], previousYearSessions: Session[]): Session | null {
  return currentSessions.find(hasWeather) ?? previousYearSessions.find(hasWeather) ?? currentSessions[0] ?? previousYearSessions[0] ?? null
}

function formatWeekendDate(startDate: string | null, endDate: string | null): string {
  if (!startDate) return 'Date unavailable'

  const start = new Date(startDate)
  const end = endDate ? new Date(endDate) : start
  const sameMonth = start.toLocaleString('en-GB', { month: 'short' }) === end.toLocaleString('en-GB', { month: 'short' })
  const startLabel = start.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
  const endLabel = end.toLocaleDateString('en-GB', sameMonth ? { day: 'numeric' } : { day: 'numeric', month: 'short' })
  return `${startLabel} - ${endLabel}`
}

function formatRaceGap(result: RaceResult, index: number): string {
  if (index === 0) return 'Winner'
  if (result.laps_down > 0) return `+${result.laps_down} lap${result.laps_down === 1 ? '' : 's'}`
  if (result.gap_ms === null) return 'Gap unavailable'
  return `+${(result.gap_ms / 1000).toFixed(3)}s`
}

function formatSessionSource(reference: SessionReference, label: string): string {
  if (reference.source === 'current') return 'Current weekend'
  if (reference.reference) return `${reference.reference.year} ${label}`
  return 'Not ingested yet'
}

function formatSessionList(sessions: Session[]): string {
  if (!sessions.length) return 'Pending ingest'
  return sessions.map((session) => sessionTypeLabel(session.session_type)).join(' • ')
}

function getWeekendFormatLabel(sessions: Session[]): string {
  const types = new Set(sessions.map((session) => session.session_type))
  if (types.has('S') || types.has('SQ') || types.has('SS')) return 'Sprint weekend'
  if (types.has('R') || types.has('Q')) return 'Standard weekend'
  return 'Partial weekend'
}

function buildPositionPath(
  positions: Record<string, number>,
  totalLaps: number,
  width: number,
  height: number,
  maxPosition: number,
): string {
  const laps = Array.from({ length: totalLaps }, (_, index) => index + 1)
  let previous = maxPosition

  return laps
    .map((lap, index) => {
      const position = positions[String(lap)] ?? previous
      previous = position
      const x = totalLaps <= 1 ? 0 : ((lap - 1) / (totalLaps - 1)) * width
      const y = ((Math.max(1, position) - 1) / Math.max(maxPosition - 1, 1)) * height
      return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`
    })
    .join(' ')
}

function groupStintsByDriver(stints: StintPreview[], driverNumbers: number[]): Map<number, StintPreview[]> {
  const grouped = new Map<number, StintPreview[]>()

  for (const driverNumber of driverNumbers) {
    grouped.set(
      driverNumber,
      stints
        .filter((stint) => stint.driver_number === driverNumber)
        .sort((a, b) => a.start_lap - b.start_lap),
    )
  }

  return grouped
}

function buildCoverageTypes(currentSessions: Session[], previousYearSessions: Session[]): string[] {
  const visible = new Set<string>()

  for (const type of COVERAGE_TYPES) {
    if (
      currentSessions.some((session) => session.session_type === type)
      || previousYearSessions.some((session) => session.session_type === type)
    ) {
      visible.add(type)
    }
  }

  return visible.size ? Array.from(visible) : ['FP1', 'FP2', 'FP3']
}

function buildActionEntries(
  currentSessions: Session[],
  raceReference: SessionReference,
  qualiReference: SessionReference,
) {
  const actions: Array<{ label: string; session: Session | null; reference: Session | null }> = [
    {
      label: raceReference.current ? sessionTypeLabel(raceReference.current.session_type) : 'Race',
      session: raceReference.current,
      reference: raceReference.reference,
    },
    {
      label: qualiReference.current ? sessionTypeLabel(qualiReference.current.session_type) : 'Quali',
      session: qualiReference.current,
      reference: qualiReference.reference,
    },
  ]

  for (const type of ACTION_EXTRA_TYPES) {
    const match = currentSessions.find((session) => session.session_type === type)
    if (match) {
      actions.push({
        label: sessionTypeLabel(match.session_type),
        session: match,
        reference: null,
      })
    }
  }

  const unique = new Set<string>()
  return actions.filter((entry) => {
    const key = entry.session?.session_key ? String(entry.session.session_key) : entry.label
    if (unique.has(key)) return false
    unique.add(key)
    return true
  })
}

function SectionShell({
  eyebrow,
  title,
  badge,
  children,
}: {
  eyebrow: string
  title: string
  badge?: ReactNode
  children: ReactNode
}) {
  return (
    <section style={{
      background: '#FFFFFF',
      border: PANEL_BORDER,
      borderRadius: 28,
      padding: 24,
      boxShadow: PANEL_SHADOW,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
        <div>
          <div style={{
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 10,
            color: '#94A3B8',
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
            marginBottom: 8,
          }}>
            {eyebrow}
          </div>
          <h2 style={{
            margin: 0,
            color: '#14233C',
            fontFamily: 'Inter, sans-serif',
            fontWeight: 900,
            fontSize: 'clamp(1.4rem, 3vw, 2rem)',
            letterSpacing: '-0.04em',
            textTransform: 'uppercase',
          }}>
            {title}
          </h2>
        </div>
        {badge}
      </div>
      {children}
    </section>
  )
}

function SourceBadge({ label, tone = 'neutral' }: { label: string; tone?: 'neutral' | 'reference' | 'live' }) {
  const background = tone === 'reference'
    ? 'rgba(245,158,11,0.10)'
    : tone === 'live'
      ? 'rgba(16,185,129,0.10)'
      : 'rgba(148,163,184,0.10)'
  const color = tone === 'reference'
    ? '#B45309'
    : tone === 'live'
      ? '#047857'
      : '#64748B'
  const dotColor = tone === 'reference'
    ? '#F59E0B'
    : tone === 'live'
      ? '#10B981'
      : '#94A3B8'

  return (
    <div style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      padding: '6px 10px',
      borderRadius: 999,
      background,
      color,
      fontFamily: 'JetBrains Mono, monospace',
      fontSize: 10,
      fontWeight: 700,
      letterSpacing: '0.06em',
      textTransform: 'uppercase',
    }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: dotColor, display: 'inline-block' }} />
      {label}
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div style={{
      background: 'linear-gradient(180deg, rgba(248,250,252,0.96) 0%, rgba(255,255,255,0.98) 100%)',
      border: '1px dashed rgba(148,163,184,0.42)',
      borderRadius: 22,
      padding: 28,
      color: '#64748B',
      fontFamily: 'Inter, sans-serif',
      fontSize: 14,
      lineHeight: 1.7,
      textAlign: 'center',
    }}>
      <div style={{
        width: 44,
        height: 44,
        margin: '0 auto 14px',
        borderRadius: 14,
        background: 'rgba(148,163,184,0.12)',
        border: '1px solid rgba(148,163,184,0.18)',
      }} />
      {message}
    </div>
  )
}

function InfoCard({ label, value }: { label: string; value: string }) {
  return (
    <div style={{
      padding: '12px 14px',
      borderRadius: 18,
      background: 'linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(247,250,255,0.98) 100%)',
      border: '1px solid rgba(204,218,236,0.85)',
      minWidth: 150,
      boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.72)',
    }}>
      <div style={{ fontSize: 9, color: '#94A3B8', fontFamily: 'JetBrains Mono, monospace', textTransform: 'uppercase', letterSpacing: '0.12em' }}>
        {label}
      </div>
      <div style={{ marginTop: 6, color: '#14233C', fontFamily: 'Inter, sans-serif', fontWeight: 800, fontSize: 13 }}>{value}</div>
    </div>
  )
}

function ConditionCard({
  icon,
  label,
  value,
  tone,
}: {
  icon: ReactNode
  label: string
  value: string
  tone: string
}) {
  return (
    <div className="session-overview-card" style={{
      background: 'linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(248,250,255,0.98) 100%)',
      border: '1px solid rgba(214,224,238,0.9)',
      borderRadius: 20,
      padding: 16,
      display: 'flex',
      flexDirection: 'column',
      gap: 10,
      boxShadow: '0 12px 28px rgba(24,39,75,0.05)',
    }}>
      <div style={{ color: tone }}>{icon}</div>
      <div>
        <div style={{
          fontSize: 9,
          fontWeight: 800,
          color: '#94A3B8',
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          fontFamily: 'JetBrains Mono, monospace',
        }}>
          {label}
        </div>
        <div style={{
          fontSize: 18,
          fontWeight: 900,
          color: '#0F172A',
          marginTop: 4,
          fontFamily: 'Inter, sans-serif',
        }}>
          {value}
        </div>
      </div>
    </div>
  )
}

function CircuitPanel({
  gpName,
  circuitName,
  coverageSummary,
  currentSessions,
  coverageTypes,
  currentSessionCount,
  hasReferenceData,
}: {
  gpName: string
  circuitName: string | null
  coverageSummary: string
  currentSessions: Session[]
  coverageTypes: string[]
  currentSessionCount: number
  hasReferenceData: boolean
}) {
  const heading = gpName.replace(' Grand Prix', '')
  const weekendFormat = getWeekendFormatLabel(
    (currentSessions.length ? currentSessions : coverageTypes.map((type) => ({ session_type: type } as Session))),
  )

  return (
    <div style={{
      background: 'linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(246,249,253,0.98) 100%)',
      borderRadius: 26,
      border: '1px solid rgba(214,224,238,0.92)',
      padding: 20,
      minHeight: 320,
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'space-between',
      gap: 16,
      boxShadow: '0 12px 28px rgba(24,39,75,0.06), inset 0 1px 0 rgba(255,255,255,0.72)',
    }}>
      <div style={{
        position: 'relative',
        borderRadius: 22,
        padding: 18,
        background: 'linear-gradient(180deg, rgba(248,250,255,0.96) 0%, rgba(238,244,252,0.96) 100%)',
        border: '1px solid rgba(214,224,238,0.86)',
      }}>
        <div style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: 'linear-gradient(rgba(148,163,184,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.08) 1px, transparent 1px)',
          backgroundSize: '28px 28px',
          maskImage: 'linear-gradient(180deg, rgba(0,0,0,0.72), rgba(0,0,0,0.18))',
          pointerEvents: 'none',
        }} />
        <div style={{ position: 'relative' }}>
          <div style={{
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 10,
            color: '#94A3B8',
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            marginBottom: 8,
          }}>
            Circuit Brief
          </div>
          <div style={{ color: '#14233C', fontFamily: 'Inter, sans-serif', fontWeight: 900, fontSize: 21, lineHeight: 1.08 }}>
            {circuitName ?? gpName}
          </div>
          <p style={{
            margin: '12px 0 0',
            color: '#64748B',
            fontFamily: 'Inter, sans-serif',
            fontSize: 13,
            lineHeight: 1.62,
          }}>
            {heading} overview with the latest ingested sessions, weekend format awareness, and clearly labeled reference data when the current race or qualifying session is not available yet.
          </p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 10 }}>
        <div style={{
          padding: '12px 14px',
          borderRadius: 18,
          background: '#FFFFFF',
          border: '1px solid rgba(214,224,238,0.88)',
        }}>
          <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 9, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Live
          </div>
          <div style={{ marginTop: 6, color: '#14233C', fontFamily: 'Inter, sans-serif', fontWeight: 900, fontSize: 20 }}>
            {currentSessionCount}
          </div>
        </div>
        <div style={{
          padding: '12px 14px',
          borderRadius: 18,
          background: '#FFFFFF',
          border: '1px solid rgba(214,224,238,0.88)',
        }}>
          <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 9, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Mode
          </div>
          <div style={{ marginTop: 6, color: '#14233C', fontFamily: 'Inter, sans-serif', fontWeight: 800, fontSize: 13 }}>
            {hasReferenceData ? 'Hybrid' : 'Live only'}
          </div>
        </div>
        <div style={{
          padding: '12px 14px',
          borderRadius: 18,
          background: '#FFFFFF',
          border: '1px solid rgba(214,224,238,0.88)',
        }}>
          <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 9, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Format
          </div>
          <div style={{ marginTop: 6, color: '#14233C', fontFamily: 'Inter, sans-serif', fontWeight: 800, fontSize: 13 }}>
            {weekendFormat}
          </div>
        </div>
      </div>

      <div style={{
        padding: 16,
        borderRadius: 20,
        background: '#FFFFFF',
        border: '1px solid rgba(214,224,238,0.88)',
      }}>
        <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 9, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>
          Weekend Coverage
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
          {coverageTypes.slice(0, 6).map((type) => (
            <span
              key={type}
              style={{
                padding: '6px 10px',
                borderRadius: 999,
                background: 'rgba(15,23,42,0.04)',
                border: '1px solid rgba(214,224,238,0.88)',
                color: '#475569',
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: 10,
                letterSpacing: '0.05em',
                textTransform: 'uppercase',
              }}
            >
              {sessionTypeLabel(type)}
            </span>
          ))}
        </div>
        <div style={{ color: '#475569', fontFamily: 'Inter, sans-serif', fontWeight: 700, fontSize: 12, lineHeight: 1.55 }}>
          {coverageSummary || 'Pending ingest'}
        </div>
      </div>
    </div>
  )
}

export default async function SessionOverviewPage({ params }: { params: Promise<{ key: string }> }) {
  const { key } = await params
  const sessionKey = Number.parseInt(key, 10)

  if (!Number.isFinite(sessionKey)) {
    notFound()
  }

  const sessions = await api.sessions.list(true).catch(() => [])
  const weekend = findWeekendBySessionKey(sessions, sessionKey)
  if (!weekend) {
    notFound()
  }

  const currentSessions = sortByWeekendOrder(weekend.sessions)
  const previousYearSessions = sortByWeekendOrder(
    sessions.filter((session) => session.year === weekend.year - 1 && session.gp_name === weekend.gp_name),
  )
  const focusedSession = currentSessions.find((session) => session.session_key === sessionKey)
    ?? previousYearSessions.find((session) => session.session_key === sessionKey)
    ?? pickLatestWeekendSession(currentSessions)
    ?? pickPrimaryWeekendSession(currentSessions)
    ?? pickLatestWeekendSession(previousYearSessions)
    ?? pickPrimaryWeekendSession(previousYearSessions)
  if (!focusedSession) {
    notFound()
  }

  const round = getWeekendRoundForSeason(weekend, sessions)
  const circuitName = getCircuitName(weekend.gp_name)
  const weatherSource = getWeatherSource(currentSessions, previousYearSessions)
  const raceReference = resolveSessionReference(currentSessions, previousYearSessions, RACE_LIKE_TYPES)
  const qualiReference = resolveSessionReference(currentSessions, previousYearSessions, QUALI_LIKE_TYPES)
  const coverageTypes = buildCoverageTypes(currentSessions, previousYearSessions)
  const actionEntries = buildActionEntries(currentSessions, raceReference, qualiReference)

  const [raceResults, stintPace, undercut, positionChanges, qualiFastest, nextRaceData] = await Promise.all([
    raceReference.effective ? fetchJson<RaceResult[]>(`/api/v1/sessions/${raceReference.effective.session_key}/race-results`) : Promise.resolve(null),
    raceReference.effective ? fetchJson<StintPreview[]>(`/api/v1/sessions/${raceReference.effective.session_key}/analysis/stint-pace`) : Promise.resolve(null),
    raceReference.effective ? fetchJson<UndercutRow[]>(`/api/v1/sessions/${raceReference.effective.session_key}/analysis/undercut`) : Promise.resolve(null),
    raceReference.effective ? fetchJson<PositionChanges>(`/api/v1/sessions/${raceReference.effective.session_key}/analysis/position-changes`) : Promise.resolve(null),
    qualiReference.effective ? fetchJson<{ laps: FastestLap[] }>(`/api/v1/sessions/${qualiReference.effective.session_key}/fastest`) : Promise.resolve(null),
    fetchJson<NextRacePayload>('/api/v1/schedule/next-race', 300),
  ])

  const classification = (raceResults ?? []).slice(0, 3)
  const topRaceDrivers = classification.map((row) => row.driver_number)
  const groupedStints = groupStintsByDriver(stintPace ?? [], topRaceDrivers)
  const maxRaceLap = positionChanges?.total_laps ?? Math.max(0, ...(raceResults ?? []).map((row) => row.total_laps))
  const topPositionDrivers = classification
    .map((row) => ({
      row,
      trace: positionChanges?.drivers[String(row.driver_number)] ?? null,
    }))
    .filter((entry) => entry.trace)

  const biggestGain = [...(undercut ?? [])]
    .filter((entry) => (entry.pos_gain ?? 0) > 0)
    .sort((a, b) => (b.pos_gain ?? 0) - (a.pos_gain ?? 0))[0] ?? null
  const biggestDrop = [...(undercut ?? [])]
    .filter((entry) => (entry.pos_gain ?? 0) < 0)
    .sort((a, b) => (a.pos_gain ?? 0) - (b.pos_gain ?? 0))[0] ?? null

  const qualifyingPreview = (qualiFastest?.laps ?? []).slice(0, 5)
  const poleLap = qualifyingPreview[0] ?? null
  const activeSessionsSummary = formatSessionList(currentSessions)
  const nextSession = nextRaceData?.next_session
  const nextRace = nextRaceData?.race
  const nextSessionBelongsToWeekend = Boolean(
    nextRace?.event_name
    && nextRace.event_name.toLowerCase().includes(weekend.gp_name.toLowerCase()),
  )

  return (
    <div style={{
      maxWidth: 1280,
      margin: '0 auto',
      padding: '24px 20px 48px',
      display: 'flex',
      flexDirection: 'column',
      gap: 24,
      background: PAGE_BACKGROUND,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <Link href="/sessions" style={{ color: '#64748B', textDecoration: 'none', fontFamily: 'Inter, sans-serif', fontSize: 13, fontWeight: 700 }}>
          Archive
        </Link>
        <span style={{ color: '#CBD5E1' }}>/</span>
        <span style={{ color: '#0F172A', fontFamily: 'Inter, sans-serif', fontSize: 13, fontWeight: 800 }}>
          Weekend Overview
        </span>
      </div>

      <section style={{
        background: 'linear-gradient(180deg, rgba(248,250,255,0.98) 0%, rgba(242,246,252,0.98) 100%)',
        border: PANEL_BORDER,
        borderRadius: 30,
        padding: 24,
        boxShadow: PANEL_SHADOW,
      }}>
        <div className="session-overview-hero" style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.2fr) 360px', gap: 24, alignItems: 'stretch' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <SourceBadge label={`Round ${round} • ${focusedSession.year}`} tone="live" />
              <SourceBadge label={`${currentSessions.length} current sessions`} />
              {raceReference.source === 'reference' || qualiReference.source === 'reference' ? (
                <SourceBadge label={`${weekend.year - 1} references active`} tone="reference" />
              ) : null}
            </div>

            <div>
              <h1 style={{
                margin: 0,
                color: '#14233C',
                fontFamily: 'Inter, sans-serif',
                fontWeight: 900,
                fontSize: 'clamp(2.15rem, 5vw, 3.5rem)',
                letterSpacing: '-0.06em',
                lineHeight: 0.96,
                textTransform: 'uppercase',
              }}>
                {weekend.gp_name.replace(' Grand Prix', '')} Grand Prix
              </h1>
              <p style={{
                margin: '12px 0 0',
                color: '#64748B',
                fontFamily: 'Inter, sans-serif',
                fontSize: 14,
                lineHeight: 1.68,
                maxWidth: 680,
              }}>
                {circuitName ?? weekend.country ?? 'Grand Prix weekend'} • {formatWeekendDate(weekend.startDate, weekend.endDate)}.
                {' '}Current coverage includes {activeSessionsSummary.toLowerCase()}, while race and qualifying summaries fall back to last season only when the current weekend has not reached those sessions yet.
              </p>
            </div>

            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <InfoCard label="Focus Session" value={sessionTypeLabel(focusedSession.session_type)} />
              <InfoCard label="Weekend Window" value={formatWeekendDate(weekend.startDate, weekend.endDate)} />
              <InfoCard label="Weekend Format" value={getWeekendFormatLabel(currentSessions)} />
            </div>

            {nextSession?.date_utc ? (
              <div style={{
                background: 'linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(248,250,255,0.98) 100%)',
                borderRadius: 20,
                padding: '18px 18px 16px',
                border: '1px solid rgba(204,218,236,0.88)',
                boxShadow: '0 12px 28px rgba(24,39,75,0.06)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 20,
                flexWrap: 'wrap',
              }}>
                <div>
                  <div style={{
                    fontFamily: 'JetBrains Mono, monospace',
                    fontSize: 10,
                    color: '#94A3B8',
                    letterSpacing: '0.12em',
                    textTransform: 'uppercase',
                    marginBottom: 8,
                  }}>
                    {nextSessionBelongsToWeekend ? 'Next Session' : 'Next On Calendar'}
                  </div>
                  <div style={{
                    color: '#14233C',
                    fontFamily: 'Inter, sans-serif',
                    fontWeight: 900,
                    fontSize: 'clamp(1rem, 2vw, 1.3rem)',
                    letterSpacing: '-0.03em',
                    textTransform: 'uppercase',
                  }}>
                    {nextSession.name ?? 'Upcoming session'}
                  </div>
                  <div style={{
                    marginTop: 6,
                    color: '#64748B',
                    fontFamily: 'Inter, sans-serif',
                    fontSize: 12,
                    lineHeight: 1.6,
                  }}>
                    {nextRace?.event_name ?? weekend.gp_name}{nextRace?.circuit ? ` • ${nextRace.circuit}` : ''}
                  </div>
                </div>
                <CountdownTimer targetDate={nextSession.date_utc} sessionName={nextSession.name} variant="light" />
              </div>
            ) : null}

            <div className="session-overview-conditions" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 12 }}>
              <ConditionCard icon={<Thermometer size={16} />} label="Track Temp" value={weatherSource?.track_temp_c != null ? `${weatherSource.track_temp_c}°C` : 'N/A'} tone="#E8002D" />
              <ConditionCard icon={<Wind size={16} />} label="Air Temp" value={weatherSource?.air_temp_c != null ? `${weatherSource.air_temp_c}°C` : 'N/A'} tone="#10B981" />
              <ConditionCard icon={<Droplets size={16} />} label="Humidity" value={weatherSource?.humidity_pct != null ? `${weatherSource.humidity_pct}%` : 'N/A'} tone="#0EA5E9" />
              <ConditionCard icon={<CalendarDays size={16} />} label="Surface" value={weatherSource?.rainfall ? 'WET' : 'DRY'} tone="#F59E0B" />
            </div>
          </div>

          <CircuitPanel
            gpName={weekend.gp_name}
            circuitName={circuitName}
            coverageSummary={activeSessionsSummary}
            currentSessions={currentSessions}
            coverageTypes={coverageTypes}
            currentSessionCount={currentSessions.length}
            hasReferenceData={raceReference.source === 'reference' || qualiReference.source === 'reference'}
          />
        </div>
      </section>

      <SectionShell
        eyebrow="Race strategy and tyre picture"
        title={raceReference.effective ? `${sessionTypeLabel(raceReference.effective.session_type)} Overview` : 'Race Overview'}
        badge={
          <SourceBadge
            label={formatSessionSource(raceReference, 'race reference')}
            tone={raceReference.source === 'reference' ? 'reference' : raceReference.source === 'current' ? 'live' : 'neutral'}
          />
        }
      >
        {!raceReference.effective || !(raceResults && raceResults.length) ? (
          <EmptyState message="Race-level data is not available yet. When it is missing this year, the page uses the previous season for reference if the same Grand Prix has already been ingested." />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.2fr) minmax(0, 1fr)', gap: 18 }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              <div style={{
                background: '#F8FBFF',
                border: '1px solid rgba(214,224,238,0.88)',
                borderRadius: 22,
                padding: 18,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 14, gap: 12, flexWrap: 'wrap' }}>
                  <div style={{ fontSize: 12, fontWeight: 800, color: '#14233C', fontFamily: 'Inter, sans-serif', textTransform: 'uppercase' }}>Classification</div>
                  <div style={{ fontSize: 10, color: '#94A3B8', fontFamily: 'JetBrains Mono, monospace' }}>
                    {raceReference.effective.year} • {sessionTypeLabel(raceReference.effective.session_type)}
                  </div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {classification.map((result, index) => {
                    const accent = teamColour(result.team_colour, result.team_name)
                    return (
                      <div key={result.driver_number} style={{
                        display: 'grid',
                        gridTemplateColumns: '28px 4px 1fr auto',
                        gap: 12,
                        alignItems: 'center',
                        padding: '12px 14px',
                        borderRadius: 16,
                        background: '#FFFFFF',
                        border: '1px solid rgba(214,224,238,0.88)',
                      }}>
                        <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: '#64748B', fontWeight: 700 }}>{index + 1}</div>
                        <div style={{ width: 4, height: 34, borderRadius: 999, background: accent }} />
                        <div>
                          <div style={{ color: '#14233C', fontFamily: 'Inter, sans-serif', fontWeight: 800 }}>{result.abbreviation}</div>
                          <div style={{ marginTop: 2, color: '#64748B', fontFamily: 'Inter, sans-serif', fontSize: 12 }}>{result.team_name}</div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <div style={{ fontFamily: 'JetBrains Mono, monospace', color: '#14233C', fontWeight: 800, fontSize: 12 }}>
                            {formatRaceGap(result, index)}
                          </div>
                          <div style={{ marginTop: 4, color: '#94A3B8', fontFamily: 'JetBrains Mono, monospace', fontSize: 10 }}>
                            {result.best_lap_ms ? `best ${formatLapTime(result.best_lap_ms)}` : `${result.total_laps} laps`}
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.1fr) 280px', gap: 16 }}>
                <div style={{
                  background: '#F8FBFF',
                  border: '1px solid rgba(214,224,238,0.88)',
                  borderRadius: 22,
                  padding: 18,
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
                    <div style={{ fontSize: 12, fontWeight: 800, color: '#14233C', fontFamily: 'Inter, sans-serif', textTransform: 'uppercase' }}>
                      Tyre Strategy
                    </div>
                    <div style={{ fontSize: 10, color: '#94A3B8', fontFamily: 'JetBrains Mono, monospace' }}>
                      {raceReference.source === 'reference' ? `From ${raceReference.effective.year}` : 'Current race profile'}
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {classification.map((result) => {
                      const driverStints = groupedStints.get(result.driver_number) ?? []
                      return (
                        <div key={result.driver_number}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 10, marginBottom: 8 }}>
                            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: teamColour(result.team_colour, result.team_name), fontWeight: 700 }}>{result.abbreviation}</span>
                            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: '#94A3B8' }}>
                              {driverStints.length ? `${driverStints.length} stint${driverStints.length === 1 ? '' : 's'}` : 'No clean stint data'}
                            </span>
                          </div>
                          <div style={{
                            display: 'flex',
                            minHeight: 42,
                            borderRadius: 16,
                            overflow: 'hidden',
                            background: '#EAF0F7',
                            border: '1px solid rgba(214,224,238,0.84)',
                          }}>
                            {driverStints.length ? driverStints.map((stint) => {
                              const laps = Math.max(1, stint.end_lap - stint.start_lap + 1)
                              return (
                                <div
                                  key={`${stint.driver_number}-${stint.stint}`}
                                  style={{
                                    width: `${(laps / Math.max(maxRaceLap, 1)) * 100}%`,
                                    minWidth: '16%',
                                    background: COMPOUND_COLOURS[stint.compound] ?? '#CBD5E1',
                                    color: stint.compound === 'HARD' ? '#0F172A' : '#FFFFFF',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    padding: '0 8px',
                                    fontFamily: 'JetBrains Mono, monospace',
                                    fontSize: 10,
                                    fontWeight: 700,
                                    textTransform: 'uppercase',
                                  }}
                                >
                                  {stint.compound} ({laps})
                                </div>
                              )
                            }) : (
                              <div style={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                width: '100%',
                                color: '#64748B',
                                fontFamily: 'Inter, sans-serif',
                                fontSize: 13,
                              }}>
                                Not ingested yet
                              </div>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>

                <div style={{
                  background: '#F8FBFF',
                  border: '1px solid rgba(214,224,238,0.88)',
                  borderRadius: 22,
                  padding: 18,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 12,
                }}>
                  <div style={{ fontSize: 12, fontWeight: 800, color: '#14233C', fontFamily: 'Inter, sans-serif', textTransform: 'uppercase' }}>
                    Race Delta
                  </div>
                  <div style={{
                    background: '#FFFFFF',
                    borderRadius: 16,
                    border: '1px solid rgba(214,224,238,0.88)',
                    padding: 14,
                  }}>
                    <div style={{ fontSize: 9, color: '#94A3B8', fontFamily: 'JetBrains Mono, monospace', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
                      Biggest gainer
                    </div>
                    {biggestGain ? (
                      <>
                        <div style={{ color: '#14233C', fontFamily: 'Inter, sans-serif', fontWeight: 800 }}>{biggestGain.abbreviation}</div>
                        <div style={{ marginTop: 6, color: '#16A34A', fontFamily: 'Inter, sans-serif', fontWeight: 900, fontSize: 28 }}>
                          +{biggestGain.pos_gain}
                        </div>
                        <div style={{ marginTop: 4, color: '#64748B', fontFamily: 'Inter, sans-serif', fontSize: 12 }}>
                          P{biggestGain.pos_before ?? '?'} to P{biggestGain.pos_after ?? '?'} after the stop cycle.
                        </div>
                      </>
                    ) : (
                      <div style={{ color: '#64748B', fontFamily: 'Inter, sans-serif', fontSize: 13 }}>No undercut data yet</div>
                    )}
                  </div>
                  <div style={{
                    background: '#FFFFFF',
                    borderRadius: 16,
                    border: '1px solid rgba(214,224,238,0.88)',
                    padding: 14,
                  }}>
                    <div style={{ fontSize: 9, color: '#94A3B8', fontFamily: 'JetBrains Mono, monospace', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
                      Biggest drop
                    </div>
                    {biggestDrop ? (
                      <>
                        <div style={{ color: '#14233C', fontFamily: 'Inter, sans-serif', fontWeight: 800 }}>{biggestDrop.abbreviation}</div>
                        <div style={{ marginTop: 6, color: '#DC2626', fontFamily: 'Inter, sans-serif', fontWeight: 900, fontSize: 28 }}>
                          {biggestDrop.pos_gain}
                        </div>
                        <div style={{ marginTop: 4, color: '#64748B', fontFamily: 'Inter, sans-serif', fontSize: 12 }}>
                          P{biggestDrop.pos_before ?? '?'} to P{biggestDrop.pos_after ?? '?'} after the stop cycle.
                        </div>
                      </>
                    ) : (
                      <div style={{ color: '#64748B', fontFamily: 'Inter, sans-serif', fontSize: 13 }}>No undercut data yet</div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div style={{
              background: '#F8FBFF',
              border: '1px solid rgba(214,224,238,0.88)',
              borderRadius: 22,
              padding: 18,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
                <div style={{ fontSize: 12, fontWeight: 800, color: '#14233C', fontFamily: 'Inter, sans-serif', textTransform: 'uppercase' }}>
                  Position Evolution
                </div>
                <div style={{ fontSize: 10, color: '#94A3B8', fontFamily: 'JetBrains Mono, monospace' }}>
                  {maxRaceLap ? `L1-L${maxRaceLap}` : 'No trace'}
                </div>
              </div>
              {positionChanges && topPositionDrivers.length > 0 && maxRaceLap > 1 ? (
                <div>
                  <svg viewBox="0 0 520 260" style={{ width: '100%', height: 'auto', display: 'block' }} role="img" aria-label="Race position evolution preview">
                    <rect x="0" y="0" width="520" height="260" rx="18" fill="#FFFFFF" />
                    {[1, Math.max(2, Math.ceil((classification.length + 1) / 2)), Math.max(classification.length, 3)].map((marker, index) => {
                      const y = ((marker - 1) / Math.max(classification.length - 1, 1)) * 220 + 20
                      return (
                        <g key={`${marker}-${index}`}>
                          <line x1="20" y1={y} x2="500" y2={y} stroke="#E2E8F0" strokeWidth="1" />
                          <text x="0" y={y + 4} fill="#94A3B8" fontSize="10" fontFamily="JetBrains Mono, monospace">
                            P{marker}
                          </text>
                        </g>
                      )
                    })}
                    {topPositionDrivers.map(({ row, trace }) => {
                      const accent = teamColour(row.team_colour, row.team_name)
                      return (
                        <path
                          key={row.driver_number}
                          d={buildPositionPath(trace!.positions, maxRaceLap, 480, 220, Math.max(classification.length, 3))}
                          transform="translate(20 20)"
                          fill="none"
                          stroke={accent}
                          strokeWidth="4"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      )
                    })}
                  </svg>
                  <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 14 }}>
                    {topPositionDrivers.map(({ row }) => {
                      const accent = teamColour(row.team_colour, row.team_name)
                      return (
                        <div key={row.driver_number} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <span style={{ width: 14, height: 4, borderRadius: 999, background: accent, display: 'inline-block' }} />
                          <span style={{ color: '#475569', fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}>{row.abbreviation}</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              ) : (
                <EmptyState message="Position trace data is not available for this session yet." />
              )}
            </div>
          </div>
        )}
      </SectionShell>

      <SectionShell
        eyebrow="Qualifying pace benchmark"
        title={qualiReference.effective ? `${sessionTypeLabel(qualiReference.effective.session_type)} Snapshot` : 'Qualifying Snapshot'}
        badge={
          <SourceBadge
            label={formatSessionSource(qualiReference, 'qualifying reference')}
            tone={qualiReference.source === 'reference' ? 'reference' : qualiReference.source === 'current' ? 'live' : 'neutral'}
          />
        }
      >
        {!qualiReference.effective || qualifyingPreview.length === 0 ? (
          <EmptyState message="Qualifying-level lap data is not available yet. When the current weekend has not reached qualifying, the page uses last year's equivalent session when possible." />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '320px minmax(0, 1fr)', gap: 18 }}>
            <div style={{
              background: '#FFFDF5',
              border: '1px solid rgba(241,231,179,0.92)',
              borderRadius: 22,
              padding: 20,
            }}>
              <div style={{ fontSize: 10, color: '#B08900', fontFamily: 'JetBrains Mono, monospace', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Pole benchmark
              </div>
              <div style={{ marginTop: 12, color: '#14233C', fontFamily: 'Inter, sans-serif', fontWeight: 900, fontSize: 34, letterSpacing: '-0.05em' }}>
                {poleLap ? formatLapTime(poleLap.lap_time_ms) : '—'}
              </div>
              <div style={{ marginTop: 10, color: '#475569', fontFamily: 'Inter, sans-serif', fontWeight: 700 }}>
                {poleLap?.abbreviation} • {poleLap?.team_name}
              </div>
              <div style={{ marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 10 }}>
                <div style={{
                  padding: '8px 10px',
                  borderRadius: 12,
                  background: '#FFFFFF',
                  border: '1px solid rgba(241,231,179,0.88)',
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: 10,
                  color: '#7C6C22',
                }}>
                  {poleLap?.compound ? `Compound ${poleLap.compound}` : 'Compound N/A'}
                </div>
                <div style={{
                  padding: '8px 10px',
                  borderRadius: 12,
                  background: '#FFFFFF',
                  border: '1px solid rgba(241,231,179,0.88)',
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: 10,
                  color: '#7C6C22',
                }}>
                  {qualifyingPreview[1] ? `Gap P2 +${((qualifyingPreview[1].lap_time_ms - qualifyingPreview[0].lap_time_ms) / 1000).toFixed(3)}s` : 'Only one lap loaded'}
                </div>
              </div>
            </div>

            <div style={{
              background: '#F8FBFF',
              border: '1px solid rgba(214,224,238,0.88)',
              borderRadius: 22,
              padding: 18,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
                <div style={{ fontSize: 12, fontWeight: 800, color: '#14233C', fontFamily: 'Inter, sans-serif', textTransform: 'uppercase' }}>
                  Top fastest laps
                </div>
                <div style={{ fontSize: 10, color: '#94A3B8', fontFamily: 'JetBrains Mono, monospace' }}>
                  {qualiReference.effective.year} • {sessionTypeLabel(qualiReference.effective.session_type)}
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {qualifyingPreview.map((lap, index) => {
                  const accent = teamColour(lap.team_colour, lap.team_name)
                  const gapToPole = index === 0 ? null : lap.lap_time_ms - qualifyingPreview[0].lap_time_ms
                  return (
                    <div key={`${lap.driver_number}-${lap.lap_number}`} style={{
                      display: 'grid',
                      gridTemplateColumns: '28px 4px 1fr auto',
                      gap: 12,
                      alignItems: 'center',
                      padding: '12px 14px',
                      borderRadius: 16,
                      background: '#FFFFFF',
                      border: '1px solid rgba(214,224,238,0.88)',
                    }}>
                      <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: index === 0 ? '#B08900' : '#64748B', fontWeight: 700 }}>
                        P{index + 1}
                      </div>
                      <div style={{ width: 4, height: 34, borderRadius: 999, background: accent }} />
                      <div>
                        <div style={{ color: '#14233C', fontFamily: 'Inter, sans-serif', fontWeight: 800 }}>{lap.abbreviation}</div>
                        <div style={{ marginTop: 2, color: '#64748B', fontFamily: 'Inter, sans-serif', fontSize: 12 }}>
                          Lap {lap.lap_number}{lap.compound ? ` • ${lap.compound}` : ''}
                        </div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontFamily: 'JetBrains Mono, monospace', color: '#14233C', fontWeight: 800, fontSize: 12 }}>{formatLapTime(lap.lap_time_ms)}</div>
                        <div style={{ marginTop: 4, color: '#94A3B8', fontFamily: 'JetBrains Mono, monospace', fontSize: 10 }}>
                          {gapToPole === null ? 'Pole lap' : `+${(gapToPole / 1000).toFixed(3)}s`}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        )}
      </SectionShell>

      <SectionShell eyebrow="Weekend format awareness" title="Session Coverage">
        <div className="session-overview-coverage" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
          {coverageTypes.map((type) => {
            const reference = resolveSessionReference(currentSessions, previousYearSessions, [type])
            const activeSession = reference.current ?? reference.reference
            return (
              <div key={type} style={{
                background: reference.source === 'current' ? '#F8FBFF' : '#F8FAFC',
                border: `1px solid ${reference.source === 'current' ? 'rgba(214,224,238,0.88)' : 'rgba(226,232,240,0.92)'}`,
                borderRadius: 22,
                padding: 18,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start', marginBottom: 12 }}>
                  <div style={{ color: '#14233C', fontFamily: 'Inter, sans-serif', fontWeight: 900, fontSize: 18 }}>
                    {sessionTypeLabel(type)}
                  </div>
                  <SourceBadge
                    label={reference.source === 'current' ? 'Loaded' : reference.source === 'reference' ? `${activeSession?.year} ref` : 'Missing'}
                    tone={reference.source === 'current' ? 'live' : reference.source === 'reference' ? 'reference' : 'neutral'}
                  />
                </div>
                <p style={{ margin: 0, color: '#64748B', fontFamily: 'Inter, sans-serif', fontSize: 13, lineHeight: 1.6 }}>
                  {reference.source === 'current'
                    ? `${sessionTypeLabel(type)} is available in the current weekend and ready for direct analysis.`
                    : reference.source === 'reference'
                      ? `Current ${sessionTypeLabel(type)} is missing, so the overview keeps a ${activeSession?.year} reference in view for context.`
                      : `${sessionTypeLabel(type)} has not been ingested yet for this Grand Prix.`}
                </p>
                <div style={{ marginTop: 12, color: '#94A3B8', fontFamily: 'JetBrains Mono, monospace', fontSize: 10 }}>
                  {activeSession?.date_start
                    ? new Date(activeSession.date_start).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
                    : 'Awaiting ingest'}
                </div>
              </div>
            )
          })}
        </div>
      </SectionShell>

      <section style={{
        background: '#FFFFFF',
        border: '1px solid rgba(226,232,240,0.92)',
        borderRadius: 28,
        padding: 22,
        boxShadow: '0 20px 48px rgba(24,39,75,0.08)',
      }}>
        <div style={{ marginBottom: 16 }}>
          <div style={{
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 10,
            color: '#94A3B8',
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
            marginBottom: 8,
          }}>
            Bottom handoff
          </div>
          <h2 style={{
            margin: 0,
            color: '#14233C',
            fontFamily: 'Inter, sans-serif',
            fontWeight: 900,
            fontSize: 'clamp(1.3rem, 2.8vw, 1.9rem)',
            letterSpacing: '-0.04em',
            textTransform: 'uppercase',
          }}>
            Session Actions
          </h2>
        </div>

        <div className="session-overview-actions" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
          {actionEntries.map(({ label, session, reference }) => (
            session ? (
              <Link
                key={`${label}-${session.session_key}`}
                href={getSessionTelemetryRoute(session.session_key)}
                className="session-overview-action-link"
                style={{
                  textDecoration: 'none',
                  background: 'linear-gradient(180deg, rgba(248,250,255,0.98) 0%, rgba(241,245,251,0.98) 100%)',
                  border: '1px solid rgba(204,218,236,0.92)',
                  borderRadius: 18,
                  padding: '14px 16px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 12,
                  color: '#14233C',
                  boxShadow: '0 12px 28px rgba(24,39,75,0.06)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{
                    width: 34,
                    height: 34,
                    borderRadius: 10,
                    background: '#FFFFFF',
                    border: '1px solid rgba(214,224,238,0.88)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: session.session_type === 'R' || session.session_type === 'S'
                      ? '#E8002D'
                      : session.session_type === 'Q' || session.session_type === 'SQ'
                        ? '#D4A514'
                        : '#3671C6',
                  }}>
                    {session.session_type === 'R' || session.session_type === 'S'
                      ? <Flag size={16} />
                      : session.session_type === 'Q' || session.session_type === 'SQ'
                        ? <Radio size={16} />
                        : <Clock3 size={16} />}
                  </div>
                  <div>
                    <div style={{ fontFamily: 'Inter, sans-serif', fontWeight: 800, fontSize: 14 }}>{label}</div>
                    <div style={{ marginTop: 2, fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: '#94A3B8' }}>
                      Current {session.session_type}
                    </div>
                  </div>
                </div>
                <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 16, color: '#94A3B8' }}>→</span>
              </Link>
            ) : (
              <div
                key={`${label}-disabled`}
                aria-disabled="true"
                style={{
                  background: '#F8FAFC',
                  border: '1px dashed rgba(203,213,225,0.96)',
                  borderRadius: 18,
                  padding: '14px 16px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  color: '#94A3B8',
                  opacity: 0.84,
                }}
              >
                <div style={{
                  width: 34,
                  height: 34,
                  borderRadius: 10,
                  background: '#FFFFFF',
                  border: '1px solid rgba(226,232,240,0.92)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}>
                  <Clock3 size={16} />
                </div>
                <div>
                  <div style={{ fontFamily: 'Inter, sans-serif', fontWeight: 800, fontSize: 14 }}>{label}</div>
                  <div style={{ marginTop: 2, fontFamily: 'JetBrains Mono, monospace', fontSize: 10 }}>
                    {reference ? `${reference.year} reference above` : 'Not ingested yet'}
                  </div>
                </div>
              </div>
            )
          ))}
        </div>
      </section>

      <style>{`
        .session-overview-action-link {
          transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
        }
        .session-overview-action-link:hover {
          transform: translateY(-3px);
          box-shadow: 0 20px 40px rgba(24,39,75,0.12);
          border-color: rgba(148,163,184,0.36);
        }
        .session-overview-card {
          transition: transform 180ms ease, box-shadow 180ms ease;
        }
        .session-overview-card:hover {
          transform: translateY(-2px);
          box-shadow: 0 16px 36px rgba(24,39,75,0.1);
        }
        @media (max-width: 1180px) {
          .session-overview-hero {
            grid-template-columns: 1fr !important;
          }
        }
        @media (max-width: 980px) {
          .session-overview-conditions {
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
          }
        }
        @media (max-width: 768px) {
          .session-overview-conditions,
          .session-overview-coverage,
          .session-overview-actions {
            grid-template-columns: 1fr !important;
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .session-overview-action-link,
          .session-overview-card {
            transition: none !important;
          }
        }
      `}</style>
    </div>
  )
}
