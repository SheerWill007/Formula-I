import { describe, expect, it } from 'vitest'

import {
  findWeekendBySessionKey,
  getLatestWeekendOverviewRoute,
  pickLatestWeekendSession,
  getWeekendRoundForSeason,
  groupSessionsIntoWeekends,
  pickPrimaryWeekendSession,
} from '@/lib/session-weekends'
import type { Session } from '@/types/f1'

const baseSession = {
  country: 'Australia',
  session_name: 'Session',
  drivers: [],
}

function makeSession(overrides: Partial<Session> & Pick<Session, 'session_key' | 'year' | 'gp_name' | 'session_type'>): Session {
  return {
    ...baseSession,
    air_temp_c: null,
    gp_name: overrides.gp_name,
    humidity_pct: null,
    rainfall: null,
    session_key: overrides.session_key,
    session_name: overrides.session_name ?? overrides.session_type,
    session_type: overrides.session_type,
    track_temp_c: null,
    year: overrides.year,
    country: overrides.country ?? 'Australia',
    date_start: overrides.date_start ?? null,
  }
}

describe('session weekend helpers', () => {
  it('routes latest weekend overview to the newest ingested session in that weekend', () => {
    const sessions = [
      makeSession({ session_key: 101, year: 2026, gp_name: 'Australian Grand Prix', session_type: 'FP1', date_start: '2026-03-12T09:00:00Z' }),
      makeSession({ session_key: 102, year: 2026, gp_name: 'Australian Grand Prix', session_type: 'Q', date_start: '2026-03-14T09:00:00Z' }),
      makeSession({ session_key: 103, year: 2026, gp_name: 'Australian Grand Prix', session_type: 'R', date_start: '2026-03-15T09:00:00Z' }),
      makeSession({ session_key: 201, year: 2026, gp_name: 'Chinese Grand Prix', session_type: 'FP1', date_start: '2026-03-20T09:00:00Z' }),
      makeSession({ session_key: 202, year: 2026, gp_name: 'Chinese Grand Prix', session_type: 'Q', date_start: '2026-03-21T07:00:00Z' }),
      makeSession({ session_key: 203, year: 2026, gp_name: 'Chinese Grand Prix', session_type: 'SQ', date_start: '2026-03-21T11:00:00Z' }),
      makeSession({ session_key: 204, year: 2026, gp_name: 'Chinese Grand Prix', session_type: 'SS', date_start: '2026-03-22T03:00:00Z' }),
    ]

    expect(getLatestWeekendOverviewRoute(sessions)).toBe('/sessions/204/overview')
  })

  it('falls back to null when no weekends exist', () => {
    expect(getLatestWeekendOverviewRoute([])).toBeNull()
  })

  it('prefers race data as the primary session when available', () => {
    const primary = pickPrimaryWeekendSession([
      makeSession({ session_key: 1, year: 2026, gp_name: 'Miami Grand Prix', session_type: 'FP3' }),
      makeSession({ session_key: 2, year: 2026, gp_name: 'Miami Grand Prix', session_type: 'Q' }),
      makeSession({ session_key: 3, year: 2026, gp_name: 'Miami Grand Prix', session_type: 'R' }),
    ])

    expect(primary?.session_key).toBe(3)
  })

  it('picks the most recent session in a weekend when asked for the latest session', () => {
    const latest = pickLatestWeekendSession([
      makeSession({ session_key: 1, year: 2026, gp_name: 'Miami Grand Prix', session_type: 'FP1', date_start: '2026-05-01T09:00:00Z' }),
      makeSession({ session_key: 2, year: 2026, gp_name: 'Miami Grand Prix', session_type: 'Q', date_start: '2026-05-02T09:00:00Z' }),
      makeSession({ session_key: 3, year: 2026, gp_name: 'Miami Grand Prix', session_type: 'S', date_start: '2026-05-03T09:00:00Z' }),
    ])

    expect(latest?.session_key).toBe(3)
  })

  it('finds the weekend for any session key and computes its round', () => {
    const sessions = [
      makeSession({ session_key: 11, year: 2026, gp_name: 'Australian Grand Prix', session_type: 'R', date_start: '2026-03-15T09:00:00Z' }),
      makeSession({ session_key: 21, year: 2026, gp_name: 'Chinese Grand Prix', session_type: 'R', date_start: '2026-03-22T09:00:00Z' }),
      makeSession({ session_key: 31, year: 2026, gp_name: 'Japanese Grand Prix', session_type: 'Q', date_start: '2026-04-05T09:00:00Z' }),
    ]

    const weekends = groupSessionsIntoWeekends(sessions)
    const target = findWeekendBySessionKey(sessions, 21)

    expect(weekends).toHaveLength(3)
    expect(target?.gp_name).toBe('Chinese Grand Prix')
    expect(target ? getWeekendRoundForSeason(target, sessions) : null).toBe(2)
  })
})
