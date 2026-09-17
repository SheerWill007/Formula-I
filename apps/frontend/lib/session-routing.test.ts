import { describe, expect, it } from 'vitest'

import {
  getSessionOverviewRoute,
  getSessionRoute,
  getSessionTelemetryRoute,
  isPracticeSessionType,
} from '@/lib/session-routing'

describe('session routing helpers', () => {
  it('recognizes free practice session types', () => {
    expect(isPracticeSessionType('FP1')).toBe(true)
    expect(isPracticeSessionType('FP2')).toBe(true)
    expect(isPracticeSessionType('FP3')).toBe(true)
    expect(isPracticeSessionType('Q')).toBe(false)
    expect(isPracticeSessionType('R')).toBe(false)
  })

  it('routes practice sessions directly to telemetry', () => {
    expect(getSessionRoute(11281, 'FP1')).toBe('/sessions/11281/telemetry')
    expect(getSessionRoute(11282, 'FP2')).toBe('/sessions/11282/telemetry')
  })

  it('keeps non-practice sessions on the base session route', () => {
    expect(getSessionRoute(11283, 'Q')).toBe('/sessions/11283')
    expect(getSessionRoute(11284, 'SQ')).toBe('/sessions/11284')
    expect(getSessionRoute(11285, 'R')).toBe('/sessions/11285')
  })

  it('builds overview and telemetry routes explicitly', () => {
    expect(getSessionOverviewRoute(11286)).toBe('/sessions/11286/overview')
    expect(getSessionTelemetryRoute(11287)).toBe('/sessions/11287/telemetry')
  })
})
