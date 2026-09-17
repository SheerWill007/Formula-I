import type { Session } from '@/types/f1'

export type WeekendGroup = {
  key: string
  year: number
  gp_name: string
  country?: string | null
  sessions: Session[]
  startDate: string | null
  endDate: string | null
}

const SESSION_TYPE_ORDER: Record<string, number> = {
  FP1: 0,
  FP2: 1,
  FP3: 2,
  SQ: 3,
  SS: 4,
  Q: 5,
  S: 6,
  R: 7,
}

const PRIMARY_SESSION_ORDER = ['R', 'Q', 'SQ', 'FP3', 'FP2', 'FP1', 'S', 'SS'] as const

function toDateValue(value: string | null | undefined): number {
  if (!value) return 0
  return new Date(value).getTime()
}

export function sortWeekendSessions(sessions: Session[]): Session[] {
  return [...sessions].sort((a, b) => {
    const timeDelta = toDateValue(a.date_start) - toDateValue(b.date_start)
    if (timeDelta !== 0) return timeDelta
    return (SESSION_TYPE_ORDER[a.session_type] ?? 99) - (SESSION_TYPE_ORDER[b.session_type] ?? 99)
  })
}

export function groupSessionsIntoWeekends(sessions: Session[]): WeekendGroup[] {
  const grouped = new Map<string, Session[]>()

  for (const session of sessions) {
    const key = `${session.year}__${session.gp_name}`
    if (!grouped.has(key)) grouped.set(key, [])
    grouped.get(key)!.push(session)
  }

  return Array.from(grouped.entries())
    .map(([key, rows]) => {
      const sorted = sortWeekendSessions(rows)
      const first = sorted[0]
      return {
        key,
        year: first.year,
        gp_name: first.gp_name,
        country: first.country ?? null,
        sessions: sorted,
        startDate: sorted[0]?.date_start ?? null,
        endDate: sorted[sorted.length - 1]?.date_start ?? sorted[0]?.date_start ?? null,
      }
    })
    .sort((a, b) => toDateValue(b.startDate) - toDateValue(a.startDate))
}

export function pickPrimaryWeekendSession(sessions: Session[]): Session | null {
  for (const sessionType of PRIMARY_SESSION_ORDER) {
    const match = sessions.find((session) => session.session_type === sessionType)
    if (match) return match
  }

  return sortWeekendSessions(sessions)[0] ?? null
}

export function pickLatestWeekendSession(sessions: Session[]): Session | null {
  return sortWeekendSessions(sessions).at(-1) ?? null
}

export function getLatestWeekendOverviewRoute(sessions: Session[]): string | null {
  const latestWeekend = groupSessionsIntoWeekends(sessions)[0]
  if (!latestWeekend) return null

  const latestSession = pickLatestWeekendSession(latestWeekend.sessions)
  return latestSession ? `/sessions/${latestSession.session_key}/overview` : null
}

export function findWeekendBySessionKey(sessions: Session[], sessionKey: number): WeekendGroup | null {
  const grouped = groupSessionsIntoWeekends(sessions)
  return grouped.find((weekend) =>
    weekend.sessions.some((session) => session.session_key === sessionKey),
  ) ?? null
}

export function getWeekendRoundForSeason(target: WeekendGroup, sessions: Session[]): number {
  const seasonWeekends = groupSessionsIntoWeekends(
    sessions.filter((session) => session.year === target.year),
  ).sort((a, b) => toDateValue(a.startDate) - toDateValue(b.startDate))

  const index = seasonWeekends.findIndex((weekend) => weekend.key === target.key)
  return index >= 0 ? index + 1 : seasonWeekends.length
}
